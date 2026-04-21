"""Métricas de volumen y gap — inputs para los confirms VolHigh/VolSeq/Gap.

Todas las funciones operan sobre la lista completa de velas y un
`index` — devuelven el valor *en ese índice* considerando la historia
previa. Esto hace trivial el uso desde el scoring (que típicamente
pide "el valor AL momento de la señal", no toda la serie).
"""

from __future__ import annotations


def volume_ratio_at(
    candles: list[dict],
    index: int,
    window: int = 20,
) -> float | None:
    """Ratio del volumen en `index` vs promedio de los `window` previos.

    Usado por el confirm VolHigh: el fixture declara un umbral mínimo
    (`volhigh_min_ratio`, típicamente 1.2) y se dispara si este ratio
    lo supera.

    Args:
        candles: lista de velas (dicts con `v`).
        index: índice de la vela a medir.
        window: cantidad de velas previas a promediar (≥ 1).

    Returns:
        `volumes[index] / mean(volumes[index - window : index])`.
        `None` si `index < window`, `index` fuera de rango, o el
        promedio es ≤ 0 (división protegida).

    Raises:
        ValueError: si `window < 1`.
    """
    if window < 1:
        raise ValueError(f"window must be >= 1 (got {window})")
    if index < window or index >= len(candles):
        return None
    recent = [candles[i]["v"] for i in range(index - window, index)]
    avg = sum(recent) / window
    if avg <= 0:
        return None
    return candles[index]["v"] / avg


def is_volume_increasing(
    candles: list[dict],
    index: int,
    n: int = 3,
) -> bool:
    """True si los últimos `n` volúmenes (inclusivo `index`) son
    estrictamente crecientes.

    Usado por el confirm VolSeq. El valor `n` típico es 3 (tres velas
    con volumen creciente seguidas).

    Args:
        candles: lista de velas.
        index: índice de la última vela de la secuencia.
        n: largo de la secuencia (≥ 2).

    Returns:
        True si `v[index-n+1] < v[index-n+2] < ... < v[index]`. False
        en cualquier otro caso, incluido no tener suficiente historia.

    Raises:
        ValueError: si `n < 2`.
    """
    if n < 2:
        raise ValueError(f"n must be >= 2 (got {n})")
    if index < n - 1 or index >= len(candles):
        return False
    vols = [candles[i]["v"] for i in range(index - n + 1, index + 1)]
    return all(vols[i] > vols[i - 1] for i in range(1, n))


def gap_pct_at(candles: list[dict], index: int) -> float | None:
    """Porcentaje de gap entre `candles[index]` y la vela anterior.

    Fórmula: `(open[i] - close[i-1]) / close[i-1] * 100`.

    Args:
        candles: lista de velas (dicts con `o` y `c`).
        index: índice de la vela cuyo open se compara contra el close
            previo.

    Returns:
        Gap en puntos porcentuales (positivo si gap al alza, negativo
        al baja). `None` si `index <= 0`, fuera de rango, o el close
        previo es ≤ 0 (división protegida).
    """
    if index < 1 or index >= len(candles):
        return None
    prev_close = candles[index - 1]["c"]
    if prev_close <= 0:
        return None
    return (candles[index]["o"] - prev_close) / prev_close * 100.0
