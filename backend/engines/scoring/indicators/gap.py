"""Análisis de gap diario — input para el confirm Gap.

Port literal de Observatory `indicators.py:gap()` líneas 242-259. Se
diferencia del helper legacy `gap_pct_at()` en `volume.py` en que:

- Devuelve un **dict rico** `{pct, significant, dir}` o `None`.
- Determina **significancia** comparando contra el ATR daily (en %
  del precio): `abs(gap_pct) > atr_pct * 0.5`.
- Devuelve la **dirección** ("bullish"/"bearish") para que el confirm
  emita CALL/PUT.

El llamador es responsable de computar `atr_pct_val` (típicamente
`atr_dollars / current_close * 100`). Si llega `None`/`0`/falsy,
Observatory aplica fallback 2% — replicado bit-a-bit acá.
"""

from __future__ import annotations


def gap(
    candles_daily: list[dict],
    atr_pct_val: float | None,
) -> dict | None:
    """Detecta gap diario (open de hoy vs close de ayer) y su
    significancia relativa al ATR.

    Observatory: ::

        gap_pct = round((today.o - yesterday.c) / yesterday.c * 100, 2)
        atr_val = atr_pct_val or 2
        significant = abs(gap_pct) > atr_val * 0.5

    Args:
        candles_daily: serie de velas diarias. Mínimo 2.
        atr_pct_val: ATR del último día expresado como porcentaje del
            close actual. `None` o `0` activa fallback 2%.

    Returns:
        Dict `{"pct": float, "significant": bool, "dir": str}` con
        `dir ∈ {"bullish", "bearish"}` (bullish solo si `pct > 0`,
        empate cuenta como bearish — paridad Observatory). `None` si
        hay menos de 2 velas.
    """
    if not candles_daily or len(candles_daily) < 2:
        return None
    today = candles_daily[-1]
    yesterday = candles_daily[-2]
    gap_pct = round(
        (today["o"] - yesterday["c"]) / yesterday["c"] * 100,
        2,
    )
    atr_val = atr_pct_val or 2
    significant = abs(gap_pct) > atr_val * 0.5
    return {
        "pct": gap_pct,
        "significant": significant,
        "dir": "bullish" if gap_pct > 0 else "bearish",
    }
