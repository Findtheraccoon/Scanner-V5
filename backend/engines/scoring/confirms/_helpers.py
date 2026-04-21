"""Helpers compartidos por los detectores de confirms (Fase 5).

Los confirms son la capa 3 del pipeline (spec §3). A diferencia de los
triggers, su peso NO viene hardcoded en el detector — el detector emite
un `ConfirmDict` con descripción canónica, y el motor en `analyze()`
mapea la descripción a una categoría (`_categorize_confirm`) y aplica
el peso tomado de `fixture.confirm_weights`.

**Paridad Observatory:** las descripciones son bit-exact. Cualquier
cambio de formato rompe `_categorize_confirm` y por ende el score.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class ConfirmDict(TypedDict):
    """Forma canónica de un confirm detectado (v4.2.1 compat).

    Aparece tal cual en `analyze()["patterns"]`, junto a los triggers.

    - `sg`: dirección del confirm. Tres valores posibles:
        - "CALL" / "PUT": direccionales (ej. BB inf 1H sugiere CALL).
        - "CONFIRM": neutro, aporta al score tanto en dirección CALL
          como PUT (ej. VolHigh, FzaRel, VolSeq, SqExp).
      El motor en `analyze()` filtra con:
          `sg in (direction, "CONFIRM")`
      donde `direction` viene del alignment gate.
    - `w`: peso informativo v4.2.1 (se preserva por paridad con el
      dict original de Observatory). En v5 NO se usa para scorear — el
      score real sale de `fixture.confirm_weights[categoria]`.
    """

    tf: Literal["15M", "1H", "D"]
    d: str
    sg: Literal["CALL", "PUT", "CONFIRM"]
    w: float
    cat: Literal["CONFIRM"]
    age: int
