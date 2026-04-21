"""Subpaquete de detección de triggers del Scoring Engine (Fase 4).

Portado desde `scanner_v4.2.1.html` función `detect()`. Cada trigger
produce un `TriggerDict` con la forma canónica:

    {"tf", "d", "sg", "w", "cat": "TRIGGER", "age"}

El motor agrega estos a `analyze()["patterns"]` y aplica el trigger
gate (spec §3 I5 item 2) + conflict gate (item 3) en fases siguientes.

**Cobertura actual (Fase 4c):** 14 de 14 triggers detectores listos.

    Candle-level 15M (Fase 4a):
      - Doji BB sup / inf        (age=0, BB-dependientes)
      - Hammer                   (age=0, BB-dependiente)
      - Shooting Star            (age=0, BB-dependiente)
      - Rechazo sup / inf        (cualquier age, con decay)

    Multi-candle (Fase 4b):
      - Envolvente alcista/bajista 1H   (curr vs prev 1H, no decay)
      - Doble techo / Doble piso        (pivots en últimas 20 velas 15M)

    Indicadores + time gate (Fase 4c):
      - Cruce alcista/bajista MA20/40 (1H)
      - ORB breakout / breakdown       (≤ 10:30 ET + volume gate volM ≥ 1.0
                                         como gate binario, paridad con
                                         Observatory engine.py)

Pendiente (Fase 4d):

    - Integración en `analyze()` con el trigger gate (spec §3 I5 item 2)
    - Conflict gate (item 3) sigue en Fase 6
"""

from engines.scoring.triggers._helpers import (
    TriggerDict,
    age_label,
    candle_body,
    candle_range,
    decay_weight,
    is_bull,
    lower_wick,
    upper_wick,
)
from engines.scoring.triggers.candle_15m import detect_candle_15m_triggers
from engines.scoring.triggers.double import detect_double_patterns_15m
from engines.scoring.triggers.envolvente import detect_engulfing_1h
from engines.scoring.triggers.ma_cross import detect_ma_cross_1h
from engines.scoring.triggers.orb import compute_orb_levels, detect_orb_triggers_15m

__all__ = [
    "TriggerDict",
    "age_label",
    "candle_body",
    "candle_range",
    "compute_orb_levels",
    "decay_weight",
    "detect_candle_15m_triggers",
    "detect_double_patterns_15m",
    "detect_engulfing_1h",
    "detect_ma_cross_1h",
    "detect_orb_triggers_15m",
    "is_bull",
    "lower_wick",
    "upper_wick",
]
