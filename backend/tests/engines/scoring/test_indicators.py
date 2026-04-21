"""Tests de los indicadores técnicos (Fase 2 del Scoring Engine).

Todos los valores esperados son hand-computed sobre series pequeñas y
verificables a mano, o derivaciones analíticas (ej. serie constante →
SMA/EMA iguales al valor, stdev=0).
"""

from __future__ import annotations

import math
from statistics import pstdev

import pytest

from engines.scoring.indicators import (
    atr,
    bb_width,
    bollinger_bands,
    ema,
    gap_pct_at,
    is_volume_increasing,
    sma,
    true_range,
    volume_ratio_at,
)

# ═══════════════════════════════════════════════════════════════════════════
# SMA
# ═══════════════════════════════════════════════════════════════════════════


class TestSMA:
    def test_warmup_is_none_until_window_reached(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = sma(values, window=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(2.0)  # mean(1,2,3)
        assert result[3] == pytest.approx(3.0)  # mean(2,3,4)
        assert result[4] == pytest.approx(4.0)  # mean(3,4,5)

    def test_constant_series_returns_same_value(self) -> None:
        values = [7.5] * 10
        result = sma(values, window=4)
        for v in result[3:]:
            assert v == pytest.approx(7.5)

    def test_empty_input_returns_empty(self) -> None:
        assert sma([], window=5) == []

    def test_shorter_than_window_returns_all_none(self) -> None:
        assert sma([1.0, 2.0], window=5) == [None, None]

    def test_window_one_returns_input_values(self) -> None:
        values = [1.0, 2.0, 3.0]
        result = sma(values, window=1)
        assert result == [1.0, 2.0, 3.0]

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            sma([1.0, 2.0], window=0)
        with pytest.raises(ValueError):
            sma([1.0, 2.0], window=-1)

    def test_output_length_matches_input(self) -> None:
        for n in [0, 1, 5, 50]:
            values = [float(i) for i in range(n)]
            assert len(sma(values, window=3)) == n


# ═══════════════════════════════════════════════════════════════════════════
# EMA
# ═══════════════════════════════════════════════════════════════════════════


class TestEMA:
    def test_warmup_none_until_window_minus_one(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = ema(values, window=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None  # seed = SMA(1,2,3) = 2.0

    def test_seed_equals_sma_of_first_window(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = ema(values, window=3)
        assert result[2] == pytest.approx(2.0)

    def test_recurrence_matches_manual_calculation(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        window = 3
        result = ema(values, window=window)
        alpha = 2.0 / (window + 1)  # = 0.5
        seed = 2.0  # SMA(1,2,3)
        expected_3 = alpha * 4.0 + (1 - alpha) * seed  # 0.5*4 + 0.5*2 = 3.0
        expected_4 = alpha * 5.0 + (1 - alpha) * expected_3  # 0.5*5 + 0.5*3 = 4.0
        assert result[3] == pytest.approx(expected_3)
        assert result[4] == pytest.approx(expected_4)

    def test_constant_series_returns_same_value(self) -> None:
        values = [7.5] * 10
        result = ema(values, window=4)
        for v in result[3:]:
            assert v == pytest.approx(7.5)

    def test_shorter_than_window_returns_all_none(self) -> None:
        assert ema([1.0, 2.0], window=5) == [None, None]

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            ema([1.0], window=0)


# ═══════════════════════════════════════════════════════════════════════════
# Bollinger Bands
# ═══════════════════════════════════════════════════════════════════════════


class TestBollingerBands:
    def test_warmup_none_until_window(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        lo, mi, up = bollinger_bands(values, window=3, k=2.0)
        assert lo[0] is lo[1] is mi[0] is mi[1] is up[0] is up[1] is None
        assert lo[2] is not None

    def test_middle_equals_sma(self) -> None:
        values = [10.0, 12.0, 11.0, 13.0, 14.0, 12.5]
        _lo, mi, _up = bollinger_bands(values, window=3, k=2.0)
        sma_ = sma(values, window=3)
        for i in range(len(values)):
            assert mi[i] == sma_[i]

    def test_bands_symmetric_around_middle(self) -> None:
        # Observatory redondea cada banda independientemente a 2 decimales.
        # La simetría puede tener desviación hasta 0.01 por rounding asimétrico
        # (ej. mi=7.0, sd=1.6329... → up=10.27, lo=3.73, ambos round a 2 dec
        # → up-mi = 3.27, mi-lo = 3.27, OK; pero en edge cases puede diferir
        # en 0.01).
        values = [10.0, 12.0, 11.0, 13.0, 14.0, 12.5]
        lo, mi, up = bollinger_bands(values, window=3, k=2.0)
        for i in range(2, len(values)):
            assert mi[i] is not None
            assert (up[i] - mi[i]) == pytest.approx(mi[i] - lo[i], abs=0.01)

    def test_constant_series_has_zero_width(self) -> None:
        values = [50.0] * 10
        lo, mi, up = bollinger_bands(values, window=5, k=2.0)
        for i in range(4, 10):
            assert lo[i] == mi[i] == up[i] == 50.0

    def test_manual_calculation_matches(self) -> None:
        # Con rounding a 2 decimales (paridad Observatory), comparamos contra
        # la versión redondeada del cálculo manual.
        values = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        window = 3
        k = 2.0
        lo, mi, up = bollinger_bands(values, window=window, k=k)
        # En el último índice: ventana [5,7,9], mean=7, pstdev=sqrt(8/3)≈1.6330
        expected_mi = 7.0
        expected_sd = pstdev([5.0, 7.0, 9.0])
        assert mi[-1] == pytest.approx(expected_mi)
        assert up[-1] == pytest.approx(round(expected_mi + k * expected_sd, 2))
        assert lo[-1] == pytest.approx(round(expected_mi - k * expected_sd, 2))

    def test_rejects_window_below_2(self) -> None:
        with pytest.raises(ValueError):
            bollinger_bands([1.0, 2.0], window=1, k=2.0)

    def test_rejects_non_positive_k(self) -> None:
        with pytest.raises(ValueError):
            bollinger_bands([1.0, 2.0, 3.0], window=2, k=0.0)
        with pytest.raises(ValueError):
            bollinger_bands([1.0, 2.0, 3.0], window=2, k=-1.0)


# ═══════════════════════════════════════════════════════════════════════════
# BB width (derivado de bollinger_bands)
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidth:
    def test_constant_series_width_is_zero(self) -> None:
        values = [50.0] * 10
        lo, mi, up = bollinger_bands(values, window=5, k=2.0)
        w = bb_width(lo, mi, up)
        for v in w[4:]:
            assert v == pytest.approx(0.0)

    def test_width_is_none_in_warmup(self) -> None:
        values = [1.0, 2.0, 3.0, 4.0]
        lo, mi, up = bollinger_bands(values, window=3, k=2.0)
        w = bb_width(lo, mi, up)
        assert w[0] is None
        assert w[1] is None
        assert w[2] is not None  # warmup completo

    def test_width_is_positive_for_non_constant_series(self) -> None:
        values = [1.0, 5.0, 2.0, 6.0, 3.0, 7.0]
        lo, mi, up = bollinger_bands(values, window=3, k=2.0)
        w = bb_width(lo, mi, up)
        for v in w[2:]:
            assert v is not None and v > 0


# ═══════════════════════════════════════════════════════════════════════════
# True range / ATR
# ═══════════════════════════════════════════════════════════════════════════


class TestTrueRange:
    def test_first_candle_uses_hl_only(self) -> None:
        tr = true_range({"o": 10, "h": 12, "l": 9, "c": 11, "v": 1000}, prev_close=None)
        assert tr == 3.0

    def test_uses_gap_up_from_prev_close(self) -> None:
        # prev_close=8, h=12, l=11 → TR = max(1, |12-8|, |11-8|) = 4
        tr = true_range({"o": 12, "h": 12, "l": 11, "c": 11, "v": 1}, prev_close=8.0)
        assert tr == 4.0

    def test_uses_gap_down_from_prev_close(self) -> None:
        # prev_close=15, h=12, l=11 → TR = max(1, |12-15|, |11-15|) = 4
        tr = true_range({"o": 12, "h": 12, "l": 11, "c": 11, "v": 1}, prev_close=15.0)
        assert tr == 4.0

    def test_inner_range_uses_hl(self) -> None:
        # prev_close=11, h=12, l=10 → TR = max(2, 1, 1) = 2
        tr = true_range({"o": 11, "h": 12, "l": 10, "c": 11, "v": 1}, prev_close=11.0)
        assert tr == 2.0


class TestATR:
    def _candle(self, h: float, low: float, c: float) -> dict:
        return {"o": low, "h": h, "l": low, "c": c, "v": 1000}

    def test_warmup_none_until_window(self) -> None:
        candles = [self._candle(10, 9, 9.5) for _ in range(5)]
        result = atr(candles, window=3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] is not None

    def test_seed_is_mean_of_first_trs(self) -> None:
        # TRs: [1.0, 1.0, 1.0] (todos idénticos, sin gap) → seed = 1.0
        candles = [self._candle(10, 9, 9.5) for _ in range(4)]
        result = atr(candles, window=3)
        assert result[2] == pytest.approx(1.0)

    def test_wilder_smoothing_recurrence(self) -> None:
        candles = [self._candle(10, 9, 9.5) for _ in range(5)]
        window = 3
        result = atr(candles, window=window)
        # Con TRs uniformes = 1.0, el smoothing mantiene 1.0.
        for v in result[window - 1 :]:
            assert v == pytest.approx(1.0)

    def test_empty_returns_empty(self) -> None:
        assert atr([], window=14) == []

    def test_shorter_than_window_all_none(self) -> None:
        candles = [self._candle(10, 9, 9.5) for _ in range(3)]
        result = atr(candles, window=14)
        assert all(v is None for v in result)

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            atr([{"o": 1, "h": 1, "l": 1, "c": 1, "v": 1}], window=0)


# ═══════════════════════════════════════════════════════════════════════════
# volume_ratio_at
# ═══════════════════════════════════════════════════════════════════════════


class TestVolumeRatio:
    def _candles_with_volumes(self, volumes: list[int]) -> list[dict]:
        return [{"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": v} for v in volumes]

    def test_none_before_warmup(self) -> None:
        candles = self._candles_with_volumes([100, 200, 300])
        assert volume_ratio_at(candles, index=2, window=5) is None

    def test_ratio_matches_manual(self) -> None:
        # Volumes: prev 4 are [100, 100, 100, 100] avg=100, current=200 → ratio=2.0
        candles = self._candles_with_volumes([100, 100, 100, 100, 200])
        assert volume_ratio_at(candles, index=4, window=4) == pytest.approx(2.0)

    def test_ratio_returns_none_when_prior_avg_is_zero(self) -> None:
        candles = self._candles_with_volumes([0, 0, 0, 0, 500])
        assert volume_ratio_at(candles, index=4, window=4) is None

    def test_out_of_range_index_returns_none(self) -> None:
        candles = self._candles_with_volumes([100, 200])
        assert volume_ratio_at(candles, index=5, window=1) is None

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError):
            volume_ratio_at([], index=0, window=0)


# ═══════════════════════════════════════════════════════════════════════════
# is_volume_increasing
# ═══════════════════════════════════════════════════════════════════════════


class TestIsVolumeIncreasing:
    def _candles_with_volumes(self, volumes: list[int]) -> list[dict]:
        return [{"o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": v} for v in volumes]

    def test_strictly_increasing_returns_true(self) -> None:
        candles = self._candles_with_volumes([10, 20, 30])
        assert is_volume_increasing(candles, index=2, n=3) is True

    def test_flat_returns_false(self) -> None:
        candles = self._candles_with_volumes([10, 10, 10])
        assert is_volume_increasing(candles, index=2, n=3) is False

    def test_decreasing_returns_false(self) -> None:
        candles = self._candles_with_volumes([30, 20, 10])
        assert is_volume_increasing(candles, index=2, n=3) is False

    def test_partial_increase_returns_false(self) -> None:
        # 10, 20, 15 — no estrictamente creciente al final
        candles = self._candles_with_volumes([10, 20, 15])
        assert is_volume_increasing(candles, index=2, n=3) is False

    def test_insufficient_history_returns_false(self) -> None:
        candles = self._candles_with_volumes([10, 20])
        assert is_volume_increasing(candles, index=1, n=3) is False

    def test_n_below_2_raises(self) -> None:
        with pytest.raises(ValueError):
            is_volume_increasing([], index=0, n=1)


# ═══════════════════════════════════════════════════════════════════════════
# gap_pct_at
# ═══════════════════════════════════════════════════════════════════════════


class TestGapPct:
    def _make(self, opens: list[float], closes: list[float]) -> list[dict]:
        return [
            {"o": o, "h": o + 1, "l": o - 1, "c": c, "v": 1}
            for o, c in zip(opens, closes, strict=True)
        ]

    def test_index_zero_returns_none(self) -> None:
        candles = self._make([100.0, 101.0], [100.5, 101.5])
        assert gap_pct_at(candles, index=0) is None

    def test_positive_gap(self) -> None:
        # prev_close=100, current_open=101 → (101-100)/100 * 100 = 1.0
        candles = self._make([99.0, 101.0], [100.0, 102.0])
        assert gap_pct_at(candles, index=1) == pytest.approx(1.0)

    def test_negative_gap(self) -> None:
        # prev_close=100, current_open=99 → -1.0
        candles = self._make([99.0, 99.0], [100.0, 100.0])
        assert gap_pct_at(candles, index=1) == pytest.approx(-1.0)

    def test_zero_gap(self) -> None:
        candles = self._make([99.0, 100.0], [100.0, 101.0])
        assert gap_pct_at(candles, index=1) == pytest.approx(0.0)

    def test_zero_prev_close_returns_none(self) -> None:
        candles = self._make([1.0, 1.0], [0.0, 1.0])
        assert gap_pct_at(candles, index=1) is None

    def test_out_of_range_returns_none(self) -> None:
        candles = self._make([1.0], [1.0])
        assert gap_pct_at(candles, index=5) is None


# ═══════════════════════════════════════════════════════════════════════════
# Sanity numeric
# ═══════════════════════════════════════════════════════════════════════════


def test_no_nan_leakage_in_core_indicators() -> None:
    """Verificación rápida: con inputs razonables no producimos NaN ni inf."""
    values = [100.0 + i * 0.5 for i in range(30)]
    sma_ = sma(values, 10)
    ema_ = ema(values, 10)
    lo, mi, up = bollinger_bands(values, 10, 2.0)
    for series in (sma_, ema_, lo, mi, up):
        for v in series:
            if v is not None:
                assert not math.isnan(v)
                assert not math.isinf(v)
