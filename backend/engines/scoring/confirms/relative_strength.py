"""Confirms de fuerza relativa — 2 del total (FzaRel + DivSPY).

Portado de `docs/specs/Observatory/Current/scanner/engine.py` líneas
99-135. Ambos comparan el cambio porcentual daily del ticker contra
el de un benchmark (SPY por default, o bench_ticker si se pasa).

**FzaRel** — fuerza relativa positiva: el activo se mueve en la
dirección del alignment con más intensidad que el benchmark
(diff > 0.5 pp). Señal neutral (`sg="CONFIRM"`), aporta a la dirección
que indique el alignment gate.

**DivSPY** — divergencia con SPY: el activo y SPY se mueven en
direcciones opuestas con magnitud suficiente (ambos cruzan sus
thresholds). Señal direccional (`sg="CALL"` o `"PUT"`) según el signo
del `a_chg`.

**Paridad crítica — descripciones:**
    FzaRel → `f"FzaRel {+|''}{diff}% vs {bench}"`
    DivSPY → `f"Div SPY ({ticker}:{+|''}{a_chg}% vs SPY:{+|''}{spy_chg}%) → VERIFICAR CATALIZADOR"`

Ambos signos usan el truco `'+' if x > 0 else ''` — el "-" para
negativos ya viene embebido en el número. La flecha es unicode `→`.

**Pesos informativos (v4.2.1):** FzaRel=4, DivSPY=1. En v5 el fixture
los pondera igual (FzaRel=4, DivSPY=1 en el canonical QQQ).
"""

from __future__ import annotations

from engines.scoring.alignment import AlignmentDir
from engines.scoring.confirms._helpers import ConfirmDict

# Umbrales hardcoded (Observatory / v4.2.1).
_DIVSPY_ASSET_THRESHOLD: float = 0.5   # |a_chg| debe superar
_DIVSPY_SPY_THRESHOLD: float = 0.3     # |spy_chg| debe superar
_FZAREL_MIN_DIVERGENCE: float = 0.5    # a_chg vs b_chg + 0.5 pp


def detect_fzarel_confirm(
    a_chg: float,
    bench_chg: float,
    bench_ticker: str,
    alignment_dir: AlignmentDir,
) -> list[dict]:
    """Confirma FzaRel cuando el ticker diverge del benchmark en la
    dirección del alignment con magnitud ≥ 0.5 pp.

    Observatory::

        if ((aln["dir"] == "bullish" and a_chg > b_chg + 0.5)
                or (aln["dir"] == "bearish" and a_chg < b_chg - 0.5)):
            ...

    No dispara si `alignment_dir == "mixed"` — por construcción el
    alignment mixto no pasa el structure gate, así que este caso no
    debería llegar a los confirms en el flujo real. Se deja el guard
    por robustez.

    Args:
        a_chg: pct change daily del ticker (última vela vs previa).
        bench_chg: pct change daily del benchmark.
        bench_ticker: símbolo del benchmark ("SPY" por default, o
            override).
        alignment_dir: dirección del alignment gate.

    Returns:
        Lista con 0 o 1 confirm.
    """
    fires_bull = (
        alignment_dir == "bullish"
        and a_chg > bench_chg + _FZAREL_MIN_DIVERGENCE
    )
    fires_bear = (
        alignment_dir == "bearish"
        and a_chg < bench_chg - _FZAREL_MIN_DIVERGENCE
    )
    if not (fires_bull or fires_bear):
        return []

    diff = round(a_chg - bench_chg, 2)
    sign = "+" if diff > 0 else ""
    confirm: ConfirmDict = {
        "tf": "D",
        "d": f"FzaRel {sign}{diff}% vs {bench_ticker}",
        "sg": "CONFIRM",
        "w": 4.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]


def detect_divspy_confirm(
    ticker: str,
    a_chg: float,
    spy_chg: float,
) -> list[dict]:
    """Confirma DivSPY cuando el ticker y SPY divergen direccionalmente.

    Observatory::

        if ticker != "SPY" and spy_chg != 0:
            if (a_chg < -0.5 and spy_chg > 0.3) or (a_chg > 0.5 and spy_chg < -0.3):
                ...

    Sólo aplica a tickers distintos de SPY. La dirección del confirm
    sigue al signo de `a_chg` (ticker bajando con SPY arriba → PUT;
    ticker subiendo con SPY abajo → CALL).

    Args:
        ticker: símbolo del asset (si es "SPY", no dispara).
        a_chg: pct change daily del ticker.
        spy_chg: pct change daily de SPY.

    Returns:
        Lista con 0 o 1 confirm.
    """
    if ticker == "SPY" or spy_chg == 0:
        return []

    bearish_div = a_chg < -_DIVSPY_ASSET_THRESHOLD and spy_chg > _DIVSPY_SPY_THRESHOLD
    bullish_div = a_chg > _DIVSPY_ASSET_THRESHOLD and spy_chg < -_DIVSPY_SPY_THRESHOLD

    if not bearish_div and not bullish_div:
        return []

    sign_a = "+" if a_chg > 0 else ""
    sign_spy = "+" if spy_chg > 0 else ""
    direction = "CALL" if a_chg > 0 else "PUT"

    confirm: ConfirmDict = {
        "tf": "D",
        "d": (
            f"Div SPY ({ticker}:{sign_a}{a_chg}% vs "
            f"SPY:{sign_spy}{spy_chg}%) → VERIFICAR CATALIZADOR"
        ),
        "sg": direction,
        "w": 1.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]
