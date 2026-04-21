"""Triggers de vela en 15M — 8 del total (port del Observatory).

Portados de `docs/specs/Observatory/Current/scanner/patterns.py` líneas
38-102 (el loop 15M con decay). Cada trigger materializa un
`TriggerDict` con la forma canónica que el scanner v5 consume.

Triggers cubiertos:

    Doji BB sup      — body < 12% del rango + high toca banda superior  (age=0)
    Doji BB inf      — body < 12% del rango + low toca banda inferior   (age=0)
    Hammer           — lower_wick > 2*body, upper_wick < 0.5*body, near lower BB (age=0)
    Shooting Star    — mirror de Hammer (upper wick dominante, near upper BB)   (age=0)
    Rechazo sup      — upper_wick/range > 60%                       (cualquier age, decay)
    Rechazo inf      — lower_wick/range > 60%                       (cualquier age, decay)
    Envolvente alcista — curr bull tras prev bear, body > 1.1 prev  (cualquier age, decay)
    Envolvente bajista — espejo del alcista                         (cualquier age, decay)

Los 4 BB-dependientes solo disparan en `age=0`; los 2 Rechazos y los 2
Envolventes 15M disparan a cualquier edad en las últimas velas con
`weight = peso_base * decay_weight(age)`.

**Range del loop (paridad Observatory):**

Observatory itera `range(min(5, len(candles_15m) - 1))` — necesita
siempre una vela previa `pv` para los Envolventes, por eso el `- 1`.
Si la lista tiene 1 vela, no se itera. Portamos ese comportamiento
literal para paridad bit-a-bit con el sample.

**Importante — BB "actuales" vs históricas:** el trío (upper, middle,
lower) se computa una sola vez sobre toda la serie 15M hasta la última
vela, y se compara contra la `h`/`l` de cada vela del loop. Así lo
hace Observatory y así se calibró el canonical QQQ.
"""

from __future__ import annotations

from engines.scoring.triggers._helpers import (
    age_label,
    candle_body,
    candle_range,
    decay_weight,
    is_bull,
    lower_wick,
    upper_wick,
)

# ───────────────────────────────────────────────────────────────────────────
# Umbrales hardcoded (Observatory / v4.2.1). Cambiarlos rompe paridad.
# ───────────────────────────────────────────────────────────────────────────
_DOJI_BODY_RATIO_MAX: float = 0.12
_REJECTION_WICK_RATIO_MIN: float = 0.6
_HAMMER_LW_OVER_BODY_MIN: float = 2.0
_HAMMER_UW_OVER_BODY_MAX: float = 0.5
_DOJI_BB_TOLERANCE: float = 0.002
_HAMMER_BB_TOLERANCE: float = 0.005
_SHOOTING_BB_TOLERANCE: float = 0.005
_ENGULF_BODY_RATIO_MIN: float = 1.1

# ───────────────────────────────────────────────────────────────────────────
# Pesos base (Observatory spec §5.1).
# ───────────────────────────────────────────────────────────────────────────
_WEIGHT_DOJI: float = 2.0
_WEIGHT_REJECTION: float = 2.0
_WEIGHT_HAMMER: float = 2.0
_WEIGHT_SHOOTING: float = 2.0
_WEIGHT_ENGULFING_15M: float = 3.0

_MAX_AGE_DEFAULT: int = 4  # edades 0..4, hasta 5 velas


def detect_candle_15m_triggers(
    candles_15m: list[dict],
    bb_15m: tuple[float, float, float] | None = None,
    *,
    max_age: int = _MAX_AGE_DEFAULT,
) -> list[dict]:
    """Detecta triggers de vela 15M en las últimas `max_age + 1` velas.

    Args:
        candles_15m: lista de velas 15M antigua→reciente (formato del spec
            §2.2).
        bb_15m: tupla `(upper, middle, lower)` de Bollinger sobre la
            serie 15M hasta la última vela. `None` deshabilita los 4
            triggers BB-dependientes.
        max_age: edad máxima a revisar (default 4 → ages 0..4).

    Returns:
        Lista de `TriggerDict`. Puede estar vacía si no hay suficiente
        historia (requiere ≥ 2 velas para cualquier trigger, por el
        `range(min(max_age + 1, n - 1))` que porta Observatory).
    """
    triggers: list[dict] = []
    if not candles_15m:
        return triggers

    n = len(candles_15m)
    # Observatory: `range(min(5, len - 1))`. Necesita siempre pv disponible.
    ages_to_check = min(max_age + 1, n - 1)
    if ages_to_check <= 0:
        return triggers

    bb_upper = bb_15m[0] if bb_15m is not None else None
    bb_lower = bb_15m[2] if bb_15m is not None else None

    for age in range(ages_to_check):
        idx = n - 1 - age
        cnd = candles_15m[idx]
        pv = candles_15m[idx - 1]  # seguro: ages_to_check <= n - 1
        rng = candle_range(cnd)
        if rng <= 0:
            continue
        body = candle_body(cnd)
        u_wick = upper_wick(cnd)
        l_wick = lower_wick(cnd)
        bull = is_bull(cnd)
        decay = decay_weight(age)
        age_lbl = age_label(age)

        # ─── Doji BB sup / inf — solo age=0, body pequeño ───
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

        # ─── Rechazos sup/inf — cualquier age, con decay ───
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

        # ─── Hammer / Shooting Star — solo age=0, BB-dependientes ───
        # Con body=0, las condiciones `uW < body*0.5` y `lW < body*0.5` se
        # reducen a `< 0` (falso — mechas nunca son negativas). Por eso
        # no hace falta guard explícito.
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

        # ─── Envolvente 15M alcista/bajista — cualquier age, con decay ───
        # Observatory patterns.py líneas 91-102. Note: description sin
        # "1H" suffix (eso distingue el Envolvente 1H del 15M).
        pv_body = candle_body(pv)
        pv_bull = is_bull(pv)
        if (
            bull
            and not pv_bull
            and cnd["o"] <= pv["c"]
            and cnd["c"] >= pv["o"]
            and body > pv_body * _ENGULF_BODY_RATIO_MIN
        ):
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Envolvente alcista{age_lbl}",
                    "sg": "CALL",
                    "w": round(_WEIGHT_ENGULFING_15M * decay, 1),
                    "cat": "TRIGGER",
                    "age": age,
                }
            )
        if (
            not bull
            and pv_bull
            and cnd["o"] >= pv["c"]
            and cnd["c"] <= pv["o"]
            and body > pv_body * _ENGULF_BODY_RATIO_MIN
        ):
            triggers.append(
                {
                    "tf": "15M",
                    "d": f"Envolvente bajista{age_lbl}",
                    "sg": "PUT",
                    "w": round(_WEIGHT_ENGULFING_15M * decay, 1),
                    "cat": "TRIGGER",
                    "age": age,
                }
            )

    return triggers
