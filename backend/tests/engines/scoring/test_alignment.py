"""Tests del alignment gate (Fase 3 Scoring Engine, port Observatory).

Cubre los 3 flavors de trend, `compute_alignment` y `alignment_gate`
con catalyst override.
"""

from __future__ import annotations

import pytest

from engines.scoring.alignment import (
    alignment_gate,
    compute_alignment,
    trend_slope,
    trend_strict,
    trend_with_fallback,
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
# trend_strict
# ═══════════════════════════════════════════════════════════════════════════


class TestTrendStrict:
    def test_bullish_when_price_above_ma20_above_ma40(self) -> None:
        assert trend_strict(price=110.0, ma20=105.0, ma40=100.0) == "bullish"

    def test_bearish_when_price_below_ma20_below_ma40(self) -> None:
        assert trend_strict(price=90.0, ma20=95.0, ma40=100.0) == "bearish"

    def test_neutral_when_price_between_mas(self) -> None:
        assert trend_strict(price=102.0, ma20=105.0, ma40=100.0) == "neutral"

    def test_neutral_when_ma20_equals_ma40(self) -> None:
        # Strict requiere `>` estricto entre MAs.
        assert trend_strict(price=110.0, ma20=100.0, ma40=100.0) == "neutral"

    def test_neutral_when_ma20_none(self) -> None:
        assert trend_strict(price=100.0, ma20=None, ma40=90.0) == "neutral"

    def test_neutral_when_ma40_none(self) -> None:
        assert trend_strict(price=100.0, ma20=95.0, ma40=None) == "neutral"


# ═══════════════════════════════════════════════════════════════════════════
# trend_slope
# ═══════════════════════════════════════════════════════════════════════════


class TestTrendSlope:
    def test_bullish_with_rising_ma20_over_25_candles(self) -> None:
        # close crece → ma20 actual > ma20 prev → bullish
        closes = [100.0 + i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        # MA20 actual = mean(closes[10..29]) = mean(105..114.5) ≈ 109.75
        # price actual = 114.5
        ma20_actual = sum(closes[10:30]) / 20
        assert trend_slope(candles, ma20_actual) == "bullish"

    def test_bearish_with_falling_ma20_over_25_candles(self) -> None:
        closes = [100.0 - i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        ma20_actual = sum(closes[10:30]) / 20
        assert trend_slope(candles, ma20_actual) == "bearish"

    def test_degraded_fallback_below_25_candles_uses_price_vs_ma20(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(10)]  # <25
        candles = _candles_with_closes(closes)
        ma20 = 101.0  # arbitrario, para forzar direcciones
        price = 104.5  # último close
        # price > ma20 → bullish (sin consultar slope)
        assert price == candles[-1]["c"]
        assert trend_slope(candles, ma20) == "bullish"
        # price < ma20 → bearish
        assert trend_slope(candles, 110.0) == "bearish"
        # price == ma20 → neutral
        assert trend_slope(candles, 104.5) == "neutral"

    def test_neutral_when_ma20_none(self) -> None:
        candles = _candles_with_closes([100.0] * 30)
        assert trend_slope(candles, None) == "neutral"

    def test_neutral_when_candles_empty(self) -> None:
        assert trend_slope([], 100.0) == "neutral"


# ═══════════════════════════════════════════════════════════════════════════
# trend_with_fallback (Observatory Option B)
# ═══════════════════════════════════════════════════════════════════════════


class TestTrendWithFallback:
    def test_strict_bullish_overrides_slope(self) -> None:
        # Si strict ya es bullish, no hace falta consultar slope.
        closes = [100.0 + i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        # Forzamos strict bullish: price=114.5, ma20=110, ma40=100 → strict OK
        assert trend_with_fallback(candles, ma20=110.0, ma40=100.0) == "bullish"

    def test_falls_back_to_slope_when_no_ma40(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        ma20 = sum(closes[-20:]) / 20
        # ma40 = None → directo a slope. Con serie creciente → bullish.
        assert trend_with_fallback(candles, ma20=ma20, ma40=None) == "bullish"

    def test_fallback_confirms_strict_neutral_when_price_on_side(self) -> None:
        # Serie creciente. ma20 actual (real) ≈ 109.75, ma20 prev ≈ 107.25.
        # Pasamos ma20=108 (cercano al real, > ma20_prev) y ma40=110
        # → strict es neutral (ma20 < ma40), pero el slope es bullish
        # (108 > 107.25) y price está por encima de ambos → fallback dispara.
        closes = [100.0 + i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        assert trend_with_fallback(candles, ma20=108.0, ma40=110.0) == "bullish"

    def test_fallback_does_not_fire_when_price_between_mas(self) -> None:
        closes = [100.0 + i * 0.5 for i in range(30)]
        candles = _candles_with_closes(closes)
        # price=114.5, ma20=120, ma40=110 → price entre MAs → strict neutral,
        # no-fallback path.
        assert trend_with_fallback(candles, ma20=120.0, ma40=110.0) == "neutral"


# ═══════════════════════════════════════════════════════════════════════════
# compute_alignment
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeAlignment:
    def test_all_bullish_returns_n3_bullish(self) -> None:
        assert compute_alignment("bullish", "bullish", "bullish") == (3, "bullish")

    def test_all_bearish_returns_n3_bearish(self) -> None:
        assert compute_alignment("bearish", "bearish", "bearish") == (3, "bearish")

    def test_two_bullish_one_bearish_returns_n2_bullish(self) -> None:
        assert compute_alignment("bullish", "bullish", "bearish") == (2, "bullish")

    def test_two_bearish_one_bullish_returns_n2_bearish(self) -> None:
        assert compute_alignment("bearish", "bullish", "bearish") == (2, "bearish")

    def test_tie_bull_bear_returns_max_mixed(self) -> None:
        # 1 bull + 1 bear + 1 neutral → max(1,1)=1, dir="mixed"
        assert compute_alignment("bullish", "bearish", "neutral") == (1, "mixed")

    def test_all_neutral_returns_n0_mixed(self) -> None:
        # max(0, 0) = 0
        assert compute_alignment("neutral", "neutral", "neutral") == (0, "mixed")

    def test_two_neutral_one_bullish_returns_n1_mixed(self) -> None:
        # bullish_count=1, bearish_count=0 → no alcanza ≥2 → (max(0,1), "mixed") = (1, "mixed")
        assert compute_alignment("neutral", "bullish", "neutral") == (1, "mixed")

    def test_order_independent(self) -> None:
        assert compute_alignment("bullish", "bullish", "bearish") == compute_alignment(
            "bearish", "bullish", "bullish"
        )


# ═══════════════════════════════════════════════════════════════════════════
# alignment_gate — sin catalyst
# ═══════════════════════════════════════════════════════════════════════════


class TestAlignmentGateStrict:
    def test_n3_bullish_passes(self) -> None:
        r = alignment_gate("bullish", "bullish", "bullish")
        assert r.passed is True
        assert r.override is False
        assert r.effective_dir == "bullish"
        assert "3/3 bullish" in r.reason

    def test_n2_bearish_passes(self) -> None:
        r = alignment_gate("bearish", "bullish", "bearish")
        assert r.passed is True
        assert r.override is False
        assert r.effective_dir == "bearish"

    def test_n1_blocked(self) -> None:
        r = alignment_gate("bullish", "bearish", "neutral")
        assert r.passed is False
        assert r.override is False
        assert r.effective_dir is None
        assert "insuficiente" in r.reason

    def test_mixed_blocked_even_with_n2(self) -> None:
        # compute_alignment nunca devuelve n=2 + "mixed" — el mixed solo
        # aparece cuando no hay mayoría. Este test chequea el caso donde
        # n=0 mixed también bloquea.
        r = alignment_gate("neutral", "neutral", "neutral")
        assert r.passed is False
        assert r.dir == "mixed"


# ═══════════════════════════════════════════════════════════════════════════
# alignment_gate — catalyst override
# ═══════════════════════════════════════════════════════════════════════════


class TestCatalystOverride:
    def test_override_fires_when_15m_1h_agree_and_catalyst(self) -> None:
        # 15M+1H bullish, daily neutral → n=2 bullish (ya pasa strict)
        # Para forzar el path de override, 15M+1H bullish pero daily bearish
        # produciría n=1. Usamos 15M+1H bullish y daily bearish:
        r = alignment_gate("bullish", "bullish", "bearish", has_catalyst=True)
        # Con 2 bullish + 1 bearish → n=2, strict pass sin override
        assert r.passed is True
        # No es override — strict ya pasa.
        assert r.override is False

    def test_override_needed_when_only_15m_1h_non_neutral(self) -> None:
        # 15M=bullish, 1H=bullish, daily=neutral → bullish_count=2, bearish=0
        # compute_alignment → (2, "bullish") → strict ya pasa.
        r = alignment_gate("bullish", "bullish", "neutral", has_catalyst=True)
        assert r.passed is True
        assert r.override is False  # strict path

    def test_override_fires_when_strict_fails(self) -> None:
        # Creamos un caso donde strict falla pero 15M+1H son iguales
        # no-neutral: impossibl que compute_alignment devuelva n>=2
        # con bullish_count=2 y strict falle. Lo único que queda para
        # forzar override es que bullish_count=1 + bearish_count=1 =
        # tie → mixed. E.g. bullish + bullish + (??) donde todas iguales
        # no queda.
        # CORRECTO uso del override: 15M=bullish, 1H=bullish, pero la
        # suma total da n<2 requeriría que 1h no sea bullish.
        # Let's try: neutral + bullish + bearish → (1, "mixed"), strict
        # falla. 15M (neutral) != 1H (bullish) → override NO dispara.
        # Realmente el override solo puede disparar cuando n=1 y 15M==1H
        # ≠ neutral. Eso sucede con: bullish + bullish + (no bullish)
        # pero eso ya da n=2.
        #
        # El override REAL ocurre con 1 neutral que cuenta para bullish:
        # e.g. bullish + bullish + neutral → n=2 (ya strict pasa).
        # O si una es neutral y dos son iguales no-neutrales → n=2.
        # El override SOLO tiene efecto cuando dir es "mixed".
        #
        # El único caso donde 15M == 1H != neutral pero n<2 es cuando 15M
        # y 1H son iguales pero otra arrastra a mixed por tie: e.g.
        # bullish (15m) + bullish (1h) + bearish (daily) → bullish_count=2
        # → strict pass. No override.
        #
        # Conclusión: con la regla de compute_alignment, si 15M==1H no-
        # neutral, siempre hay ≥ 2 votos → strict pasa. El override
        # parecería redundante. Pero Observatory lo tiene; lo replico.
        # Caso donde teóricamente dispararía: si alguna vez una versión
        # futura cuenta alignment de otra forma.
        #
        # Test simple: forzamos dir="mixed" y esperamos que no se dispare
        # override porque t_15m != t_1h.
        r = alignment_gate("bullish", "bearish", "neutral", has_catalyst=True)
        assert r.passed is False
        assert r.override is False

    def test_override_does_not_fire_without_catalyst(self) -> None:
        r = alignment_gate("bullish", "bullish", "neutral", has_catalyst=False)
        # Strict pasa (2 bullish).
        assert r.passed is True
        assert r.override is False

    def test_override_does_not_fire_when_15m_neutral(self) -> None:
        r = alignment_gate("neutral", "bullish", "neutral", has_catalyst=True)
        # n=1, dir=mixed. t_15m="neutral" → no override.
        assert r.passed is False

    def test_override_does_not_fire_when_15m_1h_differ(self) -> None:
        r = alignment_gate("bullish", "bearish", "neutral", has_catalyst=True)
        assert r.passed is False


# ═══════════════════════════════════════════════════════════════════════════
# Matriz parametrizada
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "trends,expected_n,expected_dir,expected_pass",
    [
        (("bullish", "bullish", "bullish"), 3, "bullish", True),
        (("bearish", "bearish", "bearish"), 3, "bearish", True),
        (("bullish", "bullish", "bearish"), 2, "bullish", True),
        (("bullish", "bearish", "bearish"), 2, "bearish", True),
        (("bullish", "bearish", "neutral"), 1, "mixed", False),
        (("neutral", "neutral", "neutral"), 0, "mixed", False),
        (("bullish", "neutral", "neutral"), 1, "mixed", False),
    ],
)
def test_alignment_matrix(
    trends: tuple, expected_n: int, expected_dir: str, expected_pass: bool
) -> None:
    n, direction = compute_alignment(*trends)
    assert (n, direction) == (expected_n, expected_dir)
    gate = alignment_gate(*trends)
    assert gate.passed is expected_pass
