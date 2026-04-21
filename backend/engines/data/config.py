"""Configuración tipada del Data Engine.

Distinto de `backend/modules/config/` — ese módulo se encarga de cargar,
encriptar y persistir el Config JSON completo del usuario. Acá definimos
solo el subset que el motor necesita al arrancar, ya validado y
desencriptado.

`DataEngineConfig` es el contrato entre quien instancia el motor (el
orquestador del backend) y el motor. Strict — `extra="forbid"` atrapa
typos de campo; frozen — inmutable tras construcción.

Los defaults vienen de `engines/data/constants.py`, que a su vez
derivan de FEATURE_DECISIONS §3.1 y los ADRs 0003-0004. Se pueden
overridear desde el Config del usuario por campo individual.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, PositiveInt, model_validator

from engines.data.constants import (
    AUTO_CYCLE_DELAY_AFTER_CLOSE_S,
    ENG_060_CYCLES_THRESHOLD,
    MAX_API_KEYS,
    RETRY_SHORT_DELAY_S,
    WARMUP_1H_N,
    WARMUP_15M_N,
    WARMUP_DAILY_N,
)
from engines.data.models import ApiKeyConfig


class DataEngineConfig(BaseModel):
    """Configuración del Data Engine recibida al `start()`.

    Invariantes validadas al construir:

    - Al menos 1 key en `api_keys`, y al menos 1 con `enabled=True`.
    - Sin duplicados de `key_id`.
    - No más de `MAX_API_KEYS` (5) keys totales.

    El resto de validaciones (rangos positivos, tipos correctos) las
    aplica Pydantic automáticamente via `PositiveInt` / `PositiveFloat`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # ─────────────────────────────────────────────────────────────────────
    # API keys del provider
    # ─────────────────────────────────────────────────────────────────────
    api_keys: list[ApiKeyConfig] = Field(
        description=(
            "Lista de API keys ya desencriptadas. 1 ≤ len ≤ MAX_API_KEYS. "
            "Al menos una debe tener enabled=True."
        ),
    )

    # ─────────────────────────────────────────────────────────────────────
    # Warmup por timeframe (FEATURE_DECISIONS §3.1)
    # ─────────────────────────────────────────────────────────────────────
    warmup_daily_n: PositiveInt = Field(
        default=WARMUP_DAILY_N,
        description="Cantidad total de velas daily que el motor necesita en DB + buffer.",
    )
    warmup_1h_n: PositiveInt = Field(
        default=WARMUP_1H_N,
        description="Cantidad total de velas 1H.",
    )
    warmup_15m_n: PositiveInt = Field(
        default=WARMUP_15M_N,
        description="Cantidad total de velas 15M.",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Retry policy (ADR-0004)
    # ─────────────────────────────────────────────────────────────────────
    retry_short_delay_s: PositiveFloat = Field(
        default=RETRY_SHORT_DELAY_S,
        description="Delay corto entre retry dentro del mismo ciclo.",
    )
    eng_060_cycles_threshold: PositiveInt = Field(
        default=ENG_060_CYCLES_THRESHOLD,
        description=(
            "Ciclos consecutivos sin datos de un ticker antes de marcar "
            "el slot como DEGRADED con ENG-060."
        ),
    )

    # ─────────────────────────────────────────────────────────────────────
    # Ciclo AUTO (FEATURE_DECISIONS §3.1)
    # ─────────────────────────────────────────────────────────────────────
    auto_cycle_delay_after_close_s: PositiveFloat = Field(
        default=AUTO_CYCLE_DELAY_AFTER_CLOSE_S,
        description="Delay tras cierre de vela 15M ET antes de disparar el ciclo de fetch.",
    )

    # ─────────────────────────────────────────────────────────────────────
    # HTTP
    # ─────────────────────────────────────────────────────────────────────
    http_timeout_s: PositiveFloat = Field(
        default=10.0,
        description="Timeout por request al provider Twelve Data.",
    )

    # ─────────────────────────────────────────────────────────────────────
    # Validadores
    # ─────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _validate_api_keys(self) -> DataEngineConfig:
        if not self.api_keys:
            raise ValueError("DataEngineConfig requires at least one api_key")
        if len(self.api_keys) > MAX_API_KEYS:
            raise ValueError(
                f"DataEngineConfig admits at most {MAX_API_KEYS} api_keys "
                f"(got {len(self.api_keys)})"
            )
        seen: set[str] = set()
        for k in self.api_keys:
            if k.key_id in seen:
                raise ValueError(f"DataEngineConfig has duplicate key_id: {k.key_id!r}")
            seen.add(k.key_id)
        if not any(k.enabled for k in self.api_keys):
            raise ValueError("DataEngineConfig requires at least one enabled api_key")
        return self
