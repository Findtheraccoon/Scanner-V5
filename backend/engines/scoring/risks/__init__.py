"""Subpaquete de detección de RISK patterns del Scoring Engine (Fase 4).

Portado desde `docs/specs/Observatory/Current/scanner/patterns.py`
líneas 176-196.

**Semántica v5_2:** los RISKS se **detectan** (aparecen en
`analyze()["patterns"]` con `cat="RISK"` y `sg="WARN"`) pero NO
contribuyen al score. El hallazgo H-04 del Observatory eliminó las
risk penalties del score, manteniendo los detectores solo como
informativos.

**Cobertura actual:** 4 risks del Observatory patterns.py.

    Volume-related (`volume.py`):
      - Rebote vol bajo    (volume_ratio < 0.6 + rebote)    w=-2.0
      - Vol declinante     (volSeq declining + rebote)      w=-1.0

    BB fakeouts (`fakeouts.py`):
      - Fakeout sobre BB sup 1H  (c2 wick arriba + cierres abajo)  w=-3.0
      - Fakeout bajo BB inf 1H   (espejo)                           w=-3.0

**Pendientes (no portado aún):** los fakeouts sobre pivotes de
Observatory `engine.py` líneas 142-159. Dependen de `find_pivots()`
que todavía no tiene port en el scanner. Se agregan cuando se port la
función.
"""

from engines.scoring.risks._helpers import RiskDict
from engines.scoring.risks.fakeouts import detect_bb_fakeouts_15m
from engines.scoring.risks.volume import detect_volume_risks_15m

__all__ = [
    "RiskDict",
    "detect_bb_fakeouts_15m",
    "detect_volume_risks_15m",
]
