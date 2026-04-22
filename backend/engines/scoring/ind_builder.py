"""Builder del bundle `ind` — agregado de indicadores para confirms + score.

Port parcial de Observatory `indicators.py:calc_indicators()` líneas
295-341, acotado a las claves que consumen los confirms + el cálculo
de score final en Fase 5. Las claves adicionales del bundle Observatory
(ma100D, ma200D, volH, volProjM, dMA200, orb) no se portan en 5.3a —
son informativas para el output pero no participan del score.

El builder es **puro** (sin I/O, sin estado) y **tolerante a warmup**:
campos que no tienen suficientes velas se resuelven al neutro que
Observatory usa (`0` para `_pct_change`, `1.0` para `vol_ratio`, `None`
para BB/squeeze/gap).

**Claves del bundle:**

| Clave           | Tipo                                    | Fuente                       |
|-----------------|-----------------------------------------|------------------------------|
| `price`         | `float`                                 | `candles_15m[-1]["c"]`        |
| `bb_1h`         | `(upper, middle, lower)` \\| `None`      | `bollinger_bands(closes_1h)` |
| `bb_daily`      | `(upper, middle, lower)` \\| `None`      | `bollinger_bands(closes_d)`  |
| `bb_sq_1h`      | `dict` \\| `None`                        | `bb_width(closes_1h)`        |
| `gap_info`      | `dict` \\| `None`                        | `gap(candles_daily, atr%)`   |
| `vol_m`         | `float`                                 | `vol_ratio_intraday(15m)`    |
| `vol_seq_m`     | `dict`                                  | `vol_sequence(15m, n=4)`     |
| `a_chg`         | `float`                                 | `pct_change(candles_daily)`  |
| `spy_chg`       | `float`                                 | `pct_change(spy_daily)`      |
| `bench_chg`     | `float`                                 | `pct_change(bench_daily)`    |
| `atr_daily`     | `float` \\| `None`                       | `atr(candles_daily)[-1]`     |
| `atr_pct`       | `float` \\| `None`                       | `atr/price*100`              |

El formato de `bb_1h` y `bb_daily` como **tuple** (no dict) está alineado
con la firma que espera `detect_bollinger_confirms`. El bundle completo
Observatory-style (dict `{u, m, l, w}`) queda pendiente para cuando se
wiree `key_levels()` en una fase posterior.
"""

from __future__ import annotations

from typing import TypedDict

from engines.scoring.indicators import (
    atr,
    bb_width,
    bollinger_bands,
    gap,
    vol_ratio_intraday,
    vol_sequence,
)

_BB_WINDOW: int = 20
_BB_K: float = 2.0
_VOL_SEQ_N: int = 4


class IndBundle(TypedDict):
    """Bundle de indicadores consumidos por confirms + score (Fase 5.3)."""

    price: float
    bb_1h: tuple[float, float, float] | None
    bb_daily: tuple[float, float, float] | None
    bb_sq_1h: dict | None
    gap_info: dict | None
    vol_m: float
    vol_seq_m: dict
    a_chg: float
    spy_chg: float
    bench_chg: float
    atr_daily: float | None
    atr_pct: float | None


def build_ind_bundle(
    candles_daily: list[dict],
    candles_1h: list[dict],
    candles_15m: list[dict],
    spy_daily: list[dict] | None = None,
    bench_daily: list[dict] | None = None,
    sim_date: str | None = None,
) -> IndBundle:
    """Calcula el bundle `ind` a partir de las velas del ticker.

    Args:
        candles_daily, candles_1h, candles_15m: series ordenadas
            antigua→reciente. El caller garantiza mínimo de velas
            (Fase 1 valida antes de invocar).
        spy_daily: velas SPY daily. Usado por DivSPY. Si `None`,
            `spy_chg` queda en 0.
        bench_daily: velas del benchmark (si distinto de SPY). Usado
            por FzaRel con override de benchmark. Si `None`,
            `bench_chg` queda en 0.
        sim_date: fecha simulada "YYYY-MM-DD" para `vol_ratio_intraday`.
            `None` en live (se infiere del último candle).

    Returns:
        `IndBundle` con todos los campos poblados. Warmup se resuelve
        al neutro de Observatory (0/1.0/None según campo).
    """
    price = candles_15m[-1]["c"]

    closes_1h = [c["c"] for c in candles_1h]
    closes_daily = [c["c"] for c in candles_daily]

    bb_1h = _last_bb_tuple(bollinger_bands(closes_1h, _BB_WINDOW, _BB_K))
    bb_daily = _last_bb_tuple(bollinger_bands(closes_daily, _BB_WINDOW, _BB_K))
    bb_sq_1h = bb_width(closes_1h, _BB_WINDOW, _BB_K)

    atr_series = atr(candles_daily)
    atr_daily = atr_series[-1] if atr_series else None
    atr_pct: float | None = None
    if atr_daily is not None and price > 0:
        atr_pct = round(atr_daily / price * 100, 2)

    gap_info = gap(candles_daily, atr_pct)

    vol_m = vol_ratio_intraday(candles_15m, sim_date)
    vol_seq_m = vol_sequence(candles_15m, _VOL_SEQ_N)

    a_chg = _pct_change(candles_daily, 1)
    spy_chg = _pct_change(spy_daily, 1) if spy_daily else 0.0
    bench_chg = _pct_change(bench_daily, 1) if bench_daily else 0.0

    return IndBundle(
        price=price,
        bb_1h=bb_1h,
        bb_daily=bb_daily,
        bb_sq_1h=bb_sq_1h,
        gap_info=gap_info,
        vol_m=vol_m,
        vol_seq_m=vol_seq_m,
        a_chg=a_chg,
        spy_chg=spy_chg,
        bench_chg=bench_chg,
        atr_daily=atr_daily,
        atr_pct=atr_pct,
    )


def _last_bb_tuple(
    bb_series: tuple[list[float | None], list[float | None], list[float | None]],
) -> tuple[float, float, float] | None:
    """Último trío `(upper, middle, lower)` de `bollinger_bands()`.

    Devuelve `None` si alguno de los tres es `None` en el último índice
    (warmup incompleto). La tupla respeta el orden esperado por
    `detect_bollinger_confirms` (upper primero, luego middle, luego lower).
    """
    lower, middle, upper = bb_series
    lo = lower[-1] if lower else None
    mi = middle[-1] if middle else None
    up = upper[-1] if upper else None
    if lo is None or mi is None or up is None:
        return None
    return (up, mi, lo)


def _pct_change(candles: list[dict] | None, n: int = 1) -> float:
    """Pct change del último close vs el close `n` velas atrás.

    Port literal de Observatory `indicators.py:pct_change()` líneas
    51-57. Devuelve `0` (no `None`) si no hay suficientes velas o el
    close previo es <= 0 — paridad crítica porque `a_chg` fluye a
    `detect_fzarel_confirm` y `detect_divspy_confirm` que esperan
    float, no optional.
    """
    if not candles or len(candles) < n + 1:
        return 0.0
    prev = candles[-1 - n]["c"]
    cur = candles[-1]["c"]
    if prev <= 0:
        return 0.0
    return round((cur - prev) / prev * 100, 2)
