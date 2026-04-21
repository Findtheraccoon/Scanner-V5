"""Tests de `check_integrity()` del Data Engine.

Cubren los casos que el verificador debe detectar y los que debe dejar
pasar como válidos. La función acumula TODOS los issues — los tests
chequean tanto presencia de codes específicos como su ausencia.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from engines.data.constants import ET
from engines.data.integrity import check_integrity
from engines.data.models import Candle, Timeframe

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _candle(
    dt: datetime,
    *,
    o: float = 100.0,
    h: float = 101.0,
    l: float = 99.0,  # noqa: E741
    c: float = 100.5,
    v: int = 1000,
) -> Candle:
    return Candle(dt=dt, o=o, h=h, l=l, c=c, v=v)


def _make_valid_series(
    start: datetime,
    count: int,
    step: timedelta,
) -> list[Candle]:
    """Genera una serie consecutiva válida antigua→reciente."""
    return [_candle(start + step * i) for i in range(count)]


# Base datetimes usados por los tests — ET tz-aware (ADR-0002).
_T0 = datetime(2025, 3, 10, 9, 30, tzinfo=ET)


# ═══════════════════════════════════════════════════════════════════════════
# Feliz
# ═══════════════════════════════════════════════════════════════════════════


class TestValidCandles:
    def test_exactly_min_m15_passes(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        result = check_integrity(series, Timeframe.M15)
        assert result.ok is True
        assert result.notes == []
        assert result.checked_count == 25
        assert result.timeframe == Timeframe.M15

    def test_more_than_min_passes(self) -> None:
        series = _make_valid_series(_T0, 80, timedelta(hours=1))
        result = check_integrity(series, Timeframe.H1)
        assert result.ok is True

    def test_daily_minimum_40_passes(self) -> None:
        series = _make_valid_series(_T0, 40, timedelta(days=1))
        result = check_integrity(series, Timeframe.DAILY)
        assert result.ok is True


# ═══════════════════════════════════════════════════════════════════════════
# Cantidad mínima
# ═══════════════════════════════════════════════════════════════════════════


class TestCountValidation:
    def test_empty_list_fails_with_empty_note(self) -> None:
        result = check_integrity([], Timeframe.M15)
        assert result.ok is False
        assert any(n.startswith("empty:") for n in result.notes)
        assert result.checked_count == 0

    def test_fewer_than_min_m15_fails(self) -> None:
        series = _make_valid_series(_T0, 10, timedelta(minutes=15))
        result = check_integrity(series, Timeframe.M15)
        assert result.ok is False
        assert any("too_few_candles" in n for n in result.notes)
        assert "mínimo=25" in " ".join(result.notes)

    def test_fewer_than_min_daily_fails(self) -> None:
        series = _make_valid_series(_T0, 39, timedelta(days=1))
        result = check_integrity(series, Timeframe.DAILY)
        assert result.ok is False
        assert any("too_few_candles" in n for n in result.notes)

    def test_min_count_override_accepts_shorter_series(self) -> None:
        series = _make_valid_series(_T0, 5, timedelta(minutes=15))
        result = check_integrity(series, Timeframe.M15, min_count=3)
        assert result.ok is True

    def test_min_count_override_rejects_shorter_series(self) -> None:
        series = _make_valid_series(_T0, 5, timedelta(minutes=15))
        result = check_integrity(series, Timeframe.M15, min_count=10)
        assert result.ok is False


# ═══════════════════════════════════════════════════════════════════════════
# Timezone awareness
# ═══════════════════════════════════════════════════════════════════════════


class TestTimezoneAwareness:
    def test_naive_datetime_fails(self) -> None:
        # Pydantic por default acepta datetime naive; el check debe detectarlo.
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        naive = series[0].model_copy(
            update={"dt": datetime(2025, 3, 10, 9, 30)}  # sin tzinfo
        )
        candles = [naive, *series[1:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("missing_tz" in n for n in result.notes)

    def test_utc_tz_is_valid(self) -> None:
        # ET es la convención, pero el check no exige ET específicamente:
        # solo exige que el dt sea tz-aware. La conversión a ET la hace
        # el fetcher.
        utc = UTC
        series = [
            _candle(datetime(2025, 3, 10, 14, 30, tzinfo=utc) + timedelta(minutes=15) * i)
            for i in range(25)
        ]
        result = check_integrity(series, Timeframe.M15)
        assert result.ok is True

    def test_multiple_naive_reported_individually(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        candles = [
            c.model_copy(update={"dt": c.dt.replace(tzinfo=None)}) if i < 3 else c
            for i, c in enumerate(series)
        ]
        result = check_integrity(candles, Timeframe.M15)
        missing_count = sum(1 for n in result.notes if n.startswith("missing_tz"))
        assert missing_count == 3


# ═══════════════════════════════════════════════════════════════════════════
# Orden y duplicados
# ═══════════════════════════════════════════════════════════════════════════


class TestOrderAndDuplicates:
    def test_out_of_order_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        # Invertimos índices 3 y 4 para romper el orden.
        swapped = [*series[:3], series[4], series[3], *series[5:]]
        result = check_integrity(swapped, Timeframe.M15)
        assert result.ok is False
        assert any("out_of_order" in n for n in result.notes)

    def test_duplicate_timestamp_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        # Duplicamos el dt de series[5] en series[6].
        dup = series[6].model_copy(update={"dt": series[5].dt})
        candles = [*series[:6], dup, *series[7:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("duplicate_ts" in n for n in result.notes)

    def test_reverse_ordered_list_reports_many_out_of_order(self) -> None:
        series = _make_valid_series(_T0, 30, timedelta(minutes=15))
        reversed_series = list(reversed(series))
        result = check_integrity(reversed_series, Timeframe.M15)
        out_of_order_count = sum(1 for n in result.notes if "out_of_order" in n)
        # Cada comparación consecutiva de una lista invertida está fuera de orden.
        assert out_of_order_count == 29


# ═══════════════════════════════════════════════════════════════════════════
# OHLC válido
# ═══════════════════════════════════════════════════════════════════════════


class TestOHLCValidity:
    def test_high_less_than_low_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        bad = series[10].model_copy(update={"h": 50.0, "l": 100.0})
        candles = [*series[:10], bad, *series[11:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("invalid_ohlc" in n and "high=50.0" in n for n in result.notes)

    def test_open_above_high_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        bad = series[10].model_copy(update={"o": 200.0})  # h=101, l=99
        candles = [*series[:10], bad, *series[11:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("open=200.0 fuera del rango" in n for n in result.notes)

    def test_close_below_low_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        bad = series[10].model_copy(update={"c": 50.0})  # l=99
        candles = [*series[:10], bad, *series[11:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("close=50.0" in n for n in result.notes)

    def test_zero_price_is_detected(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        bad = series[10].model_copy(update={"o": 0.0, "h": 0.0, "l": 0.0, "c": 0.0})
        candles = [*series[:10], bad, *series[11:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("non_positive_price" in n for n in result.notes)

    def test_negative_price_is_detected(self) -> None:
        # Pydantic Candle no prohibe float negativo en o/h/l/c — eso es
        # responsabilidad de la integridad semántica.
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        bad = series[10].model_copy(update={"o": -1.0, "h": 101.0, "l": -5.0, "c": 100.5})
        candles = [*series[:10], bad, *series[11:]]
        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        assert any("non_positive_price" in n for n in result.notes)


# ═══════════════════════════════════════════════════════════════════════════
# Acumulación de múltiples issues
# ═══════════════════════════════════════════════════════════════════════════


class TestMultipleIssues:
    def test_all_issues_are_reported_in_single_call(self) -> None:
        # Construimos una lista corta con múltiples problemas a la vez.
        good = _make_valid_series(_T0, 5, timedelta(minutes=15))
        bad_ohlc = good[1].model_copy(update={"h": 50.0, "l": 100.0})
        dup_ts = good[3].model_copy(update={"dt": good[2].dt})
        candles = [good[0], bad_ohlc, good[2], dup_ts, good[4]]

        result = check_integrity(candles, Timeframe.M15)
        assert result.ok is False
        codes = " ".join(result.notes)
        assert "too_few_candles" in codes  # 5 < 25
        assert "invalid_ohlc" in codes
        assert "duplicate_ts" in codes


# ═══════════════════════════════════════════════════════════════════════════
# Result model
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrityResult:
    def test_result_is_frozen(self) -> None:
        series = _make_valid_series(_T0, 25, timedelta(minutes=15))
        result = check_integrity(series, Timeframe.M15)
        with pytest.raises((TypeError, ValueError)):
            # Pydantic frozen: cualquier intento de mutación debe fallar.
            result.ok = False  # type: ignore[misc]

    def test_result_preserves_timeframe_echo(self) -> None:
        series = _make_valid_series(_T0, 40, timedelta(days=1))
        result = check_integrity(series, Timeframe.DAILY)
        assert result.timeframe == Timeframe.DAILY
