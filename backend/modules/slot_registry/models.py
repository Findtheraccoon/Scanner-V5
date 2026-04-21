"""Modelos Pydantic del slot registry.

Reflejan el schema v1.0.0 descrito en `docs/specs/SLOT_REGISTRY_SPEC.md`.
Inmutables tras construcción (`frozen=True`).

Diseño de `SlotRecord`:

    El registry reifica cada slot en un `SlotRecord` con un `status`
    derivado:

        OPERATIVE — validación completa OK, fixture parseada lista para
                    entregar al Scoring
        DEGRADED  — slot enabled pero con un problema específico
                    (archivo faltante, tipo incompatible, etc.). No se
                    corre en ese slot, pero los demás siguen
        DISABLED  — slot explícitamente desactivado por el trader

    Cuando `status=OPERATIVE`, `fixture` contiene el `Fixture` parseado.
    Cuando `DEGRADED`, `fixture=None` y `error_code`/`error_detail`
    describen la causa. Cuando `DISABLED`, `error_code=None`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from modules.fixtures import Fixture


class RegistryMetadata(BaseModel):
    """Bloque `registry_metadata`. Forward-compat con `extra="allow"`."""

    model_config = ConfigDict(frozen=True, extra="allow")

    registry_version: str = Field(description='Semver del schema (ej. "1.0.0").')
    engine_version_required: str = Field(
        description='Rango semver del motor requerido (ej. ">=5.2.0,<6.0.0").'
    )
    generated_at: datetime = Field(description="Timestamp UTC de generación (ISO 8601).")
    generated_by: str | None = Field(default=None)
    description: str | None = Field(default=None)
    notes: str | None = Field(default=None)


SlotState = Literal["OPERATIVE", "DEGRADED", "DISABLED"]


class SlotRecord(BaseModel):
    """Un slot del registry tras evaluación.

    Fields del input preservados tal cual, más `status` derivado y
    (si aplica) `error_code` / `error_detail`.
    """

    model_config = ConfigDict(frozen=True)

    slot: int = Field(ge=1, le=6)
    status: SlotState
    ticker: str | None
    fixture_path: str | None = Field(
        description="Path relativo al repo de la fixture del slot. None si disabled."
    )
    fixture: Fixture | None = Field(
        description="Fixture parseada. None si DEGRADED o DISABLED.",
    )
    benchmark: str | None
    priority: str | None = None
    notes: str | None = None
    error_code: str | None = Field(
        default=None,
        description="REG-XXX o FIX-XXX del problema. None si OPERATIVE o DISABLED.",
    )
    error_detail: str | None = None


class SlotRegistry(BaseModel):
    """Resultado de `load_registry()`.

    `slots` siempre tiene exactamente 6 elementos ordenados por `slot`
    (1 → 6). `warnings` acumula códigos no-fatales (ej. REG-101).
    """

    model_config = ConfigDict(frozen=True)

    metadata: RegistryMetadata
    slots: list[SlotRecord]
    warnings: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def operative_slots(self) -> list[SlotRecord]:
        return [s for s in self.slots if s.status == "OPERATIVE"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def degraded_slots(self) -> list[SlotRecord]:
        return [s for s in self.slots if s.status == "DEGRADED"]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def disabled_slots(self) -> list[SlotRecord]:
        return [s for s in self.slots if s.status == "DISABLED"]

    def ensure_at_least_one_operative(self) -> None:
        """Raise si 0 slots quedaron OPERATIVE (spec §8 final)."""
        from modules.slot_registry.errors import REG_003, RegistryError

        if not self.operative_slots:
            raise RegistryError(
                REG_003,
                "0 slots operativos — el scanner no puede arrancar. "
                "Revisar errores DEGRADED de cada slot.",
            )
