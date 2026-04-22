"""Resolución de bandas de confianza desde `fixture.score_bands`.

Las bandas del fixture son **semi-abiertas**: `min <= score < max`, con
`max=None` como "sin tope superior" (la banda más alta). La tabla está
ordenada por `min` descendente en el canonical QQQ:

    S+   min=16 max=null   → SETUP
    S    min=14 max=16     → SETUP
    A+   min=10 max=14     → SETUP
    A    min=7  max=10     → SETUP
    B    min=4  max=7      → REVISAR
    REVISAR min=2 max=4    → REVISAR

Score por debajo del `min` más bajo → no hay banda → `NEUTRAL` con
conf="—".

**Paridad Observatory:** los thresholds hardcoded en
`scoring.py:layered_score()` (16/14/10/7/4/2) coinciden con los de la
fixture canonical QQQ. No obstante, el motor V5 lee SIEMPRE del
fixture — jamás usa constantes propias.
"""

from __future__ import annotations

from engines.scoring.constants import (
    CONF_UNKNOWN,
    SIGNAL_NEUTRAL,
)
from modules.fixtures import Fixture


def resolve_band(
    score: float,
    fixture: Fixture,
) -> tuple[str, str]:
    """Devuelve `(conf, signal)` para un score dado.

    La búsqueda usa intervalos semi-abiertos `[min, max)`. La banda con
    `max=None` se trata como `[min, +∞)`. Si ninguna banda matchea, se
    devuelve el neutro (`CONF_UNKNOWN`, `SIGNAL_NEUTRAL`).

    Args:
        score: valor de `trigger_sum + confirm_sum`, ya redondeado.
        fixture: fixture parseado (frozen).

    Returns:
        Tupla `(conf, signal)`. `conf` es el `label` de la banda que
        matcheó (ej. "S+", "A", "B", "REVISAR"), o "—" si ninguna.
        `signal` es uno de "SETUP"/"REVISAR"/"NEUTRAL".
    """
    for band in fixture.score_bands:
        upper_ok = band.max is None or score < band.max
        if score >= band.min and upper_ok:
            return band.label, band.signal
    return CONF_UNKNOWN, SIGNAL_NEUTRAL
