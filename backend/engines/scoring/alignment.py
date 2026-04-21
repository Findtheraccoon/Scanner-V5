"""Alignment gate — estructura del scoring (primer gate del pipeline).

Define la **dirección de tendencia** en cada timeframe y combina las
tres (15m / 1h / daily) en un score de alineación `(n, dir)`.

Regla del spec §3 I5:

    alignment_gate = (n >= 2 and dir != "flat")  [o catalyst override]

`catalyst override` es una puerta trasera del v4.2.1 para noticias
pre-market etc.; no implementada en este commit — se agrega cuando se
porte desde el HTML legacy.

Cálculo de trend por timeframe:

    1. Tomar los closes.
    2. Calcular SMA(ma_window). Default 20 — convención estándar.
    3. Comparar último close vs último SMA:
         close > sma  → "up"
         close < sma  → "down"
         close == sma → "flat"   (prácticamente imposible con floats)
    4. Si la serie es muy corta (< ma_window), devolver "flat".

Combinación:

    up_count   = trends.count("up")
    down_count = trends.count("down")
    - si up > down   → (up_count, "up")
    - si down > up   → (down_count, "down")
    - si empatan     → (trends.count("flat"), "flat")
"""

from __future__ import annotations

from typing import Literal

from engines.scoring.indicators import sma

Trend = Literal["up", "down", "flat"]
"""Tendencia direccional de un timeframe."""

AlignmentDir = Literal["up", "down", "flat"]
"""Dirección dominante tras agregar las 3 tendencias."""

DEFAULT_ALIGNMENT_MA_WINDOW: int = 20


def trend_for_timeframe(
    candles: list[dict],
    *,
    ma_window: int = DEFAULT_ALIGNMENT_MA_WINDOW,
) -> Trend:
    """Dirección del último close vs SMA de la misma ventana.

    Args:
        candles: lista de velas (dicts con `c`).
        ma_window: ventana de la SMA (≥ 1). Default 20.

    Returns:
        "up" si close > SMA, "down" si close < SMA, "flat" en empate
        exacto o si no hay suficientes velas para computar SMA.
    """
    if not candles or len(candles) < ma_window:
        return "flat"
    closes = [c["c"] for c in candles]
    sma_series = sma(closes, ma_window)
    latest_sma = sma_series[-1]
    if latest_sma is None:
        return "flat"
    latest_close = closes[-1]
    if latest_close > latest_sma:
        return "up"
    if latest_close < latest_sma:
        return "down"
    return "flat"


def compute_alignment(
    trend_15m: Trend,
    trend_1h: Trend,
    trend_daily: Trend,
) -> tuple[int, AlignmentDir]:
    """Combina 3 trends en `(alignment_n, alignment_dir)`.

    Args:
        trend_15m, trend_1h, trend_daily: tendencias por timeframe.

    Returns:
        Tupla `(n, dir)` donde:
            - `n` = cuenta de timeframes que apoyan la dirección
              dominante.
            - `dir` = "up"/"down" si hay mayoría clara, "flat" si empate.
    """
    trends: list[Trend] = [trend_15m, trend_1h, trend_daily]
    up = trends.count("up")
    down = trends.count("down")
    flat = trends.count("flat")
    if up > down:
        return up, "up"
    if down > up:
        return down, "down"
    return flat, "flat"


def alignment_gate_passes(n: int, direction: AlignmentDir) -> bool:
    """True si el alignment gate del spec §3 I5 se aprueba.

    Hoy: `n >= 2 and dir != "flat"`. El `catalyst override` queda
    pendiente hasta que se porte desde v4.2.1.
    """
    return n >= 2 and direction != "flat"
