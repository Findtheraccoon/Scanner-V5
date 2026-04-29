"""KeyPool — gestor de hasta 5 API keys con round-robin proporcional.

Implementa la estrategia validada en producción por el scanner v4.2.1
durante 3 años (ver referencia conceptual en `scanner_v4.2.1.html`):

- **Round-robin proporcional** a `credits_per_minute` declarado por key:
  una key con cupo 8/min sirve el doble de llamadas que una con cupo 4/min
  en el mismo intervalo.
- **Redistribución dinámica** si una key agota cupo diario: el tráfico se
  reparte proporcionalmente entre las restantes hasta el próximo reset.
- **Reset diario al cierre de mercado ET** (no medianoche UTC), por decisión
  de producto en FEATURE_DECISIONS §3.1. `KeyPool` solo expone el método
  `reset_daily()`; el scheduling lo hace el Data Engine.
- **Wipe de secretos en memoria al shutdown** (wipe obligatorio por política
  de seguridad, implementado como best-effort — Python no garantiza borrado
  físico de strings en memoria).

Algoritmo de pick proporcional (determinístico):

    Entre las keys elegibles (enabled, no exhausted, used_minute < cpm),
    se elige la que minimiza la tupla:

        (used_minute / credits_per_minute,
         used_daily  / credits_per_day,
         key_id)

    Esto garantiza que una key con cupo 8/min reciba el doble de llamadas
    que una con cupo 4/min en un mismo minuto: la primera llena su cupo
    más lentamente (mismo `used_minute` es una fracción menor), por lo
    que se elige más veces hasta equiparar fracciones.

    Si una key se agota (daily), queda fuera del conjunto elegible y la
    distribución proporcional se recalcula implícitamente sobre las
    restantes — no hace falta recomputar pesos manualmente.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta

from engines.data.constants import ET, MAX_API_KEYS
from engines.data.models import ApiKeyConfig, ApiKeyState


@dataclass
class _KeyEntry:
    """Estado interno mutable de una key del pool.

    Separado de `ApiKeyConfig` (que es frozen) para permitir wipe del
    secreto al shutdown y mutación de contadores en caliente.
    """

    key_id: str
    secret: str
    credits_per_minute: int
    credits_per_day: int
    enabled: bool
    used_minute: int = 0
    used_daily: int = 0
    last_call_ts: datetime | None = None
    exhausted: bool = False


class KeyPool:
    """Pool de API keys con round-robin proporcional y reset diario ET.

    Lifecycle::

        pool = KeyPool(keys)
        key = await pool.acquire()
        try:
            result = await provider_call(key.secret, ...)
            pool.release(key.key_id, credits_used=1, success=True)
        except DailyCapError:
            pool.mark_exhausted(key.key_id)
        pool.shutdown()

    Thread safety:
        El pool es async-safe (lock interno). No es thread-safe; asume
        single event loop, consistente con Uvicorn single-worker del stack.
    """

    def __init__(self, keys: list[ApiKeyConfig]) -> None:
        """Inicializa el pool con hasta `MAX_API_KEYS` keys configuradas.

        Args:
            keys: lista de configs (ya desencriptadas del Config del
                usuario). Keys con `enabled=False` se conservan para
                poder reactivarlas sin reinicio, pero quedan fuera del
                round-robin.

        Raises:
            ValueError: si `keys` está vacía, si hay `key_id` duplicado,
                o si se exceden `MAX_API_KEYS` keys.
        """
        if not keys:
            raise ValueError("KeyPool requires at least one ApiKeyConfig")
        if len(keys) > MAX_API_KEYS:
            raise ValueError(f"KeyPool admits at most {MAX_API_KEYS} keys (got {len(keys)})")
        seen_ids: set[str] = set()
        entries: dict[str, _KeyEntry] = {}
        for k in keys:
            if k.key_id in seen_ids:
                raise ValueError(f"Duplicate key_id in KeyPool: {k.key_id!r}")
            seen_ids.add(k.key_id)
            entries[k.key_id] = _KeyEntry(
                key_id=k.key_id,
                secret=k.secret,
                credits_per_minute=k.credits_per_minute,
                credits_per_day=k.credits_per_day,
                enabled=k.enabled,
            )
        self._entries: dict[str, _KeyEntry] = entries
        self._minute_bucket: datetime | None = None
        self._lock = asyncio.Lock()
        self._shutdown: bool = False

    # ─────────────────────────────────────────────────────────────────────
    # Acquire / release
    # ─────────────────────────────────────────────────────────────────────

    async def acquire(self) -> ApiKeyConfig:
        """Cede la próxima key del round-robin proporcional.

        Bloquea (async) si todas las keys habilitadas están a tope de
        cupo/minuto, esperando al próximo minute rollover. Si todas las
        keys habilitadas agotaron cupo diario, lanza `KeyPoolExhaustedError`.

        Returns:
            `ApiKeyConfig` a usar para la próxima llamada al provider. Se
            reserva 1 crédito preventivamente para evitar double-pick bajo
            concurrencia; `release()` corrige el costo real al finalizar.

        Raises:
            KeyPoolExhaustedError: todas las keys agotaron cupo diario.
            RuntimeError: el pool ya fue shutdown.
        """
        while True:
            async with self._lock:
                if self._shutdown:
                    raise RuntimeError("KeyPool has been shut down")
                self._rollover_if_needed()
                eligible = self._eligible_entries()
                if eligible:
                    chosen = self._pick_proportional(eligible)
                    chosen.used_minute += 1
                    return self._to_config(chosen)
                if self._all_enabled_daily_exhausted():
                    raise KeyPoolExhaustedError("all enabled keys have exhausted their daily quota")
                wait_s = self._seconds_to_next_minute()
            await asyncio.sleep(wait_s)

    def release(
        self,
        key_id: str,
        credits_used: int = 1,
        *,
        success: bool = True,
    ) -> None:
        """Registra el consumo tras una llamada al provider.

        `acquire()` reserva 1 crédito/min preventivamente. Acá corregimos:

        - Sumamos `(credits_used - 1)` a `used_minute` (ajuste sobre la
          reserva). Si el fetch nunca llegó al provider (`credits_used=0`),
          esto desreserva el crédito.
        - Sumamos `credits_used` a `used_daily`.
        - Si `success=True`, actualizamos `last_call_ts`.

        Si `key_id` no existe, el llamado es no-op (defensivo — el caller
        podría estar reportando sobre una key removida entre acquire y
        release, aunque en nuestra arquitectura eso no debería pasar).

        Args:
            key_id: identificador de la key usada.
            credits_used: costo real de la llamada en créditos.
            success: si False, la llamada falló — no se actualiza
                `last_call_ts` pero sí se descuentan los créditos
                consumidos en provider (credits_used puede ser 0 si el
                fallo fue antes de enviar la request).
        """
        if credits_used < 0:
            raise ValueError("credits_used must be >= 0")
        entry = self._entries.get(key_id)
        if entry is None:
            return
        entry.used_minute = max(0, entry.used_minute + (credits_used - 1))
        entry.used_daily += credits_used
        if success:
            entry.last_call_ts = datetime.now(tz=ET)

    def mark_exhausted(self, key_id: str) -> None:
        """Marca una key como agotada para cupo diario.

        Típicamente invocado cuando el provider devuelve 429 o un error
        explícito de cupo diario excedido. La key queda fuera del
        conjunto elegible hasta el próximo `reset_daily()`. La
        redistribución del tráfico sobre las restantes es implícita (la
        key deja de ser elegible; el picker proporcional recalcula
        solo).
        """
        entry = self._entries.get(key_id)
        if entry is None:
            return
        entry.exhausted = True

    def redistribute_on_exhaustion(self) -> None:
        """No-op — la redistribución es implícita.

        Se conserva el método por claridad del contrato original y por
        si a futuro se agrega pre-cómputo cacheado. Hoy, como el picker
        `_pick_proportional` filtra por elegibilidad en cada acquire, una
        key marcada exhausted queda automáticamente fuera del reparto y
        la proporcionalidad se mantiene entre las restantes.
        """
        return

    # ─────────────────────────────────────────────────────────────────────
    # Mantenimiento
    # ─────────────────────────────────────────────────────────────────────

    def reset_daily(self) -> None:
        """Resetea `used_daily`, `exhausted` y `last_call_ts` de todas las keys.

        Llamado por un job del Data Engine al cierre de mercado ET
        (FEATURE_DECISIONS §3.1). No toca `used_minute` — ese se resetea
        implícitamente por minute rollover en el próximo `acquire()`.
        """
        for entry in self._entries.values():
            entry.used_daily = 0
            entry.exhausted = False
            entry.last_call_ts = None

    def snapshot(self) -> list[ApiKeyState]:
        """Estado actual de todas las keys para el evento `api_usage.tick`.

        Devuelve una lista en el mismo orden de inserción que el Config.
        No incluye `secret` — `ApiKeyState` no tiene ese campo por diseño.
        """
        # Rollover pasivo: si cambió el minuto desde la última vez, el
        # snapshot debe reflejar used_minute=0. No tocamos lock porque el
        # snapshot es lectura y tolera una carrera benigna con acquire().
        self._rollover_if_needed()
        return [
            ApiKeyState(
                key_id=e.key_id,
                used_minute=e.used_minute,
                max_minute=e.credits_per_minute,
                used_daily=e.used_daily,
                max_daily=e.credits_per_day,
                last_call_ts=e.last_call_ts,
                exhausted=e.exhausted,
            )
            for e in self._entries.values()
        ]

    async def reload(self, keys: list[ApiKeyConfig]) -> None:
        """Hot-reload de las keys del pool sin reiniciar el backend.

        Reemplaza la configuración de keys preservando los contadores
        runtime (`used_minute`, `used_daily`, `last_call_ts`,
        `exhausted`) de las keys cuyo `key_id` siga en el set nuevo.
        Las keys nuevas arrancan con contadores en cero. Las
        eliminadas hacen wipe best-effort del `secret`.

        Validaciones idénticas a `__init__`: lista no vacía, máximo
        `MAX_API_KEYS`, `key_id` únicos.

        Raises:
            ValueError: si el input no cumple las validaciones.
            RuntimeError: si el pool ya fue shutdown.
        """
        if not keys:
            raise ValueError("reload requires at least one ApiKeyConfig")
        if len(keys) > MAX_API_KEYS:
            raise ValueError(
                f"KeyPool admits at most {MAX_API_KEYS} keys (got {len(keys)})",
            )
        seen: set[str] = set()
        for k in keys:
            if k.key_id in seen:
                raise ValueError(f"Duplicate key_id in reload: {k.key_id!r}")
            seen.add(k.key_id)

        async with self._lock:
            if self._shutdown:
                raise RuntimeError("KeyPool has been shut down")
            new_entries: dict[str, _KeyEntry] = {}
            for k in keys:
                existing = self._entries.get(k.key_id)
                new_entries[k.key_id] = _KeyEntry(
                    key_id=k.key_id,
                    secret=k.secret,
                    credits_per_minute=k.credits_per_minute,
                    credits_per_day=k.credits_per_day,
                    enabled=k.enabled,
                    used_minute=existing.used_minute if existing else 0,
                    used_daily=existing.used_daily if existing else 0,
                    last_call_ts=existing.last_call_ts if existing else None,
                    exhausted=existing.exhausted if existing else False,
                )
            for old_id, entry in self._entries.items():
                if old_id not in new_entries:
                    entry.secret = ""
            self._entries = new_entries

    def shutdown(self) -> None:
        """Wipe best-effort de secretos en memoria. Idempotente.

        Python no permite wipe físico de strings (son inmutables e
        internadas). Esto sobreescribe la referencia interna del
        `_KeyEntry.secret` con una cadena vacía para que, tras el
        shutdown, no quede ninguna referencia viva desde el pool al
        secreto original. Cualquier `ApiKeyConfig` devuelto previamente
        por `acquire()` sigue siendo responsabilidad del caller.

        Tras shutdown, `acquire()` levanta `RuntimeError`.
        """
        if self._shutdown:
            return
        for entry in self._entries.values():
            entry.secret = ""
        self._shutdown = True

    # ─────────────────────────────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────────────────────────────

    def _rollover_if_needed(self) -> None:
        now = datetime.now(tz=ET)
        current_bucket = now.replace(second=0, microsecond=0)
        if self._minute_bucket != current_bucket:
            for entry in self._entries.values():
                entry.used_minute = 0
            self._minute_bucket = current_bucket

    def _eligible_entries(self) -> list[_KeyEntry]:
        return [
            e
            for e in self._entries.values()
            if e.enabled and not e.exhausted and e.used_minute < e.credits_per_minute
        ]

    def _all_enabled_daily_exhausted(self) -> bool:
        enabled = [e for e in self._entries.values() if e.enabled]
        if not enabled:
            return True
        return all(e.exhausted for e in enabled)

    @staticmethod
    def _pick_proportional(eligible: list[_KeyEntry]) -> _KeyEntry:
        def score(e: _KeyEntry) -> tuple[float, float, str]:
            return (
                e.used_minute / e.credits_per_minute,
                e.used_daily / e.credits_per_day,
                e.key_id,
            )

        return min(eligible, key=score)

    @staticmethod
    def _seconds_to_next_minute() -> float:
        now = datetime.now(tz=ET)
        next_minute = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        return max(0.01, (next_minute - now).total_seconds())

    @staticmethod
    def _to_config(entry: _KeyEntry) -> ApiKeyConfig:
        return ApiKeyConfig(
            key_id=entry.key_id,
            secret=entry.secret,
            credits_per_minute=entry.credits_per_minute,
            credits_per_day=entry.credits_per_day,
            enabled=entry.enabled,
        )


class KeyPoolExhaustedError(Exception):
    """Todas las keys habilitadas agotaron cupo diario.

    Solo se lanza desde `KeyPool.acquire()`. El caller debe manejarlo en
    su retry loop y, si persiste, elevar `ENG-060` al slot afectado.
    """
