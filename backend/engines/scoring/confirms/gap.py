"""Confirm de Gap — 1 del total (Gap alcista/bajista).

Portado de `docs/specs/Observatory/Current/scanner/engine.py` líneas
161-174. Se dispara cuando el indicador `gap` del día (open vs cierre
previo) es "significativo" (> 0.5 x ATR del daily).

**Señal de dirección:** `CALL` si `dir == "bullish"`, `PUT` si `bearish`.

**Paridad crítica — descripción:**
    bullish  → `f"Gap alcista {+|''}{pct}%"`  (siempre se prepone "+"
                                               cuando pct > 0)
    bearish  → `f"Gap bajista {pct}%"`        (el signo "-" ya viene
                                               dentro del pct)

El `_categorize_confirm` mapea `desc.startswith("Gap")` → Gap. El
valor numérico del porcentaje se compara bit-a-bit contra el sample
canonical, así que cualquier cambio de formato rompe paridad.

**Peso informativo (v4.2.1):** 1. En v5 el fixture pondera Gap=1
también.
"""

from __future__ import annotations

from engines.scoring.confirms._helpers import ConfirmDict


def detect_gap_confirm(gap_info: dict | None) -> list[dict]:
    """Confirma Gap cuando el gap del día es significativo.

    Observatory: `if ind["gap"] and ind["gap"]["significant"]: ...`.
    El dict `gap` viene del indicador `gap()`, con forma::

        {"pct": float, "significant": bool, "dir": "bullish"|"bearish"}

    Args:
        gap_info: dict del indicador Gap, o `None` si la serie daily
            no tiene suficientes velas para calcular gap (no emite
            confirm).

    Returns:
        Lista con 0 o 1 confirm.
    """
    if gap_info is None or not gap_info.get("significant"):
        return []

    pct = gap_info["pct"]
    direction = gap_info.get("dir")

    if direction == "bullish":
        sign = "+" if pct > 0 else ""
        confirm: ConfirmDict = {
            "tf": "D",
            "d": f"Gap alcista {sign}{pct}%",
            "sg": "CALL",
            "w": 1.0,
            "cat": "CONFIRM",
            "age": 0,
        }
        return [dict(confirm)]

    # bearish — el signo "-" ya viene dentro del valor del pct
    confirm = {
        "tf": "D",
        "d": f"Gap bajista {pct}%",
        "sg": "PUT",
        "w": 1.0,
        "cat": "CONFIRM",
        "age": 0,
    }
    return [dict(confirm)]
