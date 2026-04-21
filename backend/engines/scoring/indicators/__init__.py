"""Indicadores técnicos del Scoring Engine (Fase 2).

API pública consumida por alignment (Fase 3), triggers (Fase 4) y
confirms (Fase 5). Todas las funciones son puras, sin estado, sin I/O.

Convenciones globales:

    - Listas devueltas tienen el mismo largo que la entrada; se
      rellenan con `None` donde no hay suficiente historia (warmup).
    - Las funciones `*_at(candles, index, ...)` devuelven un valor
      escalar en un índice específico o `None` si el índice no está
      listo todavía.
    - División por cero se protege devolviendo `None` — nunca se
      lanza la excepción.
    - Valores numéricos de entrada se asumen float/int válidos; la
      validación de integridad de la serie (OHLC coherente, no NaN,
      etc.) es responsabilidad del Data Engine (`check_integrity`).
"""

from engines.scoring.indicators.atr import atr, true_range
from engines.scoring.indicators.bollinger import (
    bb_width,
    bb_width_normalized,
    bollinger_bands,
)
from engines.scoring.indicators.moving_averages import ema, sma
from engines.scoring.indicators.volume import (
    gap_pct_at,
    is_volume_increasing,
    today_candles,
    vol_ratio_intraday,
    vol_sequence,
    volume_ratio_at,
)

__all__ = [
    "atr",
    "bb_width",
    "bb_width_normalized",
    "bollinger_bands",
    "ema",
    "gap_pct_at",
    "is_volume_increasing",
    "sma",
    "today_candles",
    "true_range",
    "vol_ratio_intraday",
    "vol_sequence",
    "volume_ratio_at",
]
