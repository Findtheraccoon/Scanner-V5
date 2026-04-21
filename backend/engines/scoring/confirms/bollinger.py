"""Confirms de Bollinger Bands — 4 del total (sup/inf en 1H y D).

Portado de `docs/specs/Observatory/Current/scanner/patterns.py` líneas
152-160. Cada confirm se dispara cuando el close de la última vela 15M
toca o cruza la banda superior/inferior del timeframe mayor.

**Señal de dirección:**
    - BB sup (1H o D) → `PUT`  (contratendencia, esperando reversión bajista)
    - BB inf (1H o D) → `CALL` (contratendencia, esperando rebote alcista)

**Pesos informativos (v4.2.1):** BBinf_1H=3, BBsup_1H=1, BBsup_D=1,
BBinf_D=1. En v5 el score final usa `fixture.confirm_weights`, no
estos valores. Se preservan en el dict sólo para paridad con el output
de Observatory.

**Paridad crítica — descripción:** el formato `f"BB sup 1H (${upper})"`
es bit-exact con Observatory. El round a 2 decimales ya lo hace el
indicador BB al retornar la tupla; NO se aplica `.2f` explícito aquí —
por eso un valor `498.2` se serializa como `"$498.2"` (sin trailing
cero), igual que Observatory. Tocar este formato rompe paridad
porque `_categorize_confirm` sólo mira el prefijo `"BB sup 1H"` /
`"BB inf D"`, pero el valor del paréntesis se compara bit-a-bit con
el sample canonical.
"""

from __future__ import annotations

from engines.scoring.confirms._helpers import ConfirmDict


def detect_bollinger_confirms(
    last_close_15m: float,
    bb_1h: tuple[float, float, float] | None,
    bb_daily: tuple[float, float, float] | None,
) -> list[dict]:
    """Detecta confirms de BB sup/inf en 1H y D.

    Args:
        last_close_15m: close de la última vela 15M. Observatory usa
            `L["c"]` donde `L = candles_15m[-1]`.
        bb_1h: trío `(upper, middle, lower)` de BB 1H, o `None` si
            la serie 1H no tiene suficientes velas (warmup).
        bb_daily: trío `(upper, middle, lower)` de BB Daily, o `None`.

    Returns:
        Lista con 0 a 2 confirms. Por construcción, un mismo close
        no puede tocar simultáneamente upper e lower del mismo TF, así
        que el máximo efectivo es 2 (uno por timeframe).
    """
    out: list[dict] = []

    if bb_1h is not None:
        upper_1h, _middle_1h, lower_1h = bb_1h
        if last_close_15m >= upper_1h:
            confirm: ConfirmDict = {
                "tf": "1H",
                "d": f"BB sup 1H (${upper_1h})",
                "sg": "PUT",
                "w": 1.0,
                "cat": "CONFIRM",
                "age": 0,
            }
            out.append(dict(confirm))
        if last_close_15m <= lower_1h:
            confirm = {
                "tf": "1H",
                "d": f"BB inf 1H (${lower_1h})",
                "sg": "CALL",
                "w": 3.0,
                "cat": "CONFIRM",
                "age": 0,
            }
            out.append(dict(confirm))

    if bb_daily is not None:
        upper_d, _middle_d, lower_d = bb_daily
        if last_close_15m >= upper_d:
            confirm = {
                "tf": "D",
                "d": f"BB sup D (${upper_d})",
                "sg": "PUT",
                "w": 1.0,
                "cat": "CONFIRM",
                "age": 0,
            }
            out.append(dict(confirm))
        if last_close_15m <= lower_d:
            confirm = {
                "tf": "D",
                "d": f"BB inf D (${lower_d})",
                "sg": "CALL",
                "w": 1.0,
                "cat": "CONFIRM",
                "age": 0,
            }
            out.append(dict(confirm))

    return out
