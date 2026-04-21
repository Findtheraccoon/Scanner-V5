"""Average True Range (Wilder).

True Range de una vela con cierre previo `prev_close`:

    TR = max(h - l, |h - prev_close|, |l - prev_close|)

Para la primera vela del array (sin prev_close), `TR = h - l`.

ATR con **Wilder's smoothing** (el estándar):

    ATR[window - 1] = mean(TR[0..window])
    ATR[i]          = (ATR[i-1] * (window - 1) + TR[i]) / window    (i ≥ window)

Equivale a EMA con alpha = 1/window (no 2/(window+1) como la EMA clásica).
Wilder la formuló así originalmente para su RSI y ADR; todas las
plataformas que se precian lo respetan.

**Divergencia conocida con Observatory:** Observatory `indicators.py:atr()`
usa `mean(TR[-period:])` simple (no Wilder). Esta divergencia afecta
parity pero queda fuera del scope de Paso 6 (rounding); se aborda
en un commit separado si resulta necesario para el parity test.

**Rounding a 2 decimales** en el output — paridad con Observatory. La
recurrencia interna usa el valor sin redondear (`prev`) para no
acumular errores.
"""

from __future__ import annotations


def true_range(candle: dict, prev_close: float | None) -> float:
    """True Range de una vela.

    Args:
        candle: dict con claves `h`, `l`, `c` (formato del spec §2.2).
        prev_close: cierre de la vela anterior. `None` para la primera.

    Returns:
        El máximo de los 3 componentes del TR, o `h - l` si no hay
        cierre previo. Siempre ≥ 0 salvo que la vela tenga h < l (lo
        cual sería responsabilidad del caller atrapar antes).
    """
    h = candle["h"]
    low = candle["l"]
    if prev_close is None:
        return h - low
    return max(h - low, abs(h - prev_close), abs(low - prev_close))


def atr(candles: list[dict], window: int = 14) -> list[float | None]:
    """Average True Range con Wilder's smoothing.

    Args:
        candles: lista de velas (dicts con `h`, `l`, `c`).
        window: período de smoothing (≥ 1). Default 14.

    Returns:
        Lista del mismo largo que `candles`. `None` en índices
        `< window - 1`. Índice `window - 1` es el mean de los primeros
        `window` TRs. Desde `window` se aplica la recurrencia de
        Wilder.

    Raises:
        ValueError: si `window < 1`.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1 (got {window})")
    n = len(candles)
    result: list[float | None] = [None] * n
    if n == 0 or n < window:
        return result

    # Calcular TRs (uno por vela).
    trs: list[float] = []
    prev_close: float | None = None
    for c in candles:
        trs.append(true_range(c, prev_close))
        prev_close = c["c"]

    # Seed a mean(TR[0..window]).
    seed = sum(trs[:window]) / window
    result[window - 1] = round(seed, 2)
    prev = seed
    for i in range(window, n):
        curr = (prev * (window - 1) + trs[i]) / window
        result[i] = round(curr, 2)
        prev = curr  # keep unrounded for recurrence
    return result
