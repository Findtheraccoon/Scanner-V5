"""Helpers compartidos por los 14 triggers del motor v5.2.0.

Se portan tal cual del scanner_v4.2.1.html (función `detect()` + `decayW()`)
para preservar paridad con el canonical QQQ. Cualquier cambio de valores
(umbrales, schedule de decay) implica recalibrar el canonical y bumpear
versión del motor (spec §4.1).
"""

from __future__ import annotations

from typing import Literal, TypedDict


class TriggerDict(TypedDict):
    """Forma canónica de un trigger detectado (v4.2.1 compat).

    Aparece tal cual en `analyze()["patterns"]`.
    """

    tf: Literal["15M", "1H", "D"]
    d: str
    sg: Literal["CALL", "PUT"]
    w: float
    cat: Literal["TRIGGER"]
    age: int


# ───────────────────────────────────────────────────────────────────────────
# Decay schedule — v4.2.1 línea 391
# ───────────────────────────────────────────────────────────────────────────


def decay_weight(age: int) -> float:
    """Factor multiplicativo del peso según antigüedad de la vela.

    Convención v4.2.1::

        age 0-1   → 1.0   (velas muy recientes, peso pleno)
        age 2-3   → 0.85
        age 4-5   → 0.7
        age 6-10  → 0.4
        age > 10  → 0.2   (residual, casi descartada)

    Cualquier cambio de estos valores rompe paridad con el canonical
    QQQ. No modificar sin replay + sign-off.
    """
    if age <= 1:
        return 1.0
    if age <= 3:
        return 0.85
    if age <= 5:
        return 0.7
    if age <= 10:
        return 0.4
    return 0.2


# ───────────────────────────────────────────────────────────────────────────
# Features de una vela — puras geometría
# ───────────────────────────────────────────────────────────────────────────


def candle_range(c: dict) -> float:
    """High - Low."""
    return c["h"] - c["l"]


def candle_body(c: dict) -> float:
    """|Open - Close|."""
    return abs(c["o"] - c["c"])


def upper_wick(c: dict) -> float:
    """High - max(Open, Close)."""
    return c["h"] - max(c["o"], c["c"])


def lower_wick(c: dict) -> float:
    """min(Open, Close) - Low."""
    return min(c["o"], c["c"]) - c["l"]


def is_bull(c: dict) -> bool:
    """Close ≥ Open. El empate cuenta como bull (convención v4.2.1)."""
    return c["c"] >= c["o"]


def age_label(age: int) -> str:
    """Sufijo humano "(3v atrás)" o "" si age=0.

    Coincide con la etiqueta que el v4.2.1 usa en el campo `d` de los
    triggers con decay. Permite que un trigger "Rechazo sup 70% (2v atrás)"
    sea distinguible en la UI del de la vela actual.
    """
    return f" ({age}v atrás)" if age > 0 else ""
