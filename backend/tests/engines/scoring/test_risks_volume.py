"""Tests de los volume risks (Fase 4 paso 4)."""

from __future__ import annotations

from engines.scoring.risks import detect_volume_risks_15m


def _candle(c: float, o: float | None = None) -> dict:
    """Vela minimalista — solo `c` y opcionalmente `o` importan."""
    open_ = o if o is not None else c - 0.1
    return {
        "dt": "2025-01-15 10:00:00",
        "o": open_,
        "h": c + 1,
        "l": min(open_, c) - 1,
        "c": c,
        "v": 1000,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Rebote vol bajo
# ═══════════════════════════════════════════════════════════════════════════


class TestRebeteVolBajo:
    def test_fires_when_bounce_and_low_volume(self) -> None:
        # prev close = 100, curr close = 101 → rebote
        # volume_ratio = 0.4 < 0.6 → dispara
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_ratio=0.4)
        match = [r for r in risks if r["d"].startswith("Rebote vol bajo")]
        assert len(match) == 1
        assert match[0]["sg"] == "WARN"
        assert match[0]["w"] == -2.0
        assert match[0]["cat"] == "RISK"
        assert match[0]["tf"] == "15M"
        assert match[0]["age"] == 0
        assert "0.4x" in match[0]["d"]

    def test_does_not_fire_without_bounce(self) -> None:
        # curr close <= prev close → no rebote
        candles = [_candle(c=100), _candle(c=99)]
        risks = detect_volume_risks_15m(candles, volume_ratio=0.3)
        assert not any("Rebote vol bajo" in r["d"] for r in risks)

    def test_does_not_fire_when_vol_ratio_at_threshold(self) -> None:
        # volume_ratio = 0.6 NO dispara (strict `<`, no `<=`).
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_ratio=0.6)
        assert not any("Rebote vol bajo" in r["d"] for r in risks)

    def test_does_not_fire_when_vol_ratio_above_threshold(self) -> None:
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_ratio=1.2)
        assert not any("Rebote vol bajo" in r["d"] for r in risks)

    def test_does_not_fire_when_vol_ratio_none(self) -> None:
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_ratio=None)
        assert not any("Rebote vol bajo" in r["d"] for r in risks)


# ═══════════════════════════════════════════════════════════════════════════
# Vol declinante
# ═══════════════════════════════════════════════════════════════════════════


class TestVolDeclinante:
    def test_fires_when_bounce_and_declining(self) -> None:
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_seq_declining=True)
        match = [r for r in risks if r["d"] == "Vol declinante en rebote"]
        assert len(match) == 1
        assert match[0]["w"] == -1.0
        assert match[0]["sg"] == "WARN"
        assert match[0]["cat"] == "RISK"

    def test_does_not_fire_without_bounce(self) -> None:
        candles = [_candle(c=100), _candle(c=99)]
        risks = detect_volume_risks_15m(candles, volume_seq_declining=True)
        assert not risks

    def test_does_not_fire_when_not_declining(self) -> None:
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_seq_declining=False)
        assert not risks


# ═══════════════════════════════════════════════════════════════════════════
# Combinados + edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestCombined:
    def test_both_can_fire_together(self) -> None:
        candles = [_candle(c=100), _candle(c=101)]
        risks = detect_volume_risks_15m(candles, volume_ratio=0.3, volume_seq_declining=True)
        assert len(risks) == 2
        descs = {r["d"] for r in risks}
        assert any("Rebote vol bajo" in d for d in descs)
        assert "Vol declinante en rebote" in descs

    def test_empty_candles_returns_empty(self) -> None:
        assert detect_volume_risks_15m([], volume_ratio=0.3) == []

    def test_single_candle_returns_empty(self) -> None:
        # Necesita ≥ 2 velas para comparar close.
        assert detect_volume_risks_15m([_candle(c=100)], volume_ratio=0.3) == []

    def test_flat_close_counts_as_no_bounce(self) -> None:
        # close_curr == close_prev → no rebote (strict >).
        candles = [_candle(c=100), _candle(c=100)]
        risks = detect_volume_risks_15m(candles, volume_ratio=0.3, volume_seq_declining=True)
        assert not risks
