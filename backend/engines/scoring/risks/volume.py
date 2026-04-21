"""Risks basados en volumen: rebote vol bajo + vol declinante.

Port literal de `docs/specs/Observatory/Current/scanner/patterns.py`
líneas 176-184.

Ambos se detectan cuando hay un **rebote** (close actual > close previo)
pero el volumen contradice la acción:

    Rebote vol bajo    — volume_ratio < 0.6   → w=-2.0
    Vol declinante     — secuencia declinante → w=-1.0

Los weights son informativos (H-04 eliminó las risk penalties del score).
Aparecen en `analyze()["patterns"]` como `cat="RISK"` y se muestran en
el output para trazabilidad / UI.
"""

from __future__ import annotations

_WEIGHT_LOW_VOL_BOUNCE: float = -2.0
_WEIGHT_DECLINING_VOL: float = -1.0
_LOW_VOL_THRESHOLD: float = 0.6


def detect_volume_risks_15m(
    candles_15m: list[dict],
    *,
    volume_ratio: float | None = None,
    volume_seq_declining: bool = False,
) -> list[dict]:
    """Detecta rebote vol bajo + vol declinante en el último 15M.

    Ambas condiciones requieren que la vela actual cierre POR ENCIMA de
    la previa (rebote). Sin rebote, no se emite nada.

    Args:
        candles_15m: lista de velas 15M antigua→reciente. Requiere ≥ 2.
        volume_ratio: ratio de volumen actual vs mediana intraday (volM
            del indicator). Si < 0.6, dispara "Rebote vol bajo".
            `None` deshabilita ese detector.
        volume_seq_declining: si la secuencia de volumen está en
            tendencia declinante (Observatory `volSeqM.declining`). Si
            True, dispara "Vol declinante en rebote".

    Returns:
        Lista de `RiskDict` con `cat="RISK"`, `sg="WARN"`, `w` negativo.
    """
    risks: list[dict] = []
    if len(candles_15m) < 2:
        return risks

    curr = candles_15m[-1]
    prev = candles_15m[-2]

    # Ambos risks requieren rebote (close actual > close previo).
    if not (curr["c"] > prev["c"]):
        return risks

    if volume_ratio is not None and volume_ratio < _LOW_VOL_THRESHOLD:
        risks.append(
            {
                "tf": "15M",
                "d": f"Rebote vol bajo ({volume_ratio}x)",
                "sg": "WARN",
                "w": _WEIGHT_LOW_VOL_BOUNCE,
                "cat": "RISK",
                "age": 0,
            }
        )

    if volume_seq_declining:
        risks.append(
            {
                "tf": "15M",
                "d": "Vol declinante en rebote",
                "sg": "WARN",
                "w": _WEIGHT_DECLINING_VOL,
                "cat": "RISK",
                "age": 0,
            }
        )

    return risks
