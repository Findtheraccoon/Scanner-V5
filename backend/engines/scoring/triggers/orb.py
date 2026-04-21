"""ORB (Opening Range Breakout) breakout/breakdown — 2 triggers del total de 14.

Port del motor del Observatory (`docs/specs/Observatory/Current/scanner/
engine.py` líneas 191-204 + `indicators.py` función `orb()`).

Un ORB se define como el high/low de las **primeras 2 velas 15M del
día**. Un close actual que supera el high → breakout (CALL). Un close
debajo del low → breakdown (PUT).

**Gates aplicados al trigger (ambos del Observatory):**

    1. **Time gate** — solo válido ≤ 10:30 ET (spec §3 I5 item 4).
       Port literal de Observatory: slice `dt_str[11:16]` + comparación
       string contra `"10:30"`. Los segundos se ignoran — `"10:30:59"`
       → `"10:30"` → válido. Usa `sim_datetime` si lo provee el caller,
       else `dt` de la última vela.

    2. **Volume gate** — `volume_ratio >= 1.0`. Este es un GATE BINARIO
       (fire / no fire), NO un weight del score. El hallazgo H-02
       ("volumen sale del score") se refiere al `volMult` que
       multiplicaba el score, no a este gate binario. Observatory
       mantiene este filtro en engine.py. Si `volume_ratio=None`, el
       filtro se omite — útil para tests o callers que no computen
       volumen.

Weight: 2.0, age: 0, sin decay.
"""

from __future__ import annotations

_WEIGHT_ORB: float = 2.0
_ORB_CUTOFF_HHMM: str = "10:30"  # Observatory string compare — ver _is_orb_time_valid
_ORB_VOL_MIN: float = 1.0  # gate binario — paridad con Observatory


def compute_orb_levels(candles_15m: list[dict]) -> dict | None:
    """Computa `{high, low, breakUp, breakDown}` del ORB del día actual.

    Args:
        candles_15m: velas 15M antigua→reciente. Se considera "hoy" a
            la fecha de la última vela; se filtra la lista entera
            quedándose con las velas cuyo `dt` empieza igual.

    Returns:
        `None` si no se puede computar (pocas velas, falta `dt`, menos
        de 3 velas del día, etc.). Si OK, dict con:
            high      — máximo entre h de las primeras 2 velas de hoy
            low       — mínimo entre l de las primeras 2 velas de hoy
            breakUp   — True si close_actual > high
            breakDown — True si close_actual < low
    """
    if not candles_15m or len(candles_15m) < 10:
        return None
    last_dt = candles_15m[-1].get("dt")
    if not last_dt:
        return None
    # Extraer la parte de fecha — acepta tanto "YYYY-MM-DD HH:MM:SS"
    # como "YYYY-MM-DDTHH:MM:SS" (ISO 8601).
    if " " in last_dt:
        today = last_dt.split(" ", 1)[0]
    elif "T" in last_dt:
        today = last_dt.split("T", 1)[0]
    else:
        today = last_dt

    today_candles = [c for c in candles_15m if c.get("dt") and c["dt"].startswith(today)]
    if len(today_candles) < 3:
        return None

    first_two = today_candles[:2]
    orb_high = max(first_two[0]["h"], first_two[1]["h"])
    orb_low = min(first_two[0]["l"], first_two[1]["l"])
    current = candles_15m[-1]
    return {
        "high": round(orb_high, 2),
        "low": round(orb_low, 2),
        "breakUp": current["c"] > orb_high,
        "breakDown": current["c"] < orb_low,
    }


def detect_orb_triggers_15m(
    candles_15m: list[dict],
    *,
    volume_ratio: float | None = None,
    sim_datetime: str | None = None,
) -> list[dict]:
    """Detecta ORB breakout / breakdown con time gate + volume gate.

    Args:
        candles_15m: velas 15M antigua→reciente. Mínimo 10.
        volume_ratio: ratio de volumen de la vela actual vs mediana de
            las velas completadas del mismo día. Si < 1.0, el trigger
            se suprime (gate binario, no es un weight). Si es `None`,
            el filtro se omite.
        sim_datetime: timestamp "YYYY-MM-DD HH:MM:SS" ET usado por el
            Validator/Observatory. Si es `None`, se usa el `dt` de la
            última vela. Nunca se usa la hora del reloj del sistema.

    Returns:
        Lista con 0, 1 o 2 `TriggerDict`. Una vela puede disparar a lo
        sumo 1 ORB trigger (break arriba O abajo, no ambos), pero 2 es
        posible en casos artificiales construidos en tests.
    """
    current_dt = sim_datetime
    if current_dt is None and candles_15m:
        current_dt = candles_15m[-1].get("dt")

    if not _is_orb_time_valid(current_dt):
        return []

    if volume_ratio is not None and volume_ratio < _ORB_VOL_MIN:
        return []

    orb = compute_orb_levels(candles_15m)
    if orb is None:
        return []

    triggers: list[dict] = []
    if orb["breakUp"]:
        triggers.append(
            {
                "tf": "15M",
                "d": f"ORB breakout ${orb['high']:.2f}",
                "sg": "CALL",
                "w": _WEIGHT_ORB,
                "cat": "TRIGGER",
                "age": 0,
            }
        )
    if orb["breakDown"]:
        triggers.append(
            {
                "tf": "15M",
                "d": f"ORB breakdown ${orb['low']:.2f}",
                "sg": "PUT",
                "w": _WEIGHT_ORB,
                "cat": "TRIGGER",
                "age": 0,
            }
        )
    return triggers


# ═══════════════════════════════════════════════════════════════════════════
# Time gate
# ═══════════════════════════════════════════════════════════════════════════


def _is_orb_time_valid(dt_str: str | None) -> bool:
    """True si la parte "HH:MM" de `dt_str` es ≤ "10:30" (string compare).

    Port literal del Observatory `engine.py` líneas 184-185:

        _hhmm = sim_datetime[11:16]      # "HH:MM" de "YYYY-MM-DD HH:MM:SS"
        _orb_in_first_hour = _hhmm <= "10:30"

    El slice [11:16] funciona para ambos separadores (" " o "T") porque
    el carácter 10 es irrelevante. **Los segundos se ignoran por completo** —
    `"10:30:30"` → `"10:30"` → válido. Inclusivo de `"10:30"` exacto.

    Divergencias con Observatory:

        - `dt_str = None`     → Mío: False. Observatory: True (permite ORB
                                 en live mode sin sim_datetime). Mi elección
                                 es conservadora: sin info de tiempo, no
                                 dispara.
        - Parse falla         → Mío: False. Observatory: True (fallback
                                 laxo). Mismo argumento.

    En backtest contra el sample (sim_datetime siempre "YYYY-MM-DD HH:MM:SS"
    válido), ambas semánticas convergen.
    """
    if dt_str is None:
        return False
    try:
        hhmm = dt_str[11:16]
        # Validación mínima: "HH:MM" tiene longitud 5 con ":" en índice 2.
        if len(hhmm) != 5 or hhmm[2] != ":":
            return False
        return hhmm <= _ORB_CUTOFF_HHMM
    except (IndexError, TypeError):
        return False
