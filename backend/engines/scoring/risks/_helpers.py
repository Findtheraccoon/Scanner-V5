"""Tipos compartidos del subpaquete risks/.

Los RISKS del motor v5.2.0 son patterns con `cat="RISK"` y `sg="WARN"`.
Se **detectan** pero **NO** contribuyen al score (v5 hallazgo H-04
eliminó las risk penalties del score). Observatory scoring.py los
guarda en `layers.risk.items` para trazabilidad/UI.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class RiskDict(TypedDict):
    """Forma canónica de un risk detectado (Observatory compat).

    Aparece en `analyze()["patterns"]` junto con triggers y confirms.
    Se distingue por `cat="RISK"` y `sg="WARN"`.
    """

    tf: Literal["15M", "1H", "D"]
    d: str
    sg: Literal["WARN"]
    w: float  # negative (informational, NOT sumado al score)
    cat: Literal["RISK"]
    age: int
