"""Confirm de Squeeze → Expansión — 1 del total (SqExp).

Portado de `docs/specs/Observatory/Current/scanner/patterns.py` línea
173-174. Se dispara cuando el ancho de BB en 1H está en squeeze (bajo
percentil 15) Y al mismo tiempo está expandiéndose (últimas 3
lecturas crecientes). Señal de ruptura inminente.

**Paridad crítica — descripción:** `"Squeeze → Expansión (ruptura)"`
(nota: flecha unicode `→` U+2192, NO `->`). El `_categorize_confirm`
mapea por `desc.startswith("Squeeze")` → SqExp.

**Pattern adicional NO portado:** Observatory emite también
`"BB Squeeze (ancho p{percentile})"` con `cat="SQUEEZE"` cuando sólo
hay squeeze sin expansión. Ese pattern tiene categoría distinta
(SQUEEZE ≠ CONFIRM) y NO participa del score — no lo detectamos acá,
es responsabilidad informativa del ind builder si se decide incluirlo
en el output.

**Peso informativo (v4.2.1):** 0. El fixture canonical QQQ también
tiene SqExp=0 (hallazgo H-03 del Observatory: contribución marginal
negativa). El detector sigue emitiendo por paridad de output con el
sample canonical.
"""

from __future__ import annotations

from engines.scoring.confirms._helpers import ConfirmDict


def detect_squeeze_expansion_confirm(bb_sq_1h: dict | None) -> list[dict]:
    """Confirma SqExp cuando BB 1H está en squeeze y expandiendo.

    Observatory: `if ind["bbSqH"] and ind["bbSqH"]["isSqueeze"] and
    ind["bbSqH"]["isExpanding"]: ...`. Ambas condiciones deben ser
    verdaderas simultáneamente — squeeze sin expansión no dispara.

    Args:
        bb_sq_1h: dict del indicador `bb_width` sobre 1H, con las
            claves `isSqueeze` (percentil < 15) e `isExpanding`
            (últimas 3 lecturas crecientes monotónicamente).
            `None` se trata como ausencia de datos suficientes
            para el cálculo (no emite confirm).

    Returns:
        Lista con 0 o 1 confirm.
    """
    if bb_sq_1h is None:
        return []
    if not bb_sq_1h.get("isSqueeze") or not bb_sq_1h.get("isExpanding"):
        return []
    confirm: ConfirmDict = {
        "tf": "1H",
        "d": "Squeeze → Expansión (ruptura)",
        "sg": "CONFIRM",
        "w": 0.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]
