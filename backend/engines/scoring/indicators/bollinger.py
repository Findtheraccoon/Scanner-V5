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


def bb_width(
    lower: list[float | None],
    middle: list[float | None],
    upper: list[float | None],
) -> list[float | None]:
    """Ancho de banda normalizado: (upper - lower) / middle.

    Útil para detectar SqExp (squeeze → expansion) en la Fase 5. La
    compresión se ve como `bb_width` en mínimo relativo a ventanas
    anteriores; la expansión como aumento rápido.

    Args:
        lower, middle, upper: series de salida de `bollinger_bands`.

    Returns:
        Lista de mismo largo. `None` donde alguna de las tres entradas
        es `None` o `middle <= 0`.
    """
    n = len(middle)
    result: list[float | None] = [None] * n
    for i in range(n):
        lo, mi, up = lower[i], middle[i], upper[i]
        if lo is None or mi is None or up is None or mi <= 0:
            continue
        result[i] = (up - lo) / mi
    return result
