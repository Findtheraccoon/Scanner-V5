"""Tests de gap dict (Sub-fase 5.2d).

Port literal de Observatory `indicators.py:gap()` líneas 242-259.
Casuísticas:

- < 2 velas → None
- gap_pct = round((today.o - yesterday.c) / yesterday.c * 100, 2)
- atr_val = atr_pct_val or 2 (fallback 2% si falsy)
- significant = abs(gap_pct) > atr_val * 0.5  (estricto)
- dir = "bullish" si pct > 0 else "bearish"
"""

from __future__ import annotations

from engines.scoring.indicators import gap


def _candle(o: float, h: float, low: float, c: float, v: float = 1000) -> dict:
    return {"o": o, "h": h, "l": low, "c": c, "v": v, "dt": ""}


# ═══════════════════════════════════════════════════════════════════════════
# Insufficient data
# ═══════════════════════════════════════════════════════════════════════════


class TestGapInsufficient:
    def test_empty_returns_none(self) -> None:
        assert gap([], atr_pct_val=2.0) is None

    def test_one_candle_returns_none(self) -> None:
        candles = [_candle(100, 102, 99, 101)]
        assert gap(candles, atr_pct_val=2.0) is None


# ═══════════════════════════════════════════════════════════════════════════
# Bullish / bearish direction
# ═══════════════════════════════════════════════════════════════════════════


class TestGapDirection:
    def test_bullish_when_open_above_prev_close(self) -> None:
        # yesterday.c=100, today.o=102 → gap=+2.0%
        candles = [_candle(99, 101, 98, 100), _candle(102, 105, 101, 103)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == 2.0
        assert result["dir"] == "bullish"

    def test_bearish_when_open_below_prev_close(self) -> None:
        # yesterday.c=100, today.o=98 → gap=-2.0%
        candles = [_candle(99, 101, 98, 100), _candle(98, 99, 95, 96)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == -2.0
        assert result["dir"] == "bearish"

    def test_zero_gap_is_bearish_observatory_quirk(self) -> None:
        # Observatory: `dir = bullish if pct > 0 else bearish` →
        # gap exactamente 0 cae en la rama bearish (no es "neutral").
        candles = [_candle(99, 101, 98, 100), _candle(100, 102, 99, 101)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == 0.0
        assert result["dir"] == "bearish"


# ═══════════════════════════════════════════════════════════════════════════
# Significancia vs ATR
# ═══════════════════════════════════════════════════════════════════════════


class TestGapSignificance:
    def test_significant_when_gap_exceeds_half_atr(self) -> None:
        # gap=2.0%, atr=2.0% → threshold=1.0% → 2.0 > 1.0 ✓
        candles = [_candle(99, 101, 98, 100), _candle(102, 105, 101, 103)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["significant"] is True

    def test_not_significant_when_below_half_atr(self) -> None:
        # gap=0.5%, atr=2.0% → threshold=1.0% → 0.5 > 1.0 ✗
        candles = [_candle(99, 101, 98, 100), _candle(100.5, 101, 100, 101)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == 0.5
        assert result["significant"] is False

    def test_boundary_exactly_half_atr_not_significant(self) -> None:
        # Observatory usa `>` estricto. gap=1.0%, atr=2.0% → threshold=1.0
        # → 1.0 > 1.0 ✗
        candles = [_candle(99, 101, 98, 100), _candle(101, 102, 100, 101)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == 1.0
        assert result["significant"] is False

    def test_negative_gap_significance_uses_abs(self) -> None:
        # gap=-2.0%, atr=2.0% → |gap|=2.0 > 1.0 ✓
        candles = [_candle(99, 101, 98, 100), _candle(98, 99, 95, 96)]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["significant"] is True


# ═══════════════════════════════════════════════════════════════════════════
# ATR fallback (None / 0 → 2%)
# ═══════════════════════════════════════════════════════════════════════════


class TestGapAtrFallback:
    def test_none_atr_falls_back_to_2_pct(self) -> None:
        # atr=None → fallback 2 → threshold=1.0% → gap=2% > 1% ✓
        candles = [_candle(99, 101, 98, 100), _candle(102, 105, 101, 103)]
        result = gap(candles, atr_pct_val=None)
        assert result is not None
        assert result["significant"] is True

    def test_zero_atr_falls_back_to_2_pct(self) -> None:
        candles = [_candle(99, 101, 98, 100), _candle(102, 105, 101, 103)]
        result = gap(candles, atr_pct_val=0)
        assert result is not None
        assert result["significant"] is True

    def test_fallback_threshold_below_2_pct_gap_not_significant(self) -> None:
        # atr=None → fallback 2 → threshold=1%; gap=0.8% → 0.8 > 1 ✗
        candles = [_candle(99, 101, 98, 100), _candle(100.8, 101, 100, 101)]
        result = gap(candles, atr_pct_val=None)
        assert result is not None
        assert result["significant"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Rounding
# ═══════════════════════════════════════════════════════════════════════════


class TestGapRounding:
    def test_pct_rounded_to_two_decimals(self) -> None:
        # yesterday.c=100, today.o=100.123456 → 0.123456% → round(2)=0.12
        candles = [
            _candle(99, 101, 98, 100),
            _candle(100.123456, 101, 100, 100.5),
        ]
        result = gap(candles, atr_pct_val=2.0)
        assert result is not None
        assert result["pct"] == 0.12
