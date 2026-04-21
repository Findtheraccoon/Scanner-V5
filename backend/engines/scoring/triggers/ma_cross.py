"""Cruce alcista/bajista MA20/40 1H — 2 triggers del total de 14.

Port literal de scanner_v4.2.1.html líneas 440-447.

Compara la posición actual de MA20 vs MA40 contra la de 2 velas atrás
en el timeframe 1H. Si cruzó desde abajo → alcista; desde arriba →
bajista.

Reglas exactas (v4.2.1):

    Necesita >= 42 velas 1H (40 para warmup de MA40 + 2 para prev).

    m20_curr = SMA(closes_1h, 20) al final
    m40_curr = SMA(closes_1h, 40) al final
    m20_prev = SMA(closes_1h[:-2], 20) al final
    m40_prev = SMA(closes_1h[:-2], 40) al final

    Alcista:  m20_prev < m40_prev  AND  m20_curr > m40_curr
              → CALL w=2.0

    Bajista:  m20_prev > m40_prev  AND  m20_curr < m40_curr
              → PUT  w=2.0

Notar el strict `<` / `>` — empates exactos no disparan cruce. Port
literal (los empates exactos en floats son prácticamente imposibles en
series reales).
"""

from __future__ import annotations

from engines.scoring.indicators import sma

_WEIGHT_MA_CROSS: float = 2.0
_MA_SHORT: int = 20
_MA_LONG: int = 40
_MIN_CANDLES: int = 42  # 40 warmup + 2 prev offset
_PREV_OFFSET: int = 2


def detect_ma_cross_1h(candles_1h: list[dict]) -> list[dict]:
    """Detecta cruce de MA20/40 en 1H.

    Args:
        candles_1h: velas 1H antigua→reciente. Mínimo 42.

    Returns:
        Lista con 0 o 1 `TriggerDict`. Alcista y bajista son
        mutuamente excluyentes — si ocurrió cruce, fue en una sola
        dirección.
    """
    if len(candles_1h) < _MIN_CANDLES:
        return []

    closes = [c["c"] for c in candles_1h]

    m20_curr_series = sma(closes, _MA_SHORT)
    m40_curr_series = sma(closes, _MA_LONG)
    m20_curr = m20_curr_series[-1]
    m40_curr = m40_curr_series[-1]

    prev_closes = closes[:-_PREV_OFFSET]
    m20_prev_series = sma(prev_closes, _MA_SHORT)
    m40_prev_series = sma(prev_closes, _MA_LONG)
    m20_prev = m20_prev_series[-1]
    m40_prev = m40_prev_series[-1]

    if any(v is None for v in (m20_curr, m40_curr, m20_prev, m40_prev)):
        return []

    triggers: list[dict] = []
    if m20_prev < m40_prev and m20_curr > m40_curr:
        triggers.append(
            {
                "tf": "1H",
                "d": "Cruce alcista MA20/40",
                "sg": "CALL",
                "w": _WEIGHT_MA_CROSS,
                "cat": "TRIGGER",
                "age": 0,
            }
        )
    if m20_prev > m40_prev and m20_curr < m40_curr:
        triggers.append(
            {
                "tf": "1H",
                "d": "Cruce bajista MA20/40",
                "sg": "PUT",
                "w": _WEIGHT_MA_CROSS,
                "cat": "TRIGGER",
                "age": 0,
            }
        )
    return triggers
