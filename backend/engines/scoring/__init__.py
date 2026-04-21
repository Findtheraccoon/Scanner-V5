"""Scoring Engine v5.2.0 — motor puro plug-and-play.

API pública:

    - `analyze(ticker, candles_daily, candles_1h, candles_15m, fixture, ...)`
      → dict con el output estructurado (spec §2.3).
    - `ENGINE_VERSION` (str)
    - Códigos `ENG-XXX` (constants)

Ver `docs/specs/SCORING_ENGINE_SPEC.md` para el contrato formal y las
5 invariantes del motor.

**Estado:** Fase 1 — contrato + validación de entrada. Las fases 2-6
(indicadores, alignment, 14 triggers, 10 confirms, gates) se agregan
en commits sucesivos sin cambiar la firma pública.
"""

from engines.scoring.analyze import analyze
from engines.scoring.constants import (
    ENG_001,
    ENG_010,
    ENG_020,
    ENG_050,
    ENG_060,
    ENG_099,
    ENGINE_VERSION,
    FIXTURE_COMPAT_RANGE,
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
)

__all__ = [
    "ENGINE_VERSION",
    "ENG_001",
    "ENG_010",
    "ENG_020",
    "ENG_050",
    "ENG_060",
    "ENG_099",
    "FIXTURE_COMPAT_RANGE",
    "MIN_CANDLES_1H",
    "MIN_CANDLES_15M",
    "MIN_CANDLES_DAILY",
    "analyze",
]
