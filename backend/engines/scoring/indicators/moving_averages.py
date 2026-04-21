"""Medias móviles SMA y EMA.

Convenciones:

    - Listas de salida tienen **mismo largo** que la entrada. Los
      índices con warmup incompleto se rellenan con `None`.
    - `window` es el tamaño de ventana en número de observaciones (no
      tiempo). El caller decide qué cerrars usar (close, typical, etc.).
    - **EMA seeded with SMA**: sigue la convención de TradingView y la
      mayoría de algo libs — la primera EMA definida (índice
      `window - 1`) es la SMA de los primeros `window` valores. Desde
      allí se aplica la recurrencia `alpha * v + (1-alpha) * prev` con
      `alpha = 2 / (window + 1)`.

Sin try/except ni fallbacks: las funciones son puro math y lanzan
`ValueError` solo cuando el caller pasó parámetros sin sentido (window
no positivo). El Scoring Engine las envuelve en su propio try/except
catch-all (I3).
"""

from __future__ import annotations


def sma(values: list[float], window: int) -> list[float | None]:
    """Simple Moving Average de `values` sobre ventana `window`.

    Args:
        values: serie numérica (típicamente closes).
        window: tamaño de ventana (≥ 1).

    Returns:
        Lista del mismo largo que `values`. En índices `i < window - 1`
        el valor es `None`. Desde `window - 1` en adelante, el valor
        es `mean(values[i - window + 1 : i + 1])`.

    Raises:
        ValueError: si `window < 1`.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1 (got {window})")
    n = len(values)
    result: list[float | None] = [None] * n
    if n < window:
        return result
    # Cálculo vainilla — para series cortas del scanner no vale la pena
    # la sliding-window optimization.
    for i in range(window - 1, n):
        result[i] = sum(values[i - window + 1 : i + 1]) / window
    return result


def ema(values: list[float], window: int) -> list[float | None]:
    """Exponential Moving Average seeded con SMA.

    Args:
        values: serie numérica.
        window: tamaño de ventana (≥ 1).

    Returns:
        Lista del mismo largo que `values`. En índices `i < window - 1`
        el valor es `None`. Índice `window - 1` es la SMA de los
        primeros `window` valores. Desde `window` en adelante se aplica
        `alpha * values[i] + (1-alpha) * ema[i-1]` con `alpha = 2 / (window + 1)`.

    Raises:
        ValueError: si `window < 1`.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1 (got {window})")
    n = len(values)
    result: list[float | None] = [None] * n
    if n < window:
        return result
    seed = sum(values[:window]) / window
    result[window - 1] = seed
    alpha = 2.0 / (window + 1)
    prev = seed
    for i in range(window, n):
        curr = alpha * values[i] + (1.0 - alpha) * prev
        result[i] = curr
        prev = curr
    return result
