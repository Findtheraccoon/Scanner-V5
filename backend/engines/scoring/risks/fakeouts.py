"""BB Fakeout risks en 15M contra las bandas 1H.

Port literal de `docs/specs/Observatory/Current/scanner/patterns.py`
líneas 186-196.

Un **fakeout sobre BB sup 1H** ocurre cuando la vela `candles[-2]`
pincha ARRIBA de la banda superior 1H (`h > bb_upper_1h`) pero cierra
ABAJO (`c < bb_upper_1h`), y la vela actual `candles[-1]` también
cierra abajo — señal de rejection del breakout.

El espejo (`bajo BB inf 1H`) es idéntico con `l < bb_lower` y cierres
arriba de la banda inferior.

Ambos requieren ≥ 3 velas 15M (`candles[-3:]`; el primero no se usa
explícitamente pero se mantiene el mínimo por paridad con Observatory).
BB 1H se computa una sola vez sobre la serie 1H y se aplica "actual"
contra las últimas 2 velas 15M (misma convención que Doji/Hammer del
`candle_15m.py`).
"""

from __future__ import annotations

_WEIGHT_FAKEOUT: float = -3.0


def detect_bb_fakeouts_15m(
    candles_15m: list[dict],
    bb_1h: tuple[float, float, float] | None = None,
) -> list[dict]:
    """Detecta BB fakeouts 15M contra las bandas 1H.

    Args:
        candles_15m: velas 15M antigua→reciente. Requiere ≥ 3.
        bb_1h: tupla `(upper, middle, lower)` de Bollinger sobre la
            serie 1H hasta la última vela 1H. `None` deshabilita
            ambos detectores.

    Returns:
        Lista de `RiskDict`. Puede contener 0, 1 o 2 elementos (los
        dos fakeouts son técnicamente mutuamente excluyentes en
        condiciones normales, pero no se prohibe que coexistan).
    """
    if bb_1h is None or len(candles_15m) < 3:
        return []

    bb_upper = bb_1h[0]
    bb_lower = bb_1h[2]

    c2 = candles_15m[-2]
    c1 = candles_15m[-1]

    risks: list[dict] = []

    # Fakeout sobre BB sup 1H: c2.h rompe arriba pero c2 y c1 cierran abajo.
    if c2["h"] > bb_upper and c2["c"] < bb_upper and c1["c"] < bb_upper:
        risks.append(
            {
                "tf": "15M",
                "d": "Fakeout sobre BB sup 1H",
                "sg": "WARN",
                "w": _WEIGHT_FAKEOUT,
                "cat": "RISK",
                "age": 0,
            }
        )

    # Fakeout bajo BB inf 1H: espejo — c2.l rompe abajo pero c2 y c1 cierran arriba.
    if c2["l"] < bb_lower and c2["c"] > bb_lower and c1["c"] > bb_lower:
        risks.append(
            {
                "tf": "15M",
                "d": "Fakeout bajo BB inf 1H",
                "sg": "WARN",
                "w": _WEIGHT_FAKEOUT,
                "cat": "RISK",
                "age": 0,
            }
        )

    return risks
