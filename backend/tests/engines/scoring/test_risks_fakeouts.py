"""Tests de los BB fakeouts 15M (Fase 4 paso 4)."""

from __future__ import annotations

from engines.scoring.risks import detect_bb_fakeouts_15m


def _candle(o: float, h: float, low: float, c: float) -> dict:
    return {"dt": "2025-01-15 10:00:00", "o": o, "h": h, "l": low, "c": c, "v": 1000}


def _neutral(price: float = 100.0) -> dict:
    return _candle(o=price, h=price + 0.1, low=price - 0.1, c=price)


def _bb(upper: float = 110.0, lower: float = 90.0, middle: float = 100.0) -> tuple:
    return (upper, middle, lower)


# ═══════════════════════════════════════════════════════════════════════════
# Fakeout sobre BB sup 1H
# ═══════════════════════════════════════════════════════════════════════════


class TestFakeoutSupBB:
    def test_fires_when_c2_wicks_above_but_closes_below(self) -> None:
        # bb_upper = 110. c2: h=112 > 110, c=108 < 110. c1: c=109 < 110.
        c3 = _neutral(105)
        c2 = _candle(o=107, h=112, low=106, c=108)
        c1 = _candle(o=108, h=109.5, low=107, c=109)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(upper=110.0))
        match = [r for r in risks if r["d"] == "Fakeout sobre BB sup 1H"]
        assert len(match) == 1
        assert match[0]["sg"] == "WARN"
        assert match[0]["w"] == -3.0
        assert match[0]["cat"] == "RISK"
        assert match[0]["tf"] == "15M"
        assert match[0]["age"] == 0

    def test_does_not_fire_when_c1_still_closes_above(self) -> None:
        # c1 cerró por encima de la banda → no es fakeout
        c3 = _neutral(105)
        c2 = _candle(o=107, h=112, low=106, c=108)
        c1 = _candle(o=108, h=113, low=107, c=111)  # c > 110 → arriba
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(upper=110.0))
        assert not any("Fakeout sobre BB sup" in r["d"] for r in risks)

    def test_does_not_fire_when_c2_did_not_wick_through(self) -> None:
        # c2.h <= bb_upper → no hubo breakout
        c3 = _neutral(105)
        c2 = _candle(o=107, h=109.5, low=106, c=108)
        c1 = _candle(o=108, h=109.5, low=107, c=109)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(upper=110.0))
        assert not any("Fakeout sobre BB sup" in r["d"] for r in risks)

    def test_does_not_fire_when_c2_closes_above(self) -> None:
        # c2 cerró por encima (breakout efectivo, no fakeout)
        c3 = _neutral(105)
        c2 = _candle(o=107, h=112, low=106, c=111)
        c1 = _candle(o=111, h=113, low=110, c=109)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(upper=110.0))
        assert not any("Fakeout sobre BB sup" in r["d"] for r in risks)


# ═══════════════════════════════════════════════════════════════════════════
# Fakeout bajo BB inf 1H (espejo)
# ═══════════════════════════════════════════════════════════════════════════


class TestFakeoutInfBB:
    def test_fires_when_c2_wicks_below_but_closes_above(self) -> None:
        # bb_lower = 90. c2: l=88 < 90, c=92 > 90. c1: c=91 > 90.
        c3 = _neutral(95)
        c2 = _candle(o=94, h=94, low=88, c=92)
        c1 = _candle(o=92, h=93, low=91, c=91.5)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(lower=90.0))
        match = [r for r in risks if r["d"] == "Fakeout bajo BB inf 1H"]
        assert len(match) == 1
        assert match[0]["sg"] == "WARN"
        assert match[0]["w"] == -3.0

    def test_does_not_fire_when_c1_still_closes_below(self) -> None:
        c3 = _neutral(95)
        c2 = _candle(o=94, h=94, low=88, c=92)
        c1 = _candle(o=92, h=92, low=87, c=89)  # c < 90
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(lower=90.0))
        assert not any("Fakeout bajo BB inf" in r["d"] for r in risks)

    def test_does_not_fire_when_c2_did_not_wick_through(self) -> None:
        c3 = _neutral(95)
        c2 = _candle(o=94, h=94, low=90.5, c=92)  # l >= bb_lower
        c1 = _candle(o=92, h=93, low=91, c=91.5)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(lower=90.0))
        assert not any("Fakeout bajo BB inf" in r["d"] for r in risks)

    def test_does_not_fire_when_c2_closes_below(self) -> None:
        c3 = _neutral(95)
        c2 = _candle(o=91, h=92, low=88, c=89)  # c < bb_lower
        c1 = _candle(o=89, h=92, low=88, c=91)
        risks = detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=_bb(lower=90.0))
        assert not any("Fakeout bajo BB inf" in r["d"] for r in risks)


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_list_returns_empty(self) -> None:
        assert detect_bb_fakeouts_15m([], bb_1h=_bb()) == []

    def test_less_than_three_candles_returns_empty(self) -> None:
        candles = [_neutral(), _neutral()]
        assert detect_bb_fakeouts_15m(candles, bb_1h=_bb()) == []

    def test_no_bb_returns_empty(self) -> None:
        c3 = _neutral(105)
        c2 = _candle(o=107, h=112, low=106, c=108)
        c1 = _candle(o=108, h=109, low=107, c=109)
        assert detect_bb_fakeouts_15m([c3, c2, c1], bb_1h=None) == []
