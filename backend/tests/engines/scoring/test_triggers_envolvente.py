"""Tests de Envolvente 1H (Fase 4b)."""

from __future__ import annotations

from engines.scoring.triggers import detect_engulfing_1h


def _candle(o: float, h: float, low: float, c: float) -> dict:
    return {"dt": "2025-01-15 10:00:00", "o": o, "h": h, "l": low, "c": c, "v": 1000}


# ═══════════════════════════════════════════════════════════════════════════
# Envolvente alcista
# ═══════════════════════════════════════════════════════════════════════════


class TestBullishEngulfing:
    def test_fires_when_all_conditions_met(self) -> None:
        # prev: bear, body=1 (o=101, c=100)
        # curr: bull, body=2 (o=99, c=102)
        # curr.o (99) <= prev.c (100) ✓
        # curr.c (102) >= prev.o (101) ✓
        # curr_body (2) > prev_body (1) * 1.1 = 1.1 ✓
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=99, h=102.5, low=98.5, c=102)
        triggers = detect_engulfing_1h([prev, curr])
        match = [t for t in triggers if t["d"] == "Envolvente alcista 1H"]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 3.0
        assert match[0]["tf"] == "1H"
        assert match[0]["age"] == 0

    def test_does_not_fire_when_prev_is_bullish(self) -> None:
        prev = _candle(o=100, h=101, low=99.5, c=100.5)  # bull
        curr = _candle(o=99, h=102.5, low=98.5, c=102)  # bull
        triggers = detect_engulfing_1h([prev, curr])
        assert not triggers

    def test_does_not_fire_when_curr_body_not_large_enough(self) -> None:
        # curr_body = 1.0, prev_body = 1.0 → 1.0 > 1.0 * 1.1 = 1.1 → False
        prev = _candle(o=101, h=101.5, low=99.5, c=100)  # body 1
        curr = _candle(o=99.5, h=101, low=99, c=100.5)  # bull, body 1
        triggers = detect_engulfing_1h([prev, curr])
        assert not triggers

    def test_does_not_fire_when_containment_fails(self) -> None:
        # curr.o > prev.c (no rompe el close previo hacia abajo)
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=100.5, h=103, low=100.3, c=102.5)  # o > prev.c
        triggers = detect_engulfing_1h([prev, curr])
        assert not triggers


# ═══════════════════════════════════════════════════════════════════════════
# Envolvente bajista
# ═══════════════════════════════════════════════════════════════════════════


class TestBearishEngulfing:
    def test_fires_when_all_conditions_met(self) -> None:
        # prev: bull, body=1 (o=100, c=101)
        # curr: bear, body=2 (o=102, c=100)
        # curr.o (102) >= prev.c (101) ✓
        # curr.c (100) <= prev.o (100) ✓ (equality OK — v4.2.1 uses >=/<=)
        prev = _candle(o=100, h=101.5, low=99.5, c=101)
        curr = _candle(o=102, h=102.5, low=99.5, c=100)
        triggers = detect_engulfing_1h([prev, curr])
        match = [t for t in triggers if t["d"] == "Envolvente bajista 1H"]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 3.0

    def test_does_not_fire_when_prev_is_bearish(self) -> None:
        prev = _candle(o=101, h=101.5, low=99.5, c=100)  # bear
        curr = _candle(o=102, h=102.5, low=99.5, c=100)  # bear
        triggers = detect_engulfing_1h([prev, curr])
        assert not triggers


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_empty_list_returns_empty(self) -> None:
        assert detect_engulfing_1h([]) == []

    def test_single_candle_returns_empty(self) -> None:
        only = _candle(o=99, h=102, low=98, c=101)
        assert detect_engulfing_1h([only]) == []

    def test_uses_only_last_two_candles(self) -> None:
        """Solo se miran las últimas 2, las anteriores no afectan."""
        old = _candle(o=50, h=60, low=40, c=55)
        prev = _candle(o=101, h=101.5, low=99.5, c=100)  # bear, body=1
        curr = _candle(o=99, h=102.5, low=98.5, c=102)  # bull, body=3 > 1.1
        triggers = detect_engulfing_1h([old, old, prev, curr])
        assert any(t["d"] == "Envolvente alcista 1H" for t in triggers)
