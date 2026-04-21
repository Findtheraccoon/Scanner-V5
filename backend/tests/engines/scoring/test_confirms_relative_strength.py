"""Tests de confirms de fuerza relativa (Fase 5.1) — FzaRel + DivSPY.

Cada condición portada literal desde Observatory `engine.py`:

**FzaRel:**
    (aln.dir == "bullish" AND a_chg > bench_chg + 0.5)
    OR (aln.dir == "bearish" AND a_chg < bench_chg - 0.5)

**DivSPY:**
    ticker != "SPY" AND spy_chg != 0
    AND ((a_chg < -0.5 AND spy_chg > 0.3) OR (a_chg > 0.5 AND spy_chg < -0.3))
"""

from __future__ import annotations

from engines.scoring.confirms import (
    detect_divspy_confirm,
    detect_fzarel_confirm,
)

# ═══════════════════════════════════════════════════════════════════════════
# FzaRel
# ═══════════════════════════════════════════════════════════════════════════


class TestFzaRelBullish:
    def test_ticker_outperforms_benchmark_fires(self) -> None:
        # a_chg=2.0, bench_chg=0.5 → diff=1.5 > 0.5, alignment bullish
        result = detect_fzarel_confirm(
            a_chg=2.0, bench_chg=0.5, bench_ticker="SPY", alignment_dir="bullish",
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "FzaRel +1.5% vs SPY"
        assert c["sg"] == "CONFIRM"
        assert c["tf"] == "D"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 4.0

    def test_boundary_exactly_0_5_does_not_fire(self) -> None:
        # Observatory: `a_chg > b_chg + 0.5` estricto.
        result = detect_fzarel_confirm(
            a_chg=1.0, bench_chg=0.5, bench_ticker="SPY", alignment_dir="bullish",
        )
        assert result == []

    def test_below_threshold_does_not_fire(self) -> None:
        result = detect_fzarel_confirm(
            a_chg=0.8, bench_chg=0.5, bench_ticker="SPY", alignment_dir="bullish",
        )
        assert result == []


class TestFzaRelBearish:
    def test_ticker_underperforms_benchmark_fires(self) -> None:
        # a_chg=-2.0, bench_chg=-0.5 → diff=-1.5 < -0.5, alignment bearish
        result = detect_fzarel_confirm(
            a_chg=-2.0, bench_chg=-0.5, bench_ticker="SPY", alignment_dir="bearish",
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "FzaRel -1.5% vs SPY"
        assert c["sg"] == "CONFIRM"

    def test_boundary_exactly_minus_0_5_does_not_fire(self) -> None:
        # Observatory: `a_chg < b_chg - 0.5` estricto.
        result = detect_fzarel_confirm(
            a_chg=-1.0, bench_chg=-0.5, bench_ticker="SPY", alignment_dir="bearish",
        )
        assert result == []


class TestFzaRelAlignmentMismatch:
    def test_bullish_alignment_but_ticker_underperforms(self) -> None:
        # a_chg < bench_chg pero alignment bullish → no dispara
        result = detect_fzarel_confirm(
            a_chg=-1.0, bench_chg=0.5, bench_ticker="SPY", alignment_dir="bullish",
        )
        assert result == []

    def test_bearish_alignment_but_ticker_outperforms(self) -> None:
        result = detect_fzarel_confirm(
            a_chg=1.0, bench_chg=-0.5, bench_ticker="SPY", alignment_dir="bearish",
        )
        assert result == []

    def test_mixed_alignment_does_not_fire(self) -> None:
        result = detect_fzarel_confirm(
            a_chg=2.0, bench_chg=0.5, bench_ticker="SPY", alignment_dir="mixed",
        )
        assert result == []


class TestFzaRelBenchmarkOverride:
    def test_custom_bench_ticker_in_description(self) -> None:
        result = detect_fzarel_confirm(
            a_chg=2.0, bench_chg=0.5, bench_ticker="QQQ", alignment_dir="bullish",
        )
        assert result[0]["d"] == "FzaRel +1.5% vs QQQ"


# ═══════════════════════════════════════════════════════════════════════════
# DivSPY
# ═══════════════════════════════════════════════════════════════════════════


class TestDivSpyTickerGuard:
    def test_spy_ticker_never_fires(self) -> None:
        # Aun con divergencia cumpliendo thresholds, SPY no diverge de sí mismo.
        result = detect_divspy_confirm(ticker="SPY", a_chg=-1.0, spy_chg=0.5)
        assert result == []

    def test_zero_spy_chg_does_not_fire(self) -> None:
        result = detect_divspy_confirm(ticker="QQQ", a_chg=-1.0, spy_chg=0.0)
        assert result == []


class TestDivSpyBearish:
    def test_ticker_down_spy_up_fires_put(self) -> None:
        # a_chg=-1.0 (< -0.5), spy_chg=0.5 (> 0.3) → bearish divergence
        result = detect_divspy_confirm(ticker="QQQ", a_chg=-1.0, spy_chg=0.5)
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Div SPY (QQQ:-1.0% vs SPY:+0.5%) → VERIFICAR CATALIZADOR"
        assert c["sg"] == "PUT"
        assert c["tf"] == "D"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 1.0

    def test_boundary_asset_exactly_minus_0_5(self) -> None:
        # Observatory: `a_chg < -0.5` estricto.
        result = detect_divspy_confirm(ticker="QQQ", a_chg=-0.5, spy_chg=0.5)
        assert result == []

    def test_boundary_spy_exactly_0_3(self) -> None:
        # Observatory: `spy_chg > 0.3` estricto.
        result = detect_divspy_confirm(ticker="QQQ", a_chg=-1.0, spy_chg=0.3)
        assert result == []


class TestDivSpyBullish:
    def test_ticker_up_spy_down_fires_call(self) -> None:
        result = detect_divspy_confirm(ticker="AAPL", a_chg=1.2, spy_chg=-0.5)
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Div SPY (AAPL:+1.2% vs SPY:-0.5%) → VERIFICAR CATALIZADOR"
        assert c["sg"] == "CALL"
        assert c["w"] == 1.0


class TestDivSpySameDirection:
    def test_both_up_does_not_fire(self) -> None:
        result = detect_divspy_confirm(ticker="QQQ", a_chg=1.5, spy_chg=0.8)
        assert result == []

    def test_both_down_does_not_fire(self) -> None:
        result = detect_divspy_confirm(ticker="QQQ", a_chg=-1.5, spy_chg=-0.8)
        assert result == []
