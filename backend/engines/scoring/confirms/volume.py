"""Confirms de volumen — 2 del total (VolHigh + VolSeq).

Portado de `docs/specs/Observatory/Current/scanner/patterns.py` líneas
163-168. Ambos confirms son señales neutras (`sg="CONFIRM"`), aportan
al score tanto para CALL como para PUT — el motor en `analyze()` los
filtra con `sg in (direction, "CONFIRM")`.

**Pesos informativos (v4.2.1):** VolHigh=2, VolSeq=0. En v5 el score
final usa `fixture.confirm_weights`. El fixture canonical QQQ tiene
VolSeq=0 (hallazgo H-03 del Observatory: contribución marginal
negativa), pero el detector sigue emitiendo el pattern por paridad
de output bit-a-bit con el sample canonical.

**Paridad crítica — descripción:**
    VolHigh → `"Vol {volM}x avg"`     → startswith "..." + "x avg" → VolHigh
    VolSeq  → `"Vol creciente N velas"` → startswith "Vol creciente" → VolSeq

El `_categorize_confirm` de Observatory mira:
    - `"x avg" in desc` → VolHigh
    - `desc.startswith("Vol creciente")` → VolSeq

Por eso los dos empiezan con `"Vol "` pero se distinguen por la segunda
palabra. Cuidado al tocar el formato.
"""

from __future__ import annotations

from engines.scoring.confirms._helpers import ConfirmDict

# Umbrales hardcoded (Observatory / v4.2.1). Cambiarlos rompe paridad.
_VOL_HIGH_RATIO_MIN: float = 1.5


def detect_volume_high_confirm(vol_m: float | None) -> list[dict]:
    """Confirma VolHigh cuando el ratio de volumen 15M supera 1.5x.

    Observatory: `if ind["volM"] > 1.5: ...` (estrictamente mayor, no
    mayor-o-igual). El valor de `volM` es el resultado de
    `vol_ratio(candles_15m, today_only=True, sim_date=...)` —
    mediana intraday, ya redondeado a 2 decimales.

    Args:
        vol_m: ratio de volumen de la vela completada (penúltima)
            contra la mediana de velas intradía del mismo día.
            Observatory devuelve `1.0` cuando hay menos de 3 velas
            completadas en el día (neutral). `None` sólo debería
            llegar si el caller aún no computó el indicador.

    Returns:
        Lista con 0 o 1 confirm.
    """
    if vol_m is None or vol_m <= _VOL_HIGH_RATIO_MIN:
        return []
    confirm: ConfirmDict = {
        "tf": "15M",
        "d": f"Vol {vol_m}x avg",
        "sg": "CONFIRM",
        "w": 2.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]


def detect_volume_sequence_confirm(vol_seq: dict | None) -> list[dict]:
    """Confirma VolSeq creciente cuando la secuencia de volúmenes crece.

    Observatory: `if ind["volSeqM"]["growing"]: ...`. La estructura
    `volSeqM` viene de `vol_sequence(candles_15m, n=4)` —
    `{"growing": bool, "declining": bool, "count": int}`. El
    detector expone el pattern con descripción `"Vol creciente {N+1}
    velas"` donde N es `count` (número de comparaciones que cumplen).

    Args:
        vol_seq: dict del indicador VolSeq, con las claves `growing`
            y `count`. `None` se trata como ausencia del indicador
            (no emite confirm).

    Returns:
        Lista con 0 o 1 confirm.
    """
    if vol_seq is None or not vol_seq.get("growing"):
        return []
    count = vol_seq.get("count", 0)
    confirm: ConfirmDict = {
        "tf": "15M",
        "d": f"Vol creciente {count + 1} velas",
        "sg": "CONFIRM",
        "w": 0.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]
