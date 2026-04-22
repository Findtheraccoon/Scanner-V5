"""Subpaquete de detección de confirms del Scoring Engine (Fase 5).

Portado desde `docs/specs/Observatory/Current/scanner/patterns.py` (BB,
VolHigh, VolSeq, SqExp) y `engine.py` (FzaRel, DivSPY, Gap). Cada
confirm produce un `ConfirmDict` con la forma canónica::

    {"tf", "d", "sg", "w", "cat": "CONFIRM", "age"}

El motor en `analyze()` agrega estos a `patterns[]` y, para el score
final, mapea la descripción (`d`) a una de las 10 categorías mediante
`_categorize_confirm()` y aplica el peso desde `fixture.confirm_weights`
con dedup por categoría.

**Cobertura (10 confirms):**

    Bollinger Bands (4):
      - BB sup 1H / BB inf 1H
      - BB sup D  / BB inf D

    Volume (2):
      - VolHigh        (`volM > 1.5`)
      - VolSeq         (`volSeqM.growing`)

    Squeeze (1):
      - SqExp          (squeeze activo + expandiendo)

    Gap (1):
      - Gap alcista/bajista (direccional)

    Fuerza relativa vs benchmark (2):
      - FzaRel         (vs SPY o benchmark override)
      - DivSPY         (divergencia direccional con SPY)

**Importante:** los pesos aplicados al score vienen de la fixture, NO
de los detectores. Los valores de `w` en los dicts se preservan sólo
para paridad con el output de Observatory.
"""

from engines.scoring.confirms._helpers import ConfirmDict
from engines.scoring.confirms.bollinger import detect_bollinger_confirms
from engines.scoring.confirms.categorize import (
    apply_confirm_weights,
    categorize_confirm,
)
from engines.scoring.confirms.gap import detect_gap_confirm
from engines.scoring.confirms.relative_strength import (
    detect_divspy_confirm,
    detect_fzarel_confirm,
)
from engines.scoring.confirms.squeeze import detect_squeeze_expansion_confirm
from engines.scoring.confirms.volume import (
    detect_volume_high_confirm,
    detect_volume_sequence_confirm,
)

__all__ = [
    "ConfirmDict",
    "apply_confirm_weights",
    "categorize_confirm",
    "detect_bollinger_confirms",
    "detect_divspy_confirm",
    "detect_fzarel_confirm",
    "detect_gap_confirm",
    "detect_squeeze_expansion_confirm",
    "detect_volume_high_confirm",
    "detect_volume_sequence_confirm",
]
