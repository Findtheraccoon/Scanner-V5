"""Tests del alignment gate (Fase 3 del Scoring Engine)."""

from __future__ import annotations

import pytest

from engines.scoring.alignment import (
    alignment_gate_passes,
    compute_alignment,
    trend_for_timeframe,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _candles_with_closes(closes: list[float]) -> list[dict]:
    return [
        {"dt": f"2025-01-{i + 1:02d}", "o": c, "h": c + 1, "l": c - 1, "c": c, "v": 1000}
        for i, c in enumerate(closes)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# trend_for_timeframe
# ═══════════════════════════════════════════════════════════════════════════


class TestTrendForTimeframe:
    def test_monotonic_up_series_returns_up(self) -> None:
        # close crece linealmente → latest_close > SMA(20) = mean de los últimos 20
        candles = _candles_with_closes([100.0 + i * 0.5 for i in range(25)])
        assert trend_for_timeframe(candles) == "up"

    def test_monotonic_down_series_returns_down(self) -> None:
        candles = _candles_with_closes([100.0 - i * 0.5 for i in range(25)])
        assert trend_for_timeframe(candles) == "down"

    def test_constant_series_returns_flat(self) -> None:
        candles = _candles_with_closes([100.0] * 25)
        assert trend_for_timeframe(candles) == "flat"

    def test_series_shorter_than_ma_window_returns_flat(self) -> None:
        candles = _candles_with_closes([100.0 + i for i in range(10)])  # < 20
        assert trend_for_timeframe(candles) == "flat"

    def test_empty_series_returns_flat(self) -> None:
        assert trend_for_timeframe([]) == "flat"

    def test_custom_ma_window(self) -> None:
        # Con ma_window=5 y serie corta (6) el MA=mean([100,101,...,104])=102,
        # close=105 → up.
        candles = _candles_with_closes([100.0 + i for i in range(6)])
        assert trend_for_timeframe(candles, ma_window=5) == "up"

    def test_late_reversal_flips_trend(self) -> None:
        """Si la serie sube 20 velas y después cae fuerte, el último close
        puede quedar por debajo de la SMA → down."""
        up_part = [100.0 + i * 0.1 for i in range(20)]
        # Cae abrupto en las últimas 5 velas
        down_part = [90.0, 89.0, 88.0, 87.0, 86.0]
        candles = _candles_with_closes([*up_part, *down_part])
        assert trend_for_timeframe(candles) == "down"


# ═══════════════════════════════════════════════════════════════════════════
# compute_alignment
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeAlignment:
    def test_all_up_returns_n3_up(self) -> None:
        assert compute_alignment("up", "up", "up") == (3, "up")

    def test_all_down_returns_n3_down(self) -> None:
        assert compute_alignment("down", "down", "down") == (3, "down")

    def test_two_up_one_down_returns_n2_up(self) -> None:
        assert compute_alignment("up", "up", "down") == (2, "up")

    def test_two_down_one_up_returns_n2_down(self) -> None:
        assert compute_alignment("down", "up", "down") == (2, "down")

    def test_tie_up_down_returns_flat_with_flat_count(self) -> None:
        # 1 up + 1 down + 1 flat → empate up/down, cuenta de flats = 1
        assert compute_alignment("up", "down", "flat") == (1, "flat")

    def test_all_flat_returns_n3_flat(self) -> None:
        assert compute_alignment("flat", "flat", "flat") == (3, "flat")

    def test_two_flat_one_up_returns_n1_up(self) -> None:
        # up_count=1, down_count=0 → up gana. n=1, dir=up. Falla gate.
        assert compute_alignment("flat", "up", "flat") == (1, "up")

    def test_order_independent(self) -> None:
        """La función debe ser simétrica en sus 3 argumentos."""
        assert compute_alignment("up", "up", "down") == compute_alignment("down", "up", "up")
        assert compute_alignment("up", "down", "flat") == compute_alignment("flat", "down", "up")


# ═══════════════════════════════════════════════════════════════════════════
# alignment_gate_passes
# ═══════════════════════════════════════════════════════════════════════════


class TestAlignmentGate:
    def test_n3_up_passes(self) -> None:
        assert alignment_gate_passes(3, "up") is True

    def test_n2_up_passes(self) -> None:
        assert alignment_gate_passes(2, "up") is True

    def test_n2_down_passes(self) -> None:
        assert alignment_gate_passes(2, "down") is True

    def test_n1_fails_regardless_of_dir(self) -> None:
        assert alignment_gate_passes(1, "up") is False
        assert alignment_gate_passes(1, "down") is False

    def test_flat_dir_fails_even_with_n3(self) -> None:
        # 3 flats no pasa — no hay dirección que operar
        assert alignment_gate_passes(3, "flat") is False

    def test_n0_fails(self) -> None:
        assert alignment_gate_passes(0, "flat") is False


# ═══════════════════════════════════════════════════════════════════════════
# Integración trend → compute_alignment
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegration:
    def test_three_up_timeframes_produce_gate_pass(self) -> None:
        up_candles = _candles_with_closes([100.0 + i * 0.5 for i in range(25)])
        t_15m = trend_for_timeframe(up_candles)
        t_1h = trend_for_timeframe(up_candles)
        t_daily = trend_for_timeframe(up_candles)
        n, direction = compute_alignment(t_15m, t_1h, t_daily)
        assert alignment_gate_passes(n, direction) is True
        assert direction == "up"

    def test_mixed_flat_daily_blocks_gate(self) -> None:
        """daily con serie corta (flat) + 15m/1h up → n=2 up, debería pasar."""
        up_candles = _candles_with_closes([100.0 + i * 0.5 for i in range(25)])
        short_daily = _candles_with_closes([100.0] * 10)  # < ma_window → flat
        n, direction = compute_alignment(
            trend_for_timeframe(up_candles),
            trend_for_timeframe(up_candles),
            trend_for_timeframe(short_daily),
        )
        assert n == 2
        assert direction == "up"
        assert alignment_gate_passes(n, direction) is True


@pytest.mark.parametrize(
    "trends,expected_n,expected_dir,expected_pass",
    [
        (("up", "up", "up"), 3, "up", True),
        (("down", "down", "down"), 3, "down", True),
        (("up", "up", "down"), 2, "up", True),
        (("up", "down", "down"), 2, "down", True),
        (("up", "down", "flat"), 1, "flat", False),
        (("flat", "flat", "flat"), 3, "flat", False),
        (("up", "flat", "flat"), 1, "up", False),
    ],
)
def test_alignment_matrix(
    trends: tuple, expected_n: int, expected_dir: str, expected_pass: bool
) -> None:
    n, direction = compute_alignment(*trends)
    assert (n, direction) == (expected_n, expected_dir)
    assert alignment_gate_passes(n, direction) is expected_pass
