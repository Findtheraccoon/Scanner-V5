"""Tests del wrapper de `exchange_calendars` para XNYS.

Usamos fechas conocidas y estables para no depender de "ahora":

    - 2025-01-02 (jueves) → día regular, close 16:00 ET
    - 2025-01-03 (viernes) → día regular
    - 2025-01-04 (sábado) → weekend
    - 2025-01-01 → New Year's Day (feriado)
    - 2024-12-25 → Christmas (feriado)
    - 2024-12-24 → Christmas Eve (half-day, close 13:00 ET)
    - 2024-11-29 → day after Thanksgiving (half-day, close 13:00 ET)
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from engines.data.constants import ET
from engines.data.market_calendar import (
    is_market_day,
    is_market_open,
    next_close,
    previous_close,
    session_close,
)

# ═══════════════════════════════════════════════════════════════════════════
# is_market_open
# ═══════════════════════════════════════════════════════════════════════════


class TestIsMarketOpen:
    def test_open_during_rth_regular_day(self) -> None:
        assert is_market_open(datetime(2025, 1, 2, 10, 0, tzinfo=ET)) is True
        assert is_market_open(datetime(2025, 1, 2, 15, 59, tzinfo=ET)) is True

    def test_closed_before_rth(self) -> None:
        assert is_market_open(datetime(2025, 1, 2, 9, 29, tzinfo=ET)) is False

    def test_closed_at_open_minute_is_open(self) -> None:
        # 9:30 es el primer minuto abierto.
        assert is_market_open(datetime(2025, 1, 2, 9, 30, tzinfo=ET)) is True

    def test_closed_at_exact_close_time(self) -> None:
        # Empírico: 16:00 exacto NO cuenta como abierto (el último
        # minuto abierto es 15:59).
        assert is_market_open(datetime(2025, 1, 2, 16, 0, tzinfo=ET)) is False

    def test_closed_after_hours(self) -> None:
        assert is_market_open(datetime(2025, 1, 2, 20, 0, tzinfo=ET)) is False

    def test_closed_saturday(self) -> None:
        assert is_market_open(datetime(2025, 1, 4, 12, 0, tzinfo=ET)) is False

    def test_closed_sunday(self) -> None:
        assert is_market_open(datetime(2025, 1, 5, 12, 0, tzinfo=ET)) is False

    def test_closed_holiday_new_years(self) -> None:
        assert is_market_open(datetime(2025, 1, 1, 12, 0, tzinfo=ET)) is False

    def test_closed_holiday_christmas(self) -> None:
        assert is_market_open(datetime(2024, 12, 25, 12, 0, tzinfo=ET)) is False

    def test_open_before_half_day_close(self) -> None:
        # 29 nov 2024 es day after Thanksgiving → cierre 13:00 ET.
        assert is_market_open(datetime(2024, 11, 29, 12, 30, tzinfo=ET)) is True

    def test_closed_after_half_day_close(self) -> None:
        assert is_market_open(datetime(2024, 11, 29, 13, 30, tzinfo=ET)) is False

    def test_raises_on_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            is_market_open(datetime(2025, 1, 2, 10, 0))


# ═══════════════════════════════════════════════════════════════════════════
# is_market_day
# ═══════════════════════════════════════════════════════════════════════════


class TestIsMarketDay:
    def test_true_for_regular_weekday(self) -> None:
        assert is_market_day(date(2025, 1, 2)) is True

    def test_false_for_saturday(self) -> None:
        assert is_market_day(date(2025, 1, 4)) is False

    def test_false_for_sunday(self) -> None:
        assert is_market_day(date(2025, 1, 5)) is False

    def test_false_for_new_years(self) -> None:
        assert is_market_day(date(2025, 1, 1)) is False

    def test_false_for_christmas(self) -> None:
        assert is_market_day(date(2024, 12, 25)) is False

    def test_true_for_half_day(self) -> None:
        # Half-days siguen siendo market days.
        assert is_market_day(date(2024, 11, 29)) is True
        assert is_market_day(date(2024, 12, 24)) is True


# ═══════════════════════════════════════════════════════════════════════════
# session_close
# ═══════════════════════════════════════════════════════════════════════════


class TestSessionClose:
    def test_regular_day_closes_at_16_et(self) -> None:
        close = session_close(date(2025, 1, 2))
        assert close is not None
        assert close == datetime(2025, 1, 2, 16, 0, tzinfo=ET)

    def test_half_day_closes_at_13_et(self) -> None:
        close = session_close(date(2024, 11, 29))
        assert close is not None
        assert close == datetime(2024, 11, 29, 13, 0, tzinfo=ET)

    def test_christmas_eve_half_day(self) -> None:
        close = session_close(date(2024, 12, 24))
        assert close is not None
        assert close == datetime(2024, 12, 24, 13, 0, tzinfo=ET)

    def test_weekend_returns_none(self) -> None:
        assert session_close(date(2025, 1, 4)) is None

    def test_holiday_returns_none(self) -> None:
        assert session_close(date(2025, 1, 1)) is None
        assert session_close(date(2024, 12, 25)) is None

    def test_close_is_tz_aware_in_et(self) -> None:
        close = session_close(date(2025, 1, 2))
        assert close is not None
        assert close.tzinfo is not None
        # Debe ser ET específicamente — el motor consume solo ET.
        assert close.utcoffset() == datetime(2025, 1, 2, tzinfo=ET).utcoffset()


# ═══════════════════════════════════════════════════════════════════════════
# next_close
# ═══════════════════════════════════════════════════════════════════════════


class TestNextClose:
    def test_mid_session_returns_same_day_close(self) -> None:
        result = next_close(datetime(2025, 1, 2, 10, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 2, 16, 0, tzinfo=ET)

    def test_after_close_returns_next_session(self) -> None:
        # Jueves 17:00 → próximo close es viernes 16:00
        result = next_close(datetime(2025, 1, 2, 17, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 3, 16, 0, tzinfo=ET)

    def test_friday_evening_returns_monday_close(self) -> None:
        # Viernes 2025-01-03 17:00 → lunes 2025-01-06 16:00
        result = next_close(datetime(2025, 1, 3, 17, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 6, 16, 0, tzinfo=ET)

    def test_saturday_returns_monday_close(self) -> None:
        result = next_close(datetime(2025, 1, 4, 12, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 6, 16, 0, tzinfo=ET)

    def test_during_half_day_returns_early_close(self) -> None:
        result = next_close(datetime(2024, 11, 29, 10, 0, tzinfo=ET))
        assert result == datetime(2024, 11, 29, 13, 0, tzinfo=ET)

    def test_raises_on_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            next_close(datetime(2025, 1, 2, 10, 0))


# ═══════════════════════════════════════════════════════════════════════════
# previous_close
# ═══════════════════════════════════════════════════════════════════════════


class TestPreviousClose:
    def test_next_morning_returns_prior_day_close(self) -> None:
        # Viernes 2025-01-03 08:00 → jueves 2025-01-02 16:00
        result = previous_close(datetime(2025, 1, 3, 8, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 2, 16, 0, tzinfo=ET)

    def test_after_close_same_day(self) -> None:
        # Jueves 17:00 → mismo día 16:00 (suficiente tiempo tras close)
        result = previous_close(datetime(2025, 1, 2, 17, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 2, 16, 0, tzinfo=ET)

    def test_monday_morning_returns_prior_friday_close(self) -> None:
        # Lunes 2025-01-06 08:00 → viernes 2025-01-03 16:00
        result = previous_close(datetime(2025, 1, 6, 8, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 3, 16, 0, tzinfo=ET)

    def test_tuesday_after_holiday_weekend(self) -> None:
        # New Year 2025 cae miércoles. Jueves 2 es primer día.
        # Viernes 3 morning → jueves 2 cierre.
        result = previous_close(datetime(2025, 1, 3, 8, 0, tzinfo=ET))
        assert result == datetime(2025, 1, 2, 16, 0, tzinfo=ET)

    def test_raises_on_naive_datetime(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            previous_close(datetime(2025, 1, 2, 17, 0))
