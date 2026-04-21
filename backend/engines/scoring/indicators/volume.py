"""Métricas de volumen y gap — inputs para los confirms VolHigh/VolSeq/Gap.

Dos familias de funciones conviven acá:

1. **API legacy `*_at(candles, index)`** — `volume_ratio_at`,
   `is_volume_increasing`, `gap_pct_at`. Usadas por Fase 4. La forma
   `_at` evita pasar la serie completa cuando solo se necesita el
   valor en un índice. **Diverge de Observatory** (`volume_ratio_at`
   usa mean sobre ventana fija; Observatory usa median intraday).

2. **API Observatory** — `today_candles`, `vol_ratio_intraday`,
   `vol_sequence`. Port exacto de
   `docs/specs/Observatory/Current/scanner/indicators.py` (líneas
   64-235). Usadas por Fase 5 (confirms VolHigh + VolSeq + DivSPY +
   FzaRel y por el wiring del ORB en sub-fase 5.3).

**Rounding a 2 decimales** en todas las funciones de salida numérica —
paridad bit-a-bit con Observatory `indicators.py`.
"""

from __future__ import annotations

import math
from statistics import median as _stdlib_median


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
    return round(candles[index]["v"] / avg, 2)


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


def today_candles(
    candles: list[dict],
    sim_date: str | None = None,
) -> list[dict]:
    """Filtra las velas que pertenecen al día `sim_date` (YYYY-MM-DD).

    Port literal de Observatory `indicators.py:today_candles()`
    (líneas 64-75). En modo backtest se pasa `sim_date` explícito; en
    live, si se omite, se infiere del `dt` de la última vela.

    El campo `dt` puede venir con formato `"YYYY-MM-DD HH:MM:SS"` o
    ISO `"YYYY-MM-DDTHH:MM:SS"` — ambos casos cubiertos por el split
    en " " o "T".

    Args:
        candles: lista de velas (dicts con `dt`).
        sim_date: fecha simulada `"YYYY-MM-DD"`. Si `None`, se infiere
            del último candle.

    Returns:
        Sub-lista de velas cuyo `dt` empieza con `sim_date`. Lista
        vacía si `candles` es vacío.
    """
    if not candles:
        return []
    if sim_date is None:
        last_dt = candles[-1]["dt"]
        if " " in last_dt:
            sim_date = last_dt.split(" ")[0]
        elif "T" in last_dt:
            sim_date = last_dt.split("T")[0]
        else:
            sim_date = last_dt
    return [c for c in candles if c["dt"] and c["dt"].startswith(sim_date)]


def vol_ratio_intraday(
    candles: list[dict],
    sim_date: str | None = None,
) -> float:
    """Ratio del volumen de la penúltima vela completa vs **mediana**
    de las velas completas del día.

    Port literal de Observatory `indicators.py:vol_ratio()` con
    `today_only=True` (líneas 82-100). Se usa para 15M/1H. Razones
    Observatory:

    1. **Same-day comparison** — comparar contra el mismo día evita
       distorsión por sesiones previas con perfil distinto.
    2. **Mediana** — anula el outlier de la vela de apertura 9:30
       que típicamente lleva 3-5x el volumen del resto.
    3. **Penúltima completa** — la vela `[-1]` puede estar en
       formación (incompleta); la "completed" es `[-2]`.

    Si hay menos de 4 velas del día (3 completas + 1 actual), no hay
    suficiente historia para una mediana significativa → devuelve
    1.0 neutro (en lugar de `None`, paridad Observatory).

    Args:
        candles: lista de velas intraday (15M o 1H típicamente).
        sim_date: fecha simulada `"YYYY-MM-DD"`. Si `None`, se infiere
            del último candle (live mode).

    Returns:
        Ratio redondeado a 2 decimales, o `1.0` si no hay datos
        suficientes o la mediana es ≤ 0 (división protegida).
    """
    tc = today_candles(candles, sim_date)
    if len(tc) < 4:
        return 1.0
    completed = tc[-2]
    vols = [c["v"] for c in tc[:-2]]
    med = _stdlib_median(vols)
    if med <= 0:
        return 1.0
    return round(completed["v"] / med, 2)


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
    return round((candles[index]["o"] - prev_close) / prev_close * 100.0, 2)


def vol_sequence(candles: list[dict], n: int = 4) -> dict:
    """Detecta secuencia de N velas completas crecientes o decrecientes
    en volumen, con tolerancia del 5%.

    Port literal de Observatory `indicators.py:vol_sequence()` líneas
    211-235. Comportamiento clave:

    - **Excluye la última vela** (potencialmente incompleta). Toma
      `n` velas previas (`candles[-(n+1):-1]`).
    - **Tolerancia 5%:** una vela cuenta como "growing" si su volumen
      supera al 95% de la previa, y como "declining" si está por
      debajo del 105% de la previa. Una misma vela puede contar para
      ambos en la zona de tolerancia (es por diseño).
    - **Threshold 75%:** `ceil((n-1) * 0.75)` velas deben cumplir.
      Para `n=4` → 3 de 3 comparaciones (estricto).
    - **Mutex con prioridad growing:** si ambos cumplen, gana
      `growing` (orden del `if` Observatory).
    - **Count signo:** positivo para growing, negativo para declining.

    Usado por:
    - confirm `VolSeq` (`growing == True` → fires)
    - risk `vol_declining` (`declining == True` → fires)

    Args:
        candles: lista de velas (dicts con `v`).
        n: número de velas completas a evaluar (default 4 — Observatory).

    Returns:
        Dict con forma `{"growing": bool, "declining": bool, "count": int}`.
        Si `len(candles) < n + 2`, devuelve neutro `{False, False, 0}`.
    """
    if not candles or len(candles) < n + 2:
        return {"growing": False, "declining": False, "count": 0}
    completed = candles[-(n + 1) : -1]
    g_count = 0
    d_count = 0
    for i in range(1, len(completed)):
        if completed[i]["v"] > completed[i - 1]["v"] * 0.95:
            g_count += 1
        if completed[i]["v"] < completed[i - 1]["v"] * 1.05:
            d_count += 1
    threshold = math.ceil((n - 1) * 0.75)
    growing = g_count >= threshold
    declining = d_count >= threshold
    if growing:
        return {"growing": True, "declining": False, "count": g_count}
    if declining:
        return {"growing": False, "declining": True, "count": -d_count}
    return {"growing": False, "declining": False, "count": 0}
