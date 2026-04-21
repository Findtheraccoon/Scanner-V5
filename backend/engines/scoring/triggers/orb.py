"""ORB (Opening Range Breakout) breakout/breakdown — 2 triggers del total de 14.

Port de scanner_v4.2.1.html líneas 302-316 (cálculo de niveles) + 640-648
(triggers). Agrega el time gate "≤ 10:30 ET" que v5 requiere explícitamente
(spec §3 I5 item 4).

Definición del ORB:

    Opening Range = máximo y mínimo de las **primeras 2 velas 15M del día**
    (9:30-10:00 ET en un día regular → ventana de 30 minutos).

    breakUp  si close_actual > ORB_high
    breakDown si close_actual < ORB_low

Cuándo dispara en v5:

    1. Debe ser ≤ 10:30 ET (spec §3 I5). Se consulta `sim_datetime` si
       el caller lo provee, else el `dt` de la última vela 15M.
    2. (v4.2.1) Se respeta el filtro volumétrico opcional `volM >= 1.0`
       para mantener paridad con el canonical QQQ. El caller pasa
       `volume_ratio=volM` computado con volumen relativo a mediana
       reciente; si no lo pasa, el filtro se salta.

Weight: 2.0, age: 0 (nunca decay — ORB es solo de la vela actual).
"""

from __future__ import annotations

_WEIGHT_ORB: float = 2.0
_ORB_CUTOFF_SECONDS: int = 10 * 3600 + 30 * 60  # 10:30:00 ET = 37800 s
_ORB_VOL_MIN: float = 1.0  # v4.2.1


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
    """Detecta ORB breakout / breakdown con time gate 10:30 ET.

    Args:
        candles_15m: velas 15M antigua→reciente. Mínimo 10.
        volume_ratio: ratio de volumen actual vs promedio reciente
            (`volume_ratio_at` del módulo indicators). Si < 1.0, el
            trigger se suprime para mantener paridad con v4.2.1. Si
            `None`, el filtro se salta.
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
    """True si el time-component de `dt_str` es ≤ 10:30:00 (ET asumido).

    Semántica del spec §3 I5: ORB solo válido ≤ 10:30 ET. Inclusivo de
    10:30:00 exacto.

    Conservadoramente devuelve False si no se puede parsear el time
    (no queremos disparar ORB de forma incontrolada cuando el
    timestamp está roto).
    """
    if not dt_str:
        return False
    if " " in dt_str:
        _, time_part = dt_str.split(" ", 1)
    elif "T" in dt_str:
        _, time_part = dt_str.split("T", 1)
    else:
        return False  # sin time-component no se puede validar
    parts = time_part.split(":")
    if len(parts) < 2:
        return False
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2]) if len(parts) >= 3 else 0
    except ValueError:
        return False
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds <= _ORB_CUTOFF_SECONDS
