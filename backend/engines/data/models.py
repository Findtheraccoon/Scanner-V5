"""Modelos de datos del Data Engine.

Tipos Pydantic que viajan entre Data Engine ↔ Scoring ↔ persistencia ↔ API.

- `Candle` es el formato canónico de vela (compatible con el contrato del
  Scoring Engine §2.2).
- `ApiKeyConfig` es lo que el Config del usuario aporta (persistido
  encriptado).
- `ApiKeyState` es el estado runtime de una key — nunca se persiste.
- `EngineStatus` y `SlotStatus` son los enum que viajan en los eventos
  WebSocket `engine.status` y `slot.status`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt

# ═══════════════════════════════════════════════════════════════════════════
# Enumerations
# ═══════════════════════════════════════════════════════════════════════════


class Timeframe(StrEnum):
    """Timeframes soportados por el scanner."""

    DAILY = "daily"
    H1 = "1h"
    M15 = "15m"


class EngineStatus(StrEnum):
    """Estados válidos de un motor vivo.

    OFF      — no arrancado o detenido explícitamente
    STARTING — en proceso de arranque (warmup, validación)
    RUNNING  — operativo, sirviendo ciclos
    DEGRADED — operativo pero con problemas (provider intermitente, etc.)
    STOPPING — en proceso de shutdown graceful
    """

    OFF = "off"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"


class SlotStatus(StrEnum):
    """Estados válidos de un slot del Slot Registry.

    WARMUP   — descargando datos históricos, aún no operativo
    ACTIVE   — operativo, recibe señales en cada ciclo
    DEGRADED — problemas específicos del slot (ticker sin datos, hash
               canonical desincronizado, fixture inválida)
    OFF      — desactivado explícitamente por el trader
    """

    WARMUP = "warmup"
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFF = "off"


# ═══════════════════════════════════════════════════════════════════════════
# Vela (Candle)
# ═══════════════════════════════════════════════════════════════════════════


class Candle(BaseModel):
    """Una vela OHLCV.

    Coincide con el formato que consume `analyze()` del Scoring Engine:
    `{"dt": "YYYY-MM-DD HH:MM:SS", "o": ..., "h": ..., "l": ..., "c": ..., "v": ...}`.

    El campo `dt` es tz-aware en ET (ADR-0002). La serialización a JSON
    produce el formato string "YYYY-MM-DD HH:MM:SS" sin tzinfo porque el
    Scoring Engine espera ese formato.
    """

    model_config = ConfigDict(frozen=True)

    dt: datetime = Field(description="Timestamp tz-aware en ET (ADR-0002)")
    o: float = Field(description="Open")
    h: float = Field(description="High")
    l: float = Field(description="Low")  # noqa: E741 — mantenemos nombres cortos del spec
    c: float = Field(description="Close")
    v: NonNegativeInt = Field(description="Volume")


# ═══════════════════════════════════════════════════════════════════════════
# API Keys — configuración + estado
# ═══════════════════════════════════════════════════════════════════════════


class ApiKeyConfig(BaseModel):
    """Configuración de una API key del Config del usuario.

    Vive encriptado en el Config JSON (ADR-0001 describe el patrón de
    encriptación). El Data Engine recibe estos objetos ya desencriptados.
    """

    model_config = ConfigDict(frozen=True)

    key_id: str = Field(
        description=(
            "Identificador opaco de la key (ej. 'key_1', 'key_2'). Nunca "
            "se expone el secreto en logs ni en eventos WebSocket — solo "
            "el key_id."
        )
    )
    secret: str = Field(
        description=(
            "Token real a enviar a Twelve Data. Sensible: no loguear, no "
            "serializar fuera del Config encriptado."
        )
    )
    credits_per_minute: PositiveInt = Field(
        description="Cupo declarado de créditos/min de esta key."
    )
    credits_per_day: PositiveInt = Field(description="Cupo declarado de créditos/día de esta key.")
    enabled: bool = Field(
        default=True,
        description="Si false, la key existe en Config pero no participa del pool.",
    )


class ApiKeyState(BaseModel):
    """Estado runtime de una API key.

    Se emite en el evento WebSocket `api_usage.tick` para alimentar el
    banner de 5 barras del Cockpit. Nunca se persiste en DB.
    """

    key_id: str
    used_minute: NonNegativeInt = 0
    max_minute: PositiveInt
    used_daily: NonNegativeInt = 0
    max_daily: PositiveInt
    last_call_ts: datetime | None = Field(
        default=None,
        description="Timestamp tz-aware en ET de la última llamada exitosa.",
    )
    exhausted: bool = Field(
        default=False,
        description=(
            "True si la key agotó cupo diario. Se resetea al cierre de "
            "mercado ET (no a medianoche UTC)."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Resultado de verificación de integridad
# ═══════════════════════════════════════════════════════════════════════════


class IntegrityResult(BaseModel):
    """Resultado de `check_integrity()` sobre una lista de velas.

    Es estructural: verifica orden, duplicados, OHLC válido, tz-awareness,
    y cuenta mínima. No verifica staleness (frescura) ni gaps entre
    sesiones — eso requiere market calendar y es responsabilidad del
    caller si le interesa.

    `notes` acumula TODOS los issues encontrados (no solo el primero)
    para dar diagnóstico completo al chat de desarrollo y a los logs.
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    notes: list[str] = Field(default_factory=list)
    checked_count: NonNegativeInt = Field(description="Cantidad de velas examinadas")
    timeframe: Timeframe


# ═══════════════════════════════════════════════════════════════════════════
# Resultados de fetch
# ═══════════════════════════════════════════════════════════════════════════


class FetchResult(BaseModel):
    """Resultado de un fetch de velas al provider.

    El Data Engine nunca devuelve velas con `integrity_ok=False` al Scoring
    Engine (invariante 1 del motor en `backend/engines/data/README.md`).
    """

    model_config = ConfigDict(frozen=True)

    ticker: str
    timeframe: Timeframe
    candles: list[Candle]
    integrity_ok: bool
    integrity_notes: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(description="Timestamp tz-aware ET del fetch")
    used_key_id: str | None = Field(
        default=None,
        description="key_id usada; None si el fetch se resolvió enteramente desde DB local.",
    )


__all__ = [
    "ApiKeyConfig",
    "ApiKeyState",
    "Candle",
    "EngineStatus",
    "FetchResult",
    "IntegrityResult",
    "SlotStatus",
    "Timeframe",
]
