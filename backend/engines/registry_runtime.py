"""RegistryRuntime — estado runtime del Slot Registry (SR.1).

Wrapper in-memory alrededor de `SlotRegistry` (el objeto estático
parseado por `load_registry()`) que:

1. Sirve consultas concurrentes con un `asyncio.Lock`.
2. Mantiene una overlay de **warmup** — set de slots que se están
   recalentando tras un hot-reload. Los slots en warmup NO son
   "scannable" para el scan loop.
3. Traduce el `SlotState` del registry (OPERATIVE/DEGRADED/DISABLED)
   más la overlay a un **status runtime** consumible por el frontend:
   `"active" | "warming_up" | "degraded" | "disabled"`.

**Persistencia:** si se pasó `registry_path` al construir, las
mutaciones que cambian el base state (`disable_slot`,
`replace_registry`) escriben el nuevo estado a disco de forma atómica.
Si la escritura falla, el cambio in-memory se revierte (fail-fast).

**Slot "scannable":** `status == "active"` (base OPERATIVE + no
warming_up). El scan loop consume `list_scannable_tickers()`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from modules.slot_registry import SlotRecord, SlotRegistry, save_registry

SlotRuntimeStatus = Literal["active", "warming_up", "degraded", "disabled"]


class RegistryRuntime:
    """Estado runtime del registry. Single source of truth del scan loop."""

    def __init__(
        self,
        registry: SlotRegistry,
        *,
        registry_path: str | Path | None = None,
    ) -> None:
        self._registry = registry
        self._warming: set[int] = set()
        self._lock = asyncio.Lock()
        self._registry_path: Path | None = (
            Path(registry_path) if registry_path is not None else None
        )

    # ─────────────────────────────────────────────────────────────────────
    # Lecturas
    # ─────────────────────────────────────────────────────────────────────

    async def list_scannable_tickers(self) -> list[tuple[int, str]]:
        """Retorna `[(slot_id, ticker), ...]` de los slots scannables.

        "Scannable" = base state OPERATIVE y no está en warmup.

        Ordenado por `slot_id` ascendente para determinismo.
        """
        async with self._lock:
            return sorted(
                [
                    (s.slot, s.ticker)
                    for s in self._registry.operative_slots
                    if s.ticker is not None and s.slot not in self._warming
                ],
                key=lambda t: t[0],
            )

    async def list_slots(self) -> list[dict[str, Any]]:
        """Snapshot completo de los 6 slots con status runtime."""
        async with self._lock:
            return [self._serialize(s) for s in self._registry.slots]

    async def get_slot(self, slot_id: int) -> dict[str, Any] | None:
        """Devuelve el dict del slot `slot_id`, o `None` si no existe."""
        async with self._lock:
            for s in self._registry.slots:
                if s.slot == slot_id:
                    return self._serialize(s)
            return None

    async def effective_status(self, slot_id: int) -> SlotRuntimeStatus | None:
        """Status runtime de un slot. `None` si `slot_id` no existe."""
        async with self._lock:
            for s in self._registry.slots:
                if s.slot == slot_id:
                    return self._effective_status(s)
            return None

    async def get_fixture_dict(self, slot_id: int) -> dict[str, Any] | None:
        """Fixture del slot como dict (para pasar a `scan_and_emit()`).

        Retorna `None` si el slot no existe, está DEGRADED o DISABLED,
        o si el registry no tiene la fixture parseada.
        """
        async with self._lock:
            for s in self._registry.slots:
                if s.slot == slot_id and s.fixture is not None:
                    return s.fixture.model_dump(mode="json")
            return None

    # ─────────────────────────────────────────────────────────────────────
    # Overlay de warmup
    # ─────────────────────────────────────────────────────────────────────

    async def mark_warming(self, slot_id: int) -> None:
        """Marca el slot como warming_up — el scan loop lo excluye."""
        async with self._lock:
            self._warming.add(slot_id)

    async def mark_warmed(self, slot_id: int) -> None:
        """Termina el warmup de un slot. Idempotente."""
        async with self._lock:
            self._warming.discard(slot_id)

    async def is_warming(self, slot_id: int) -> bool:
        async with self._lock:
            return slot_id in self._warming

    async def warming_slots(self) -> list[int]:
        async with self._lock:
            return sorted(self._warming)

    # ─────────────────────────────────────────────────────────────────────
    # Reload atómico del registry completo
    # ─────────────────────────────────────────────────────────────────────

    async def replace_registry(self, new_registry: SlotRegistry) -> None:
        """Reemplaza el registry entero.

        Usado cuando el trader cambia múltiples slots en una misma
        edición: el frontend re-serializa el JSON, el backend hace
        `load_registry()` nuevo y lo inyecta acá.

        **Reset de warmup:** el overlay se limpia — los slots recién
        cargados pasarán por el warmup normal del scan loop según
        corresponda (scope SR.2).

        **No persiste a disco** — asume que el caller ya escribió el
        archivo antes de pasar el `new_registry` (el flujo típico es
        frontend PUT → file write → `load_registry()` → `replace_registry()`).
        """
        async with self._lock:
            self._registry = new_registry
            self._warming.clear()

    async def disable_slot(self, slot_id: int) -> bool:
        """Marca el slot como `DISABLED` en memoria y persiste a disco.

        Si el runtime fue construido con `registry_path=`, escribe el
        registry actualizado de forma atómica. Si la escritura falla,
        el cambio in-memory se revierte (fail-fast) y se propaga la
        excepción — garantiza consistencia disco/memoria.

        Returns:
            `True` si el slot existía y cambió. `False` si no existe.
        """
        async with self._lock:
            for i, s in enumerate(self._registry.slots):
                if s.slot != slot_id:
                    continue
                new_slot = SlotRecord(
                    slot=s.slot,
                    status="DISABLED",
                    ticker=None,
                    fixture_path=None,
                    fixture=None,
                    benchmark=None,
                    priority=s.priority,
                    notes=s.notes,
                    error_code=None,
                    error_detail=None,
                )
                new_slots = list(self._registry.slots)
                new_slots[i] = new_slot
                prev_registry = self._registry
                prev_warming = set(self._warming)
                self._registry = SlotRegistry(
                    metadata=prev_registry.metadata,
                    slots=new_slots,
                    warnings=prev_registry.warnings,
                )
                self._warming.discard(slot_id)
                if self._registry_path is not None:
                    try:
                        save_registry(self._registry, self._registry_path)
                    except OSError:
                        # Rollback: la memoria vuelve al estado anterior
                        # y propagamos el error al caller.
                        self._registry = prev_registry
                        self._warming = prev_warming
                        logger.exception(
                            f"disable_slot({slot_id}): failed to persist "
                            f"registry to {self._registry_path}. "
                            "In-memory change rolled back.",
                        )
                        raise
                return True
            return False

    # ─────────────────────────────────────────────────────────────────────
    # Introspección (NO acquire lock — solo para uso interno)
    # ─────────────────────────────────────────────────────────────────────

    def _serialize(self, rec: SlotRecord) -> dict[str, Any]:
        return {
            "slot": rec.slot,
            "ticker": rec.ticker,
            "fixture_path": rec.fixture_path,
            "fixture_id": (
                rec.fixture.metadata.fixture_id if rec.fixture is not None else None
            ),
            "benchmark": rec.benchmark,
            "base_state": rec.status,
            "status": self._effective_status(rec),
            "error_code": rec.error_code,
            "error_detail": rec.error_detail,
        }

    def _effective_status(self, rec: SlotRecord) -> SlotRuntimeStatus:
        if rec.status == "DISABLED":
            return "disabled"
        if rec.status == "DEGRADED":
            return "degraded"
        if rec.slot in self._warming:
            return "warming_up"
        return "active"
