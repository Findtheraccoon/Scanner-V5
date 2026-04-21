"""Triggers de vela individual en 15M — 6 del total de 14.

Portados de `scanner_v4.2.1.html` líneas 408-417. Cada trigger
materializa un `TriggerDict` con la forma canónica del v4.2.1 para
mantener paridad con el canonical QQQ.

Triggers cubiertos:

    Doji BB sup   — body < 12% del rango + high toca banda superior  (age=0)
    Doji BB inf   — body < 12% del rango + low toca banda inferior   (age=0)
    Hammer        — lower_wick > 2*body, upper_wick < 0.5*body, near lower BB (age=0)
    Shooting Star — mirror de Hammer (upper wick dominante, near upper BB)   (age=0)
    Rechazo sup   — upper_wick/range > 60%                      (cualquier age, decay)
    Rechazo inf   — lower_wick/range > 60%                      (cualquier age, decay)

Los 4 primeros solo disparan en `age=0` (la vela más reciente) y
requieren BB Bollinger cargado; los 2 Rechazos disparan a cualquier
edad en los últimos 5 velas, con `weight = 2.0 * decay_weight(age)`.

**Importante (paridad con v4.2.1):** los BB que se consultan son los
"actuales" — un único trío (upper, middle, lower) computado sobre toda
la serie 15M hasta la vela más reciente. Se comparan contra la `h`/`l`
de cada vela en el loop, no contra los BB "contemporáneos" de esa vela.
Así se porta del HTML y es una rareza deliberada que el canonical QQQ
fue calibrado asumiendo.
"""

from __future__ import annotations

from engines.scoring.triggers._helpers import (
    age_label,
    candle_body,
    candle_range,
    decay_weight,
    lower_wick,
    upper_wick,
)

# Umbrales — hardcoded en v4.2.1. Cambiarlos rompe paridad.
_DOJI_BODY_RATIO_MAX: float = 0.12
_REJECTION_WICK_RATIO_MIN: float = 0.6
_HAMMER_LW_OVER_BODY_MIN: float = 2.0
_HAMMER_UW_OVER_BODY_MAX: float = 0.5
_DOJI_BB_TOLERANCE: float = 0.002  # 0.2% desde banda
_HAMMER_BB_TOLERANCE: float = 0.005  # 0.5% desde banda
_SHOOTING_BB_TOLERANCE: float = 0.005  # 0.5% desde banda superior

# Pesos base — hardcoded en v4.2.1 spec §5.1.
_WEIGHT_DOJI: float = 2.0
_WEIGHT_REJECTION: float = 2.0
_WEIGHT_HAMMER: float = 2.0
_WEIGHT_SHOOTING: float = 2.0

# Cuántas velas hacia atrás chequear (v4.2.1 usa min(5, len-1)).
_MAX_AGE_DEFAULT: int = 4  # edades 0..4, 5 velas total


def detect_candle_15m_triggers(
    candles_15m: list[dict],
    bb_15m: tuple[float, float, float] | None = None,
    *,
    max_age: int = _MAX_AGE_DEFAULT,
) -> list[dict]:
    """Detecta triggers de vela individual en 15M.

    Args:
        candles_15m: lista de velas 15M antigua→reciente (formato del spec
            §2.2). Mínimo 1.
        bb_15m: tupla `(upper, middle, lower)` de Bollinger sobre la
            serie 15M hasta la última vela. `None` deshabilita los 4
            triggers BB-dependientes (Doji, Hammer, Shooting).
        max_age: edad máxima a revisar para Rechazos (ventana por
            defecto 4 → últimas 5 velas). Por compatibilidad con
            v4.2.1.

    Returns:
        Lista de `TriggerDict` en el orden en que se detectan. Puede
        estar vacía. No filtra por dirección — retorna CALLs y PUTs
        juntos.
    """
    triggers: list[dict] = []
    if not candles_15m:
        return triggers

    n = len(candles_15m)
    ages_to_check = min(max_age + 1, n)
    bb_upper = bb_15m[0] if bb_15m is not None else None
    bb_lower = bb_15m[2] if bb_15m is not None else None

    for age in range(ages_to_check):
        idx = n - 1 - age
        cnd = candles_15m[idx]
        rng = candle_range(cnd)
        if rng <= 0:
            continue
        body = candle_body(cnd)
        u_wick = upper_wick(cnd)
        l_wick = lower_wick(cnd)
        decay = decay_weight(age)
        age_lbl = age_label(age)

        # Doji BB sup / inf — solo age=0, body pequeño relativo al rango
        if age == 0 and bb_15m is not None and body / rng < _DOJI_BODY_RATIO_MAX:
            if bb_upper is not None and cnd["h"] >= bb_upper * (1 - _DOJI_BB_TOLERANCE):
                triggers.append(
                    {
                        "tf": "15M",
                        "d": "Doji BB sup",
                        "sg": "PUT",
                        "w": _WEIGHT_DOJI,
                        "cat": "TRIGGER",
                        "age": 0,
                    }
                )
            if bb_lower is not None and cnd["l"] <= bb_lower * (1 + _DOJI_BB_TOLERANCE):
                triggers.append(
                    {
                        "tf": "15M",
                        "d": "Doji BB inf",
                        "sg": "CALL",
                        "w": _WEIGHT_DOJI,
                        "cat": "TRIGGER",
                        "age": 0,
                    }
                )

        # Rechazos sup/inf — cualquier age, con decay
        if u_wick / rng > _REJECTION_WICK_RATIO_MIN:
            pct = round(u_wick / rng * 100)
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Rechazo sup {pct}%{age_lbl}",
                    "sg": "PUT",
                    "w": round(_WEIGHT_REJECTION * decay, 1),
                    "cat": "TRIGGER",
                    "age": age,
                }
            )
        if l_wick / rng > _REJECTION_WICK_RATIO_MIN:
            pct = round(l_wick / rng * 100)
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Rechazo inf {pct}%{age_lbl}",
                    "sg": "CALL",
                    "w": round(_WEIGHT_REJECTION * decay, 1),
                    "cat": "TRIGGER",
                    "age": age,
                }
            )

        # Hammer / Shooting Star — solo age=0, BB-dependientes.
        # Nota: con body=0 las condiciones `uW < body*0.5` y `lW < body*0.5`
        # se reducen a `uW < 0` y `lW < 0`, que son siempre falsas (las
        # mechas nunca son negativas). Por eso no hace falta guardar
        # contra body=0 explícitamente — la inequality ya lo excluye.
        if age == 0 and bb_15m is not None:
            if (
                bb_lower is not None
                and l_wick > body * _HAMMER_LW_OVER_BODY_MIN
                and u_wick < body * _HAMMER_UW_OVER_BODY_MAX
                and cnd["l"] <= bb_lower * (1 + _HAMMER_BB_TOLERANCE)
            ):
                triggers.append(
                    {
                        "tf": "15M",
                        "d": "Hammer",
                        "sg": "CALL",
                        "w": _WEIGHT_HAMMER,
                        "cat": "TRIGGER",
                        "age": 0,
                    }
                )
            if (
                bb_upper is not None
                and u_wick > body * _HAMMER_LW_OVER_BODY_MIN
                and l_wick < body * _HAMMER_UW_OVER_BODY_MAX
                and cnd["h"] >= bb_upper * (1 - _SHOOTING_BB_TOLERANCE)
            ):
                triggers.append(
                    {
                        "tf": "15M",
                        "d": "Shooting Star",
                        "sg": "PUT",
                        "w": _WEIGHT_SHOOTING,
                        "cat": "TRIGGER",
                        "age": 0,
                    }
                )

    return triggers
