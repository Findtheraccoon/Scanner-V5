"""Tests del loader/validador de fixtures.

Cubren:
  - Happy path con el canonical real `backend/fixtures/qqq_canonical_v1.json`.
  - Todos los códigos FIX-XXX que el módulo emite (FIX-000/001/003/005/
    006/007/011/020/021/022/023/024).
  - parse_fixture() consumible para dicts construidos en memoria.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from modules.fixtures import (
    CONFIRM_CATEGORIES,
    FIX_000,
    FIX_001,
    FIX_003,
    FIX_005,
    FIX_006,
    FIX_007,
    FIX_011,
    FIX_020,
    FIX_021,
    FIX_022,
    FIX_023,
    FIX_024,
    Fixture,
    FixtureError,
    load_fixture,
    parse_fixture,
)

# Path al canonical QQQ real que vive en el repo.
# tests/modules/fixtures/test_loader.py → subir 3 niveles → backend/
_BACKEND_DIR = Path(__file__).resolve().parents[3]
_QQQ_CANONICAL = _BACKEND_DIR / "fixtures" / "qqq_canonical_v1.json"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _valid_fixture_dict() -> dict:
    """Construye una fixture válida mínima para modificar en los tests."""
    return {
        "metadata": {
            "fixture_id": "test_v5_0_0",
            "fixture_version": "5.0.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "generated_from": "unit-test fabricated",
            "description": "Fixture sintética para tests del loader",
            "author": "pytest",
            "notes": None,
        },
        "ticker_info": {
            "ticker": "QQQ",
            "benchmark": "SPY",
            "requires_spy_daily": True,
            "requires_bench_daily": True,
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


def _assert_fix_code(err: FixtureError, expected: str) -> None:
    assert err.code == expected, f"expected {expected}, got {err.code}: {err.detail}"


# ═══════════════════════════════════════════════════════════════════════════
# Happy path — canonical real
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_load_qqq_canonical_v1(self) -> None:
        fixture = load_fixture(_QQQ_CANONICAL)
        assert isinstance(fixture, Fixture)
        assert fixture.metadata.fixture_id == "qqq_canonical_v1"
        assert fixture.ticker_info.ticker == "QQQ"
        assert fixture.ticker_info.benchmark == "SPY"
        assert len(fixture.score_bands) == 6
        # 10 categorías — las que manda el spec.
        assert set(fixture.confirm_weights.keys()) == set(CONFIRM_CATEGORIES)

    def test_parse_fixture_dict_roundtrip(self) -> None:
        data = _valid_fixture_dict()
        fixture = parse_fixture(data)
        assert fixture.metadata.fixture_id == "test_v5_0_0"
        assert fixture.confirm_weights["FzaRel"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# FIX-000: I/O y JSON parse
# ═══════════════════════════════════════════════════════════════════════════


class TestIOErrors:
    def test_file_not_found_raises_fix000(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.json"
        with pytest.raises(FixtureError) as exc_info:
            load_fixture(missing)
        _assert_fix_code(exc_info.value, FIX_000)

    def test_malformed_json_raises_fix000(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not-json")
        with pytest.raises(FixtureError) as exc_info:
            load_fixture(bad)
        _assert_fix_code(exc_info.value, FIX_000)

    def test_top_level_array_raises_fix000(self, tmp_path: Path) -> None:
        bad = tmp_path / "arr.json"
        bad.write_text("[1, 2, 3]")
        with pytest.raises(FixtureError) as exc_info:
            load_fixture(bad)
        _assert_fix_code(exc_info.value, FIX_000)


# ═══════════════════════════════════════════════════════════════════════════
# FIX-007: bloque top-level desconocido
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownTopLevelBlock:
    def test_extra_top_level_block_raises_fix007(self) -> None:
        data = _valid_fixture_dict()
        data["trigger_weights"] = {"ORB": 2}  # prohibido en schema v5.0.0
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_007)


# ═══════════════════════════════════════════════════════════════════════════
# FIX-001: campos obligatorios faltantes / tipos inválidos
# ═══════════════════════════════════════════════════════════════════════════


class TestMissingOrMalformedFields:
    def test_missing_top_level_block_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        del data["ticker_info"]
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)

    def test_missing_metadata_required_field_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        del data["metadata"]["fixture_id"]
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)

    def test_detection_threshold_out_of_range_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        data["detection_thresholds"]["fzarel_min_divergence_pct"] = 10.0  # > 5.0
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)

    def test_volhigh_min_ratio_not_gt_1_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        data["detection_thresholds"]["volhigh_min_ratio"] = 1.0  # debe ser > 1.0
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)

    def test_ticker_info_extra_field_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        data["ticker_info"]["unknown_field"] = "oops"
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)


# ═══════════════════════════════════════════════════════════════════════════
# FIX-003 / FIX-005 / FIX-006: confirm_weights
# ═══════════════════════════════════════════════════════════════════════════


class TestConfirmWeights:
    def test_missing_category_raises_fix003(self) -> None:
        data = _valid_fixture_dict()
        del data["confirm_weights"]["FzaRel"]
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_003)
        assert "FzaRel" in exc_info.value.detail

    def test_unknown_category_raises_fix005(self) -> None:
        data = _valid_fixture_dict()
        data["confirm_weights"]["BogusConfirm"] = 2
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_005)
        assert "BogusConfirm" in exc_info.value.detail

    def test_weight_above_max_raises_fix006(self) -> None:
        data = _valid_fixture_dict()
        data["confirm_weights"]["FzaRel"] = 15
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_006)

    def test_negative_weight_raises_fix006(self) -> None:
        data = _valid_fixture_dict()
        data["confirm_weights"]["FzaRel"] = -1
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_006)

    def test_boolean_weight_rejected_as_fix006(self) -> None:
        # bool es subclass de int en Python — excluir explícitamente.
        data = _valid_fixture_dict()
        data["confirm_weights"]["FzaRel"] = True
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_006)

    def test_weight_zero_is_valid(self) -> None:
        data = _valid_fixture_dict()
        data["confirm_weights"]["FzaRel"] = 0
        fixture = parse_fixture(data)
        assert fixture.confirm_weights["FzaRel"] == 0

    def test_weight_exactly_ten_is_valid(self) -> None:
        data = _valid_fixture_dict()
        data["confirm_weights"]["FzaRel"] = 10
        fixture = parse_fixture(data)
        assert fixture.confirm_weights["FzaRel"] == 10


# ═══════════════════════════════════════════════════════════════════════════
# FIX-011: ticker_info inconsistencia
# ═══════════════════════════════════════════════════════════════════════════


class TestTickerInfoConsistency:
    def test_benchmark_null_with_requires_true_raises_fix011(self) -> None:
        data = _valid_fixture_dict()
        data["ticker_info"]["benchmark"] = None
        data["ticker_info"]["requires_bench_daily"] = True
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_011)

    def test_benchmark_set_with_requires_false_raises_fix011(self) -> None:
        data = _valid_fixture_dict()
        data["ticker_info"]["benchmark"] = "SPY"
        data["ticker_info"]["requires_bench_daily"] = False
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_011)

    def test_benchmark_null_with_requires_false_is_valid(self) -> None:
        data = _valid_fixture_dict()
        data["ticker_info"]["ticker"] = "SPY"
        data["ticker_info"]["benchmark"] = None
        data["ticker_info"]["requires_bench_daily"] = False
        fixture = parse_fixture(data)
        assert fixture.ticker_info.benchmark is None


# ═══════════════════════════════════════════════════════════════════════════
# FIX-020..024: score_bands
# ═══════════════════════════════════════════════════════════════════════════


class TestScoreBands:
    def test_gap_between_bands_raises_fix020(self) -> None:
        data = _valid_fixture_dict()
        # S tiene min=14, A+ tiene max=14. Crear un gap cambiando A+.max a 13.
        data["score_bands"][2]["max"] = 13.0
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_020)

    def test_overlap_between_bands_raises_fix021(self) -> None:
        data = _valid_fixture_dict()
        # S tiene min=14. Hacer A+.max=15 → solapa.
        data["score_bands"][2]["max"] = 15.0
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_021)

    def test_top_band_without_null_max_raises_fix022(self) -> None:
        data = _valid_fixture_dict()
        data["score_bands"][0]["max"] = 20.0  # ya no es null
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_022)

    def test_non_top_band_with_null_max_raises_fix022(self) -> None:
        data = _valid_fixture_dict()
        data["score_bands"][2]["max"] = None  # A+ no debería tener null max
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_022)

    def test_negative_bottom_min_raises_fix023(self) -> None:
        data = _valid_fixture_dict()
        # Última banda REVISAR con min=-1, ajustar max de la anterior para
        # mantener contiguidad.
        data["score_bands"][-1]["min"] = -1.0
        data["score_bands"][-1]["max"] = 4.0  # sin cambio
        data["score_bands"][-2]["min"] = 4.0  # B sin cambio; mantener anterior
        # Antes de llegar a FIX-023 podría tropezar con contiguidad;
        # mantenemos bands[-1].max == bands[-2].min, que es 4.0 == 4.0 ✓
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_023)

    def test_duplicate_label_raises_fix024(self) -> None:
        data = _valid_fixture_dict()
        data["score_bands"][1]["label"] = "A"  # duplica con banda 3
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_024)

    def test_empty_score_bands_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        data["score_bands"] = []
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)

    def test_invalid_signal_value_raises_fix001(self) -> None:
        data = _valid_fixture_dict()
        data["score_bands"][0]["signal"] = "BUY"  # no es SETUP/REVISAR/NEUTRAL
        with pytest.raises(FixtureError) as exc_info:
            parse_fixture(data)
        _assert_fix_code(exc_info.value, FIX_001)


# ═══════════════════════════════════════════════════════════════════════════
# Inmutabilidad y roundtrip
# ═══════════════════════════════════════════════════════════════════════════


class TestImmutability:
    def test_fixture_is_frozen(self) -> None:
        fixture = parse_fixture(_valid_fixture_dict())
        with pytest.raises((TypeError, ValueError)):
            fixture.ticker_info = None  # type: ignore[misc]

    def test_roundtrip_json(self) -> None:
        original = parse_fixture(_valid_fixture_dict())
        dumped = original.model_dump_json()
        # parse_fixture espera un dict, así que decodeamos primero.
        restored = parse_fixture(json.loads(dumped))
        assert restored == original


# ═══════════════════════════════════════════════════════════════════════════
# Sanity: no mutamos el dict original en parse_fixture
# ═══════════════════════════════════════════════════════════════════════════


class TestNoMutation:
    def test_parse_fixture_does_not_mutate_input(self) -> None:
        data = _valid_fixture_dict()
        snapshot = copy.deepcopy(data)
        parse_fixture(data)
        assert data == snapshot
