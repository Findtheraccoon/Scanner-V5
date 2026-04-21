"""Doble techo / Doble piso — 2 triggers del total de 14.

Port literal de scanner_v4.2.1.html líneas 432-438.

Sobre las últimas 20 velas 15M, identifica pivots locales (highs y lows
con lookback = 1 vela a cada lado, comparación estricta). Si los dos
últimos pivot highs (o lows) están dentro de 0.5% y separados por ≥3
velas, dispara el trigger con precio aproximado del pivote más antiguo.

Reglas exactas (v4.2.1):

    Pivot high en i: h[i] > h[i-1] AND h[i] > h[i+1]
    Pivot low  en i: l[i] < l[i-1] AND l[i] < l[i+1]

    Doble techo:
        últimos 2 pivot highs = (a, b) con índices (a_i, b_i)
        |a.h - b.h| / a.h < 0.005
        b_i - a_i >= 3
        → PUT w=3.0, description "Doble techo ~$<a.h>"

    Doble piso:
        espejo sobre pivot lows
        → CALL w=3.0
"""

from __future__ import annotations

_DOUBLE_PRICE_TOLERANCE: float = 0.005  # 0.5%
_DOUBLE_MIN_INDEX_GAP: int = 3
_LOOKBACK_WINDOW: int = 20
_WEIGHT_DOUBLE: float = 3.0


def detect_double_patterns_15m(candles_15m: list[dict]) -> list[dict]:
    """Detecta doble techo / piso en las últimas 20 velas 15M.

    Args:
        candles_15m: velas 15M antigua→reciente. Se usa `candles[-20:]`.
            Si hay menos de 20 devuelve vacío (v4.2.1 no dispara).

    Returns:
        Lista de `TriggerDict` con `tf="15M"`, `age=0`. Puede tener 0,
        1 o 2 elementos (techo + piso pueden coexistir en teoría si hay
        pivots alternados, aunque es raro).
    """
    if len(candles_15m) < _LOOKBACK_WINDOW:
        return []
    recent = candles_15m[-_LOOKBACK_WINDOW:]
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []

    # Pivots con lookback=1 a cada lado, comparación estricta (>/<).
    for i in range(1, len(recent) - 1):
        if recent[i]["h"] > recent[i - 1]["h"] and recent[i]["h"] > recent[i + 1]["h"]:
            pivot_highs.append((i, recent[i]["h"]))
        if recent[i]["l"] < recent[i - 1]["l"] and recent[i]["l"] < recent[i + 1]["l"]:
            pivot_lows.append((i, recent[i]["l"]))

    triggers: list[dict] = []

    # Doble techo: últimos 2 pivot highs cerca en precio + separación temporal
    if len(pivot_highs) >= 2:
        (a_idx, a_val), (b_idx, b_val) = pivot_highs[-2], pivot_highs[-1]
        if (
            a_val > 0
            and abs(a_val - b_val) / a_val < _DOUBLE_PRICE_TOLERANCE
            and b_idx - a_idx >= _DOUBLE_MIN_INDEX_GAP
        ):
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Doble techo ~${a_val:.2f}",
                    "sg": "PUT",
                    "w": _WEIGHT_DOUBLE,
                    "cat": "TRIGGER",
                    "age": 0,
                }
            )

    # Doble piso: espejo sobre pivot lows
    if len(pivot_lows) >= 2:
        (a_idx, a_val), (b_idx, b_val) = pivot_lows[-2], pivot_lows[-1]
        if (
            a_val > 0
            and abs(a_val - b_val) / a_val < _DOUBLE_PRICE_TOLERANCE
            and b_idx - a_idx >= _DOUBLE_MIN_INDEX_GAP
        ):
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Doble piso ~${a_val:.2f}",
                    "sg": "CALL",
                    "w": _WEIGHT_DOUBLE,
                    "cat": "TRIGGER",
                    "age": 0,
                }
            )

    return triggers
