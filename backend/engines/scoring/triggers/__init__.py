"""Subpaquete de detección de triggers del Scoring Engine (Fase 4).

Portado desde `scanner_v4.2.1.html` función `detect()`. Cada trigger
produce un `TriggerDict` con la forma canónica:

    {"tf", "d", "sg", "w", "cat": "TRIGGER", "age"}

El motor agrega estos a `analyze()["patterns"]` y aplica el trigger
gate (spec §3 I5 item 2) + conflict gate (item 3) en fases siguientes.

**Cobertura actual (Fase 4a):** 6 de 14 triggers — los que operan
sobre vela individual en 15M:

    - Doji BB sup / inf        (age=0, BB-dependientes)
    - Hammer                   (age=0, BB-dependiente)
    - Shooting Star            (age=0, BB-dependiente)
    - Rechazo sup / inf        (cualquier age, con decay)

Pendientes (Fase 4b/c/d/e):

    - Envolvente alcista/bajista 1H
    - Doble techo / Doble piso (15M)
    - Cruce alcista/bajista MA20/40 (1H)
    - ORB breakout/breakdown (≤10:30 ET)
    - Integración en `analyze()` con el trigger gate
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

__all__ = [
    "TriggerDict",
    "age_label",
    "candle_body",
    "candle_range",
    "decay_weight",
    "detect_candle_15m_triggers",
    "is_bull",
    "lower_wick",
    "upper_wick",
]
