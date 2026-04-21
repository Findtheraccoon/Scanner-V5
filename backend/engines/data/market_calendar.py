"""Wrapper del calendario XNYS (NYSE) para el Data Engine.

Fuente: `exchange-calendars`. El calendario XNYS cubre US equities
listados en NYSE y NASDAQ (ambos siguen el mismo horario oficial).

Expone las primitivas que consume el motor:

    - `is_market_open(dt)`        — ¿abierto ese minuto?
    - `is_market_day(d)`          — ¿es día hábil de mercado?
    - `session_close(d)`          — cierre oficial de la sesión del día
    - `next_close(dt)`            — próximo cierre estrictamente posterior a dt
    - `previous_close(dt)`        — cierre anterior estrictamente previo a dt

Todos los inputs/outputs `datetime` son tz-aware (ADR-0002). Si llega
un datetime naive, se lanza `ValueError` — nunca se infiere zona.

Edge cases cubiertos por la lib:

    - Feriados US (New Year, MLK Day, Washington's Birthday, Good Friday,
      Memorial Day, Juneteenth, Independence Day, Labor Day, Thanksgiving,
      Christmas).
    - **Half-days**: typical cierre 13:00 ET (day after Thanksgiving,
      Christmas Eve, day before Independence Day cuando cae en día hábil).
    - DST transitions: manejadas por `zoneinfo` + `pandas`.

Rango temporal: `exchange-calendars` incluye sesiones ~20 años hacia
atrás y hacia adelante del año actual. Consultas fuera de rango
devolverán resultados indefinidos.

Boundary semantics (empíricas de `exchange_calendars`):

    - `is_market_open(close_time)` → False. El minuto del cierre no
      cuenta como abierto; el último minuto abierto es close-1min.
    - `previous_close(T)` devuelve el cierre más reciente ESTRICTAMENTE
      anterior a T. Ejemplo: `previous_close(Jan 2 16:00:01)` → Dec 31
      16:00 (porque Jan 2 16:00 no es "estrictamente anterior" al
      resolvente de minuto de la librería). Usar `next_close` al
      programar jobs de cierre para evitar este efecto.
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd

from engines.data.constants import ET

_CALENDAR_NAME = "XNYS"


@lru_cache(maxsize=1)
def _calendar() -> xcals.ExchangeCalendar:
    """Devuelve el calendario XNYS memoizado (construcción cara la primera vez)."""
    return xcals.get_calendar(_CALENDAR_NAME)


def _require_tz_aware(dt: datetime, param_name: str) -> None:
    if dt.tzinfo is None:
        raise ValueError(f"{param_name} must be tz-aware (ADR-0002). Got naive datetime: {dt!r}")


def _to_utc_ts(dt: datetime) -> pd.Timestamp:
    return pd.Timestamp(dt).tz_convert("UTC")


def _to_et_datetime(ts: pd.Timestamp) -> datetime:
    return ts.tz_convert(ET).to_pydatetime()


# ═══════════════════════════════════════════════════════════════════════════
# API pública
# ═══════════════════════════════════════════════════════════════════════════


def is_market_open(dt: datetime) -> bool:
    """True si el mercado de equities US está abierto en el minuto de `dt`.

    Args:
        dt: datetime tz-aware. Lanza ValueError si es naive.

    Returns:
        True solo dentro de RTH (9:30 ≤ t < close) de un día hábil.
        Pre-market y after-hours cuentan como cerrado.
    """
    _require_tz_aware(dt, "dt")
    return _calendar().is_open_on_minute(_to_utc_ts(dt), ignore_breaks=True)


def is_market_day(d: date) -> bool:
    """True si `d` es una fecha con sesión de mercado (no feriado, no weekend)."""
    session = pd.Timestamp(d)
    return session in _calendar().sessions


def session_close(d: date) -> datetime | None:
    """Datetime tz-aware ET del cierre oficial de la sesión de `d`.

    Args:
        d: fecha calendario en ET.

    Returns:
        - 16:00 ET en días regulares.
        - 13:00 ET en half-days (day after Thanksgiving, Christmas Eve,
          etc.).
        - `None` si `d` no es día de mercado.
    """
    if not is_market_day(d):
        return None
    return _to_et_datetime(_calendar().session_close(pd.Timestamp(d)))


def next_close(dt: datetime) -> datetime:
    """Próximo cierre de mercado ET estrictamente posterior a `dt`.

    Si `dt` cae durante RTH, devuelve el cierre de ese mismo día. Si cae
    fuera de RTH (o en feriado / fin de semana), devuelve el cierre del
    próximo día hábil.

    Args:
        dt: datetime tz-aware. Lanza ValueError si es naive.
    """
    _require_tz_aware(dt, "dt")
    return _to_et_datetime(_calendar().next_close(_to_utc_ts(dt)))


def previous_close(dt: datetime) -> datetime:
    """Cierre de mercado ET más reciente estrictamente anterior a `dt`.

    Útil para preguntas del tipo "¿cuándo fue el último reset diario?".

    Args:
        dt: datetime tz-aware. Lanza ValueError si es naive.
    """
    _require_tz_aware(dt, "dt")
    return _to_et_datetime(_calendar().previous_close(_to_utc_ts(dt)))
