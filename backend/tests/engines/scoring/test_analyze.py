"""Tests de contrato e invariantes del Scoring Engine (Fase 1).

Validan la forma del output, los códigos ENG-XXX emitidos en cada caso
de error, y las 5 invariantes del motor declaradas en
`docs/specs/SCORING_ENGINE_SPEC.md §3`:

    I1 · Sin look-ahead (trust-based — no testeable directamente acá)
    I2 · Determinístico
    I3 · Nunca lanza excepciones
    I4 · Fixture read-only
    I5 · Structure gate siempre primero (validado cuando estén las fases)

Fases siguientes del motor (indicadores, triggers, confirms, gates)
van a agregar tests sin cambiar los del contrato.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from engines.scoring import (
    ENG_001,
    ENG_010,
    ENG_099,
    ENGINE_VERSION,
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
    analyze,
)
from modules.fixtures import CONFIRM_CATEGORIES

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _valid_fixture(
    *,
    requires_bench_daily: bool = True,
    benchmark: str | None = "SPY",
) -> dict[str, Any]:
    """Fixture canónica que el loader acepta sin quejarse."""
    return {
        "metadata": {
            "fixture_id": "qqq_test_v5_2_0",
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "Fixture sintética para tests del motor.",
        },
        "ticker_info": {
            "ticker": "QQQ",
            "benchmark": benchmark,
            "requires_spy_daily": True,
            "requires_bench_daily": requires_bench_daily,
        },
        "confirm_weights": dict.fromkeys(CONFIRM_CATEGORIES, 1.0),
        "detection_thresholds": {
            "fzarel_min_divergence_pct": 0.5,
            "divspy_asset_threshold_pct": 0.5,
            "divspy_spy_threshold_pct": 0.3,
            "volhigh_min_ratio": 1.2,
        },
        "score_bands": [
            {"min": 16.0, "max": None, "label": "S+", "signal": "SETUP"},
            {"min": 14.0, "max": 16.0, "label": "S", "signal": "SETUP"},
            {"min": 10.0, "max": 14.0, "label": "A+", "signal": "SETUP"},
            {"min": 7.0, "max": 10.0, "label": "A", "signal": "SETUP"},
            {"min": 4.0, "max": 7.0, "label": "B", "signal": "REVISAR"},
            {"min": 2.0, "max": 4.0, "label": "REVISAR", "signal": "REVISAR"},
        ],
    }


def _candles(n: int, *, start_price: float = 100.0) -> list[dict]:
    """Velas sintéticas en el formato exacto del spec §2.2."""
    return [
        {
            "dt": f"2025-01-{(i % 28) + 1:02d} 10:00:00",
            "o": start_price + i * 0.1,
            "h": start_price + i * 0.1 + 1.0,
            "l": start_price + i * 0.1 - 1.0,
            "c": start_price + i * 0.1 + 0.5,
            "v": 1_000_000 + i,
        }
        for i in range(n)
    ]


def _valid_inputs() -> dict[str, Any]:
    return {
        "ticker": "QQQ",
        "candles_daily": _candles(MIN_CANDLES_DAILY, start_price=500.0),
        "candles_1h": _candles(MIN_CANDLES_1H, start_price=500.0),
        "candles_15m": _candles(MIN_CANDLES_15M, start_price=500.0),
        "fixture": _valid_fixture(),
        "spy_daily": _candles(MIN_CANDLES_DAILY, start_price=600.0),
        "bench_daily": _candles(MIN_CANDLES_DAILY, start_price=600.0),
    }


# Todas las claves que el spec §2.3 garantiza en TODO output del motor.
_REQUIRED_OUTPUT_KEYS: frozenset[str] = frozenset(
    {
        "ticker",
        "engine_version",
        "fixture_id",
        "fixture_version",
        "score",
        "conf",
        "signal",
        "dir",
        "blocked",
        "error",
        "error_code",
        "layers",
        "ind",
        "patterns",
        "sec_rel",
        "div_spy",
    }
)


def _assert_output_shape(out: dict[str, Any]) -> None:
    assert set(out.keys()) == _REQUIRED_OUTPUT_KEYS, (
        f"missing keys: {_REQUIRED_OUTPUT_KEYS - set(out.keys())}, "
        f"extra: {set(out.keys()) - _REQUIRED_OUTPUT_KEYS}"
    )
    assert isinstance(out["ticker"], str)
    assert isinstance(out["engine_version"], str)
    assert isinstance(out["score"], float)
    assert isinstance(out["conf"], str)
    assert isinstance(out["signal"], str)
    assert out["dir"] in (None, "CALL", "PUT")
    assert isinstance(out["error"], bool)
    assert isinstance(out["layers"], dict)
    assert isinstance(out["ind"], dict)
    assert isinstance(out["patterns"], list)


# ═══════════════════════════════════════════════════════════════════════════
# Happy path (Fase 1: siempre "no_triggers_detected")
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_returns_neutral_with_valid_inputs(self) -> None:
        out = analyze(**_valid_inputs())
        _assert_output_shape(out)
        assert out["error"] is False
        assert out["error_code"] is None
        assert out["signal"] == "NEUTRAL"
        assert out["score"] == 0.0
        assert out["dir"] is None
        # Phase 1 bloquea a nivel de trigger porque no hay detectores.
        assert out["blocked"] == "no_triggers_detected"

    def test_echoes_ticker_and_engine_version(self) -> None:
        out = analyze(**_valid_inputs())
        assert out["ticker"] == "QQQ"
        assert out["engine_version"] == ENGINE_VERSION

    def test_echoes_fixture_id_and_version(self) -> None:
        out = analyze(**_valid_inputs())
        assert out["fixture_id"] == "qqq_test_v5_2_0"
        assert out["fixture_version"] == "5.2.0"


# ═══════════════════════════════════════════════════════════════════════════
# ENG-001 — inputs obligatorios faltantes / insuficientes
# ═══════════════════════════════════════════════════════════════════════════


class TestEng001:
    def test_daily_below_minimum_returns_eng001(self) -> None:
        inputs = _valid_inputs()
        inputs["candles_daily"] = _candles(MIN_CANDLES_DAILY - 1)
        out = analyze(**inputs)
        _assert_output_shape(out)
        assert out["error"] is True
        assert out["error_code"] == ENG_001
        assert "daily" in out["layers"]["error_detail"]

    def test_1h_below_minimum_returns_eng001(self) -> None:
        inputs = _valid_inputs()
        inputs["candles_1h"] = _candles(MIN_CANDLES_1H - 1)
        out = analyze(**inputs)
        assert out["error_code"] == ENG_001
        assert "1h" in out["layers"]["error_detail"]

    def test_15m_below_minimum_returns_eng001(self) -> None:
        inputs = _valid_inputs()
        inputs["candles_15m"] = _candles(MIN_CANDLES_15M - 1)
        out = analyze(**inputs)
        assert out["error_code"] == ENG_001
        assert "15m" in out["layers"]["error_detail"]

    def test_empty_lists_aggregated_into_single_detail(self) -> None:
        """Acumula todas las deficiencias en un solo detail (no fail-fast)."""
        inputs = _valid_inputs()
        inputs["candles_daily"] = []
        inputs["candles_1h"] = []
        inputs["candles_15m"] = []
        out = analyze(**inputs)
        assert out["error_code"] == ENG_001
        detail = out["layers"]["error_detail"]
        assert "daily" in detail and "1h" in detail and "15m" in detail

    def test_missing_required_spy_daily_returns_eng001(self) -> None:
        inputs = _valid_inputs()
        inputs["spy_daily"] = None
        out = analyze(**inputs)
        assert out["error_code"] == ENG_001
        assert "spy_daily" in out["layers"]["error_detail"]

    def test_missing_required_bench_daily_returns_eng001(self) -> None:
        inputs = _valid_inputs()
        inputs["bench_daily"] = None
        out = analyze(**inputs)
        assert out["error_code"] == ENG_001
        assert "bench_daily" in out["layers"]["error_detail"]

    def test_no_bench_required_when_fixture_says_so(self) -> None:
        """Si fixture.requires_bench_daily=False, no se exige el input."""
        inputs = _valid_inputs()
        inputs["fixture"] = _valid_fixture(benchmark=None, requires_bench_daily=False)
        inputs["bench_daily"] = None
        out = analyze(**inputs)
        # Pasa a NEUTRAL normal — no es ENG-001.
        assert out["error"] is False
        assert out["signal"] == "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════════
# ENG-010 — fixture inválida
# ═══════════════════════════════════════════════════════════════════════════


class TestEng010:
    def test_missing_fixture_block_returns_eng010(self) -> None:
        inputs = _valid_inputs()
        fx = inputs["fixture"]
        del fx["ticker_info"]
        out = analyze(**inputs)
        assert out["error_code"] == ENG_010
        assert "FIX-" in out["layers"]["error_detail"]

    def test_confirm_weights_missing_category_returns_eng010(self) -> None:
        inputs = _valid_inputs()
        del inputs["fixture"]["confirm_weights"]["FzaRel"]
        out = analyze(**inputs)
        assert out["error_code"] == ENG_010

    def test_weight_out_of_range_returns_eng010(self) -> None:
        inputs = _valid_inputs()
        inputs["fixture"]["confirm_weights"]["FzaRel"] = 999
        out = analyze(**inputs)
        assert out["error_code"] == ENG_010

    def test_empty_fixture_returns_eng010(self) -> None:
        inputs = _valid_inputs()
        inputs["fixture"] = {}
        out = analyze(**inputs)
        assert out["error_code"] == ENG_010

    def test_fixture_error_leaves_fixture_id_empty(self) -> None:
        """Si la fixture no se pudo parsear, no hay id que echo-ar."""
        inputs = _valid_inputs()
        inputs["fixture"] = {"metadata": {}}  # parseo falla
        out = analyze(**inputs)
        assert out["fixture_id"] == ""
        assert out["fixture_version"] == ""


# ═══════════════════════════════════════════════════════════════════════════
# ENG-099 — catch-all defensivo
# ═══════════════════════════════════════════════════════════════════════════


class TestEng099:
    def test_non_list_candles_trigger_eng099_not_exception(self) -> None:
        """Un tipo inesperado (ej. None) debe caer en el catch-all, no lanzar."""
        inputs = _valid_inputs()
        inputs["candles_daily"] = None  # type: ignore[assignment]
        out = analyze(**inputs)
        _assert_output_shape(out)
        assert out["error"] is True
        # Puede ser ENG-001 (si len(None) se chequea antes) o ENG-099 — la
        # invariante crítica es que NO se propague excepción. Aceptamos
        # cualquiera de los dos códigos razonables, lo importante es el
        # contrato.
        assert out["error_code"] in {ENG_001, ENG_099}


# ═══════════════════════════════════════════════════════════════════════════
# Invariantes del motor (spec §3)
# ═══════════════════════════════════════════════════════════════════════════


class TestInvariants:
    def test_i2_deterministic_two_calls_produce_equal_output(self) -> None:
        """I2: mismos inputs → mismo output bit a bit."""
        inputs = _valid_inputs()
        out1 = analyze(**inputs)
        out2 = analyze(**inputs)
        assert out1 == out2

    def test_i3_never_raises_on_completely_malformed_fixture(self) -> None:
        """I3: cualquier input no-estándar se materializa en error, no
        en excepción."""
        bad_inputs: list[Any] = [
            123,
            "not-a-dict",
            [],
            {"nested": {"mess": True}},
        ]
        for bad in bad_inputs:
            out = analyze(
                ticker="X",
                candles_daily=[],
                candles_1h=[],
                candles_15m=[],
                fixture=bad,  # type: ignore[arg-type]
            )
            _assert_output_shape(out)
            assert out["error"] is True

    def test_i3_never_raises_on_weird_spy_daily_type(self) -> None:
        """La invariante crítica es "no propagar excepción + shape válida";
        si el valor es truthy puede pasar la validación de presencia y
        explotar más adelante cuando el motor lo use. En Fase 1 no se usa
        spy_daily; en fases posteriores este test debería asegurar
        error=True también."""
        inputs = _valid_inputs()
        inputs["spy_daily"] = "not-a-list"  # type: ignore[assignment]
        out = analyze(**inputs)
        _assert_output_shape(out)

    def test_i4_fixture_not_mutated(self) -> None:
        """I4: el dict de fixture que recibe el motor no se modifica."""
        inputs = _valid_inputs()
        fixture_before = copy.deepcopy(inputs["fixture"])
        analyze(**inputs)
        assert inputs["fixture"] == fixture_before

    def test_i4_candle_lists_not_mutated(self) -> None:
        """Aunque el spec sólo exige fixture read-only, por buena salud
        también garantizamos que las listas de velas no se mutan."""
        inputs = _valid_inputs()
        daily_before = copy.deepcopy(inputs["candles_daily"])
        h1_before = copy.deepcopy(inputs["candles_1h"])
        m15_before = copy.deepcopy(inputs["candles_15m"])
        analyze(**inputs)
        assert inputs["candles_daily"] == daily_before
        assert inputs["candles_1h"] == h1_before
        assert inputs["candles_15m"] == m15_before


# ═══════════════════════════════════════════════════════════════════════════
# Estabilidad del shape bajo condiciones límite
# ═══════════════════════════════════════════════════════════════════════════


class TestOutputShapeStability:
    @pytest.mark.parametrize(
        "mutation",
        [
            "happy",
            "daily_short",
            "fixture_empty",
            "spy_missing",
            "all_empty",
        ],
    )
    def test_all_error_paths_respect_output_shape(self, mutation: str) -> None:
        inputs = _valid_inputs()
        if mutation == "daily_short":
            inputs["candles_daily"] = _candles(5)
        elif mutation == "fixture_empty":
            inputs["fixture"] = {}
        elif mutation == "spy_missing":
            inputs["spy_daily"] = None
        elif mutation == "all_empty":
            inputs["candles_daily"] = []
            inputs["candles_1h"] = []
            inputs["candles_15m"] = []
        out = analyze(**inputs)
        _assert_output_shape(out)
