"""Bollinger Bands.

Convención canónica de J. Bollinger:

    middle = SMA(n)
    stdev  = population std deviation (divisor n)
    upper  = middle + k * stdev
    lower  = middle - k * stdev

Valores estándar: n=20, k=2.0. El scanner usa estos por default pero
acepta override para experimentar.

**Rounding a 2 decimales** en middle/upper/lower — paridad con
Observatory `indicators.py:bb()`.
"""

from __future__ import annotations

from statistics import pstdev


def bollinger_bands(
    values: list[float],
    window: int = 20,
    k: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Calcula Bollinger Bands. Devuelve (lower, middle, upper).

    Args:
        values: serie numérica (típicamente closes).
        window: ventana de la SMA/stdev (≥ 2).
        k: multiplicador de stdev (> 0). Default 2.0.

    Returns:
        Tupla de 3 listas del mismo largo que `values`. Antes de warmup
        (índice < window - 1), todas son `None`.

    Raises:
        ValueError: `window < 2` o `k <= 0`.
    """
    if window < 2:
        raise ValueError(f"window must be >= 2 (got {window})")
    if k <= 0:
        raise ValueError(f"k must be > 0 (got {k})")
    n = len(values)
    lower: list[float | None] = [None] * n
    middle: list[float | None] = [None] * n
    upper: list[float | None] = [None] * n
    if n < window:
        return lower, middle, upper
    for i in range(window - 1, n):
        win = values[i - window + 1 : i + 1]
        m = sum(win) / window
        sd = pstdev(win)
        middle[i] = round(m, 2)
        upper[i] = round(m + k * sd, 2)
        lower[i] = round(m - k * sd, 2)
    return lower, middle, upper


def bb_width_normalized(
    lower: list[float | None],
    middle: list[float | None],
    upper: list[float | None],
) -> list[float | None]:
    """Ancho de banda **normalizado**: `(upper - lower) / middle`.

    Helper auxiliar (no Observatory) — devuelve serie escalar útil
    para visualizaciones o para análisis ad-hoc. Para detección de
    squeeze + expansión usar `bb_width()` (firma Observatory).

    Args:
        lower, middle, upper: series de salida de `bollinger_bands`.

    Returns:
        Lista de mismo largo. `None` donde alguna entrada es `None`
        o `middle <= 0`.
    """
    n = len(middle)
    result: list[float | None] = [None] * n
    for i in range(n):
        lo, mi, up = lower[i], middle[i], upper[i]
        if lo is None or mi is None or up is None or mi <= 0:
            continue
        result[i] = (up - lo) / mi
    return result


def _bb_width_at(values: list[float], period: int, k: float) -> float:
    """Ancho absoluto de BB en la ventana terminada en el último índice.

    Implementa la fórmula Observatory `bb()['w'] = round(2 * mult * st, 2)`
    sin pasar por `bollinger_bands()` (que redondea u/l antes y produce
    drift bit-a-bit en `u - l`). Asume `len(values) >= period`.
    """
    win = values[-period:]
    sd = pstdev(win)
    return round(2 * k * sd, 2)


def bb_width(
    values: list[float],
    period: int = 20,
    k: float = 2.0,
) -> dict | None:
    """Detección de **Squeeze → Expansión** vía percentil del ancho de BB.

    Port literal de Observatory `indicators.py:bb_width()` líneas 175-204.
    Devuelve un dict con metadata sobre el estado del squeeze, o `None`
    si no hay suficientes datos.

    Algoritmo:

    1. Para cada ventana terminada en `i ∈ [period, n]`, calcula
       `width = round(2 * k * stdev(values[i-period:i]), 2)`.
    2. Toma los últimos 20 widths.
    3. `percentile = (current - min20) / (max20 - min20) * 100` (entero).
    4. `isSqueeze` si `percentile < 15` (estricto).
    5. `isExpanding` si `widths[-3] < widths[-2] < widths[-1]`
       (3 lecturas estrictamente crecientes).

    Mínimo `period + 20` valores para devolver dict no-None.

    Args:
        values: serie numérica (típicamente closes).
        period: ventana de la SMA/stdev interna (default 20).
        k: multiplicador de stdev (default 2.0).

    Returns:
        Dict `{current, min20, percentile, isSqueeze, isExpanding}` o
        `None` si `len(values) < period + 20`.
    """
    if not values or len(values) < period + 20:
        return None
    widths: list[float] = []
    for i in range(period, len(values) + 1):
        widths.append(_bb_width_at(values[:i], period, k))
    if len(widths) < 20:
        return None
    current = widths[-1]
    last_20 = widths[-20:]
    min20 = min(last_20)
    max20 = max(last_20)
    rng = max20 - min20 or 1
    percentile = round((current - min20) / rng * 100)
    return {
        "current": round(current, 2),
        "min20": round(min20, 2),
        "percentile": percentile,
        "isSqueeze": percentile < 15,
        "isExpanding": (
            len(widths) >= 3
            and widths[-1] > widths[-2]
            and widths[-2] > widths[-3]
        ),
    }
