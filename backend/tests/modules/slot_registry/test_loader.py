"""Tests del loader del slot_registry.

Construyen árboles de archivos en `tmp_path` (registry + fixtures +
canonicals) y verifican los caminos felices y los códigos REG-XXX +
FIX-XXX que el loader debe producir en cada caso.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from modules.fixtures import CONFIRM_CATEGORIES
from modules.slot_registry import (
    REG_001,
    REG_002,
    REG_003,
    REG_004,
    REG_005,
    REG_010,
    REG_011,
    REG_012,
    REG_013,
    REG_020,
    REG_030,
    REG_101,
    RegistryError,
    SlotRegistry,
    load_registry,
)

ENGINE_V = "5.2.0"


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _fixture_dict(
    *,
    ticker: str = "QQQ",
    benchmark: str | None = "SPY",
    canonical_ref: str | None = "qqq_canonical_v1",
    engine_compat_range: str = ">=5.2.0,<6.0.0",
    requires_bench_daily: bool | None = None,
) -> dict[str, Any]:
    if requires_bench_daily is None:
        requires_bench_daily = benchmark is not None
    return {
        "metadata": {
            "fixture_id": f"{ticker.lower()}_v5_2_0",
            "fixture_version": "5.2.0",
            "engine_compat_range": engine_compat_range,
            "canonical_ref": canonical_ref,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": f"Fixture test para {ticker}",
        },
        "ticker_info": {
            "ticker": ticker,
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


def _write_canonical_with_hash(
    fixtures_dir: Path,
    canonical_name: str,
    fixture_data: dict[str, Any],
    *,
    corrupt_hash: bool = False,
) -> None:
    """Escribe `{canonical_name}.json` + su `.sha256` en `fixtures_dir`."""
    canonical_path = fixtures_dir / f"{canonical_name}.json"
    canonical_path.write_text(json.dumps(fixture_data))
    actual_hash = hashlib.sha256(canonical_path.read_bytes()).hexdigest()
    hash_path = fixtures_dir / f"{canonical_name}.sha256"
    if corrupt_hash:
        actual_hash = "0" * 64
    hash_path.write_text(f"{actual_hash}  {canonical_path.name}\n")


def _write_registry(
    tmp_path: Path,
    *,
    slot_overrides: list[dict] | None = None,
    engine_version_required: str = ">=5.2.0,<6.0.0",
    skip_canonicals: bool = False,
    corrupt_canonical_hash: bool = False,
) -> Path:
    """Escribe un registry completo + fixture QQQ enabled + canonical.

    `slot_overrides` reemplaza los 6 slots. Si None, se usa 1 enabled
    con QQQ + 5 disabled. Útil para tests que quieren construir registries
    arbitrarios.
    """
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()

    # Fixture activa QQQ (siempre escrita, por si algún slot la usa)
    fx_data = _fixture_dict()
    (fixtures_dir / "qqq_v5_2_0.json").write_text(json.dumps(fx_data))

    # Canonical + sha256
    if not skip_canonicals:
        _write_canonical_with_hash(
            fixtures_dir,
            "qqq_canonical_v1",
            fx_data,
            corrupt_hash=corrupt_canonical_hash,
        )

    if slot_overrides is None:
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "baseline",
            },
        ] + [
            {
                "slot": i,
                "ticker": None,
                "fixture": None,
                "benchmark": None,
                "enabled": False,
                "priority": None,
                "notes": "libre",
            }
            for i in range(2, 7)
        ]
    else:
        slots = slot_overrides

    registry = {
        "registry_metadata": {
            "registry_version": "1.0.0",
            "engine_version_required": engine_version_required,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "test registry",
        },
        "slots": slots,
    }
    path = tmp_path / "slot_registry.json"
    path.write_text(json.dumps(registry))
    return path


def _assert_code(err: RegistryError, expected: str) -> None:
    assert err.code == expected, f"expected {expected}, got {err.code}: {err.detail}"


# ═══════════════════════════════════════════════════════════════════════════
# Happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    def test_load_minimal_registry(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        assert isinstance(registry, SlotRegistry)
        assert len(registry.slots) == 6
        assert len(registry.operative_slots) == 1
        assert len(registry.disabled_slots) == 5

        op = registry.operative_slots[0]
        assert op.slot == 1
        assert op.ticker == "QQQ"
        assert op.fixture is not None
        assert op.fixture.ticker_info.ticker == "QQQ"

    def test_ensure_at_least_one_operative_passes(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        registry.ensure_at_least_one_operative()  # no debe lanzar

    def test_slots_ordered_by_id(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        assert [s.slot for s in registry.slots] == [1, 2, 3, 4, 5, 6]


# ═══════════════════════════════════════════════════════════════════════════
# Fatal — estructura del archivo
# ═══════════════════════════════════════════════════════════════════════════


class TestFatalFileErrors:
    def test_file_not_found_raises_reg001(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.json"
        with pytest.raises(RegistryError) as exc_info:
            load_registry(missing, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_001)

    def test_invalid_json_raises_reg002(self, tmp_path: Path) -> None:
        bad = tmp_path / "slot_registry.json"
        bad.write_text("{not-json")
        with pytest.raises(RegistryError) as exc_info:
            load_registry(bad, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_002)

    def test_top_level_array_raises_reg002(self, tmp_path: Path) -> None:
        path = tmp_path / "slot_registry.json"
        path.write_text("[]")
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_002)

    def test_missing_top_level_block_raises_reg002(self, tmp_path: Path) -> None:
        path = tmp_path / "slot_registry.json"
        path.write_text(json.dumps({"registry_metadata": {}}))
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_002)

    def test_extra_top_level_block_raises_reg002(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        data = json.loads(path.read_text())
        data["extra_block"] = {"foo": "bar"}
        path.write_text(json.dumps(data))
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_002)


# ═══════════════════════════════════════════════════════════════════════════
# Fatal — slots (REG-003 / REG-004)
# ═══════════════════════════════════════════════════════════════════════════


class TestFatalSlotErrors:
    def test_wrong_slot_count_raises_reg003(self, tmp_path: Path) -> None:
        slots = [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(1, 6)
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_003)

    def test_duplicate_slot_id_raises_reg004(self, tmp_path: Path) -> None:
        slots = [
            {"slot": 1, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 1, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 3, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 4, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 5, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 6, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_004)

    def test_slot_ids_not_covering_1_to_6_raises_reg003(self, tmp_path: Path) -> None:
        slots = [
            {"slot": 1, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 2, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 3, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 4, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 5, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
            {"slot": 7, "enabled": False, "ticker": None, "fixture": None, "benchmark": None},
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_003)


# ═══════════════════════════════════════════════════════════════════════════
# Fatal — REG-030 (engine compat del registry)
# ═══════════════════════════════════════════════════════════════════════════


class TestEngineCompat:
    def test_registry_requires_future_engine_raises_reg030(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path, engine_version_required=">=6.0.0,<7.0.0")
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version="5.2.0")
        _assert_code(exc_info.value, REG_030)


# ═══════════════════════════════════════════════════════════════════════════
# Per-slot DEGRADED
# ═══════════════════════════════════════════════════════════════════════════


class TestPerSlotDegraded:
    def _registry_with_single_active_override(
        self, tmp_path: Path, override: dict[str, Any]
    ) -> Path:
        slot_1 = {
            "slot": 1,
            "ticker": "QQQ",
            "fixture": "fixtures/qqq_v5_2_0.json",
            "benchmark": "SPY",
            "enabled": True,
            "priority": "primary",
            "notes": "primary",
        }
        slot_1.update(override)
        slots = [slot_1] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(2, 7)
        ]
        return _write_registry(tmp_path, slot_overrides=slots)

    def test_fixture_file_missing_degrades_slot_reg010(self, tmp_path: Path) -> None:
        path = self._registry_with_single_active_override(
            tmp_path, {"fixture": "fixtures/does_not_exist.json"}
        )
        registry = load_registry(path, engine_version=ENGINE_V)
        assert len(registry.operative_slots) == 0
        degraded = registry.degraded_slots
        assert len(degraded) == 1
        assert degraded[0].error_code == REG_010

    def test_ticker_mismatch_degrades_slot_reg012(self, tmp_path: Path) -> None:
        path = self._registry_with_single_active_override(tmp_path, {"ticker": "SPY"})
        registry = load_registry(path, engine_version=ENGINE_V)
        assert registry.degraded_slots[0].error_code == REG_012

    def test_benchmark_mismatch_degrades_slot_reg013(self, tmp_path: Path) -> None:
        path = self._registry_with_single_active_override(tmp_path, {"benchmark": "QQQ"})
        registry = load_registry(path, engine_version=ENGINE_V)
        assert registry.degraded_slots[0].error_code == REG_013

    def test_fixture_engine_compat_incompatible_reg011(self, tmp_path: Path) -> None:
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        fx = _fixture_dict(engine_compat_range=">=6.0.0,<7.0.0")
        (fixtures_dir / "qqq_v5_2_0.json").write_text(json.dumps(fx))
        _write_canonical_with_hash(fixtures_dir, "qqq_canonical_v1", fx)
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "primary",
            }
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(2, 7)
        ]
        registry_data = {
            "registry_metadata": {
                "registry_version": "1.0.0",
                "engine_version_required": ">=5.2.0,<6.0.0",
                "generated_at": "2025-03-10T00:00:00Z",
            },
            "slots": slots,
        }
        path = tmp_path / "slot_registry.json"
        path.write_text(json.dumps(registry_data))
        registry = load_registry(path, engine_version=ENGINE_V)
        assert registry.degraded_slots[0].error_code == REG_011

    def test_malformed_fixture_degrades_with_fix_code(self, tmp_path: Path) -> None:
        """Errores FIX-XXX del loader de fixtures se propagan como DEGRADED."""
        fixtures_dir = tmp_path / "fixtures"
        fixtures_dir.mkdir()
        fx = _fixture_dict()
        del fx["confirm_weights"]["FzaRel"]  # provocará FIX-003
        (fixtures_dir / "qqq_v5_2_0.json").write_text(json.dumps(fx))
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "primary",
            }
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(2, 7)
        ]
        registry_data = {
            "registry_metadata": {
                "registry_version": "1.0.0",
                "engine_version_required": ">=5.2.0,<6.0.0",
                "generated_at": "2025-03-10T00:00:00Z",
            },
            "slots": slots,
        }
        path = tmp_path / "slot_registry.json"
        path.write_text(json.dumps(registry_data))
        registry = load_registry(path, engine_version=ENGINE_V)
        degraded = registry.degraded_slots
        assert len(degraded) == 1
        assert degraded[0].error_code == "FIX-003"

    def test_enabled_slot_without_ticker_or_fixture_reg010(self, tmp_path: Path) -> None:
        slots = [
            {
                "slot": 1,
                "enabled": True,
                "ticker": None,
                "fixture": None,
                "benchmark": None,
            }
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(2, 7)
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        registry = load_registry(path, engine_version=ENGINE_V)
        assert registry.degraded_slots[0].error_code == REG_010


# ═══════════════════════════════════════════════════════════════════════════
# Canonical hash (REG-010 DEGRADED / REG-020 FATAL)
# ═══════════════════════════════════════════════════════════════════════════


class TestCanonicalHash:
    def test_missing_canonical_files_degrade_slot_reg010(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path, skip_canonicals=True)
        registry = load_registry(path, engine_version=ENGINE_V)
        degraded = registry.degraded_slots
        assert len(degraded) == 1
        assert degraded[0].error_code == REG_010

    def test_corrupt_canonical_hash_is_fatal_reg020(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path, corrupt_canonical_hash=True)
        with pytest.raises(RegistryError) as exc_info:
            load_registry(path, engine_version=ENGINE_V)
        _assert_code(exc_info.value, REG_020)


# ═══════════════════════════════════════════════════════════════════════════
# Unicidad de tickers entre operativos (REG-005 per-slot DEGRADED)
# ═══════════════════════════════════════════════════════════════════════════


class TestDuplicateTicker:
    def test_duplicate_ticker_degrades_second_slot_reg005(self, tmp_path: Path) -> None:
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "first",
            },
            {
                "slot": 2,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "secondary",
                "notes": "duplicate",
            },
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(3, 7)
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        registry = load_registry(path, engine_version=ENGINE_V)
        op = registry.operative_slots
        deg = registry.degraded_slots
        assert len(op) == 1
        assert op[0].slot == 1
        assert len(deg) == 1
        assert deg[0].slot == 2
        assert deg[0].error_code == REG_005


# ═══════════════════════════════════════════════════════════════════════════
# REG-101 warning (slot disabled con campos populados)
# ═══════════════════════════════════════════════════════════════════════════


class TestDisabledWithPopulatedFields:
    def test_emits_reg101_warning(self, tmp_path: Path) -> None:
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/qqq_v5_2_0.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "primary",
            },
            {
                "slot": 2,
                "ticker": "PAUSED_SPY",  # disabled pero con campo
                "fixture": "fixtures/unused.json",
                "benchmark": "QQQ",
                "enabled": False,
                "priority": "secondary",
                "notes": "pausado temporalmente",
            },
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(3, 7)
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        registry = load_registry(path, engine_version=ENGINE_V)
        assert any(REG_101 in w for w in registry.warnings)
        # El slot queda DISABLED (no OPERATIVE ni DEGRADED).
        assert registry.slots[1].status == "DISABLED"


# ═══════════════════════════════════════════════════════════════════════════
# ensure_at_least_one_operative
# ═══════════════════════════════════════════════════════════════════════════


class TestEnsureAtLeastOneOperative:
    def test_raises_when_zero_operative(self, tmp_path: Path) -> None:
        slots = [
            {
                "slot": 1,
                "ticker": "QQQ",
                "fixture": "fixtures/does_not_exist.json",
                "benchmark": "SPY",
                "enabled": True,
                "priority": "primary",
                "notes": "will degrade",
            }
        ] + [
            {"slot": i, "enabled": False, "ticker": None, "fixture": None, "benchmark": None}
            for i in range(2, 7)
        ]
        path = _write_registry(tmp_path, slot_overrides=slots)
        registry = load_registry(path, engine_version=ENGINE_V)
        assert len(registry.operative_slots) == 0
        with pytest.raises(RegistryError) as exc_info:
            registry.ensure_at_least_one_operative()
        _assert_code(exc_info.value, REG_003)
