"""Tests del Check A — validación de fixtures vía RegistryRuntime."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.registry_runtime import RegistryRuntime
from engines.scoring import ENGINE_VERSION
from modules.slot_registry import load_registry
from modules.validator.checks import a_fixtures
from tests.modules.slot_registry.test_loader import _fixture_dict, _write_registry


def _setup(tmp_path: Path) -> tuple[Path, RegistryRuntime]:
    registry_path = _write_registry(tmp_path)
    registry = load_registry(registry_path, engine_version=ENGINE_VERSION)
    runtime = RegistryRuntime(registry)
    return registry_path.parent, runtime


@pytest.mark.asyncio
async def test_skip_when_no_registry(tmp_path: Path) -> None:
    result = await a_fixtures.run(registry=None, fixtures_root=tmp_path)
    assert result.status == "skip"
    assert "no provistos" in (result.message or "")


@pytest.mark.asyncio
async def test_skip_when_no_fixtures_root(tmp_path: Path) -> None:
    _, runtime = _setup(tmp_path)
    result = await a_fixtures.run(registry=runtime, fixtures_root=None)
    assert result.status == "skip"


@pytest.mark.asyncio
async def test_pass_valid_fixtures(tmp_path: Path) -> None:
    root, runtime = _setup(tmp_path)
    result = await a_fixtures.run(registry=runtime, fixtures_root=root)
    assert result.status == "pass"
    assert result.severity is None
    fixtures = result.details["fixtures"]
    assert len(fixtures) == 1  # solo slot 1 es enabled
    assert fixtures[0]["status"] == "ok"
    assert fixtures[0]["slot"] == 1


@pytest.mark.asyncio
async def test_fail_degraded_on_invalid_fixture(tmp_path: Path) -> None:
    """Si una fixture tiene JSON inválido, el check falla con degraded."""
    # Escribo un registry normal, luego corrompo la fixture
    root, runtime = _setup(tmp_path)
    fixture_path = root / "fixtures" / "qqq_v5_2_0.json"
    fixture_path.write_text("{ not valid json")

    result = await a_fixtures.run(registry=runtime, fixtures_root=root)
    assert result.status == "fail"
    assert result.severity == "degraded"
    assert result.error_code is not None
    assert result.error_code.startswith("FIX-")

    fixtures = result.details["fixtures"]
    failed = [f for f in fixtures if f["status"] == "fail"]
    assert len(failed) == 1


@pytest.mark.asyncio
async def test_disabled_slots_not_validated(tmp_path: Path) -> None:
    """Los slots DISABLED no se chequean aunque tengan fixture_path."""
    root, runtime = _setup(tmp_path)
    result = await a_fixtures.run(registry=runtime, fixtures_root=root)
    # Solo slot 1 (el único enabled) aparece
    fixture_slots = [f["slot"] for f in result.details["fixtures"]]
    assert fixture_slots == [1]


@pytest.mark.asyncio
async def test_two_enabled_slots_both_validated(tmp_path: Path) -> None:
    """Cuando hay múltiples slots enabled, se validan todos."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    # 2 fixtures distintas — QQQ y SPY
    qqq = _fixture_dict(ticker="QQQ", canonical_ref=None)
    spy = _fixture_dict(ticker="SPY", benchmark=None, canonical_ref=None)
    (fixtures_dir / "qqq.json").write_text(json.dumps(qqq))
    (fixtures_dir / "spy.json").write_text(json.dumps(spy))

    registry = {
        "registry_metadata": {
            "registry_version": "1.0.0",
            "engine_version_required": ">=5.2.0,<6.0.0",
            "generated_at": "2025-03-10T00:00:00Z",
        },
        "slots": [
            {"slot": 1, "ticker": "QQQ", "fixture": "fixtures/qqq.json",
             "benchmark": "SPY", "enabled": True},
            {"slot": 2, "ticker": "SPY", "fixture": "fixtures/spy.json",
             "benchmark": None, "enabled": True},
            *[
                {"slot": i, "ticker": None, "fixture": None,
                 "benchmark": None, "enabled": False}
                for i in range(3, 7)
            ],
        ],
    }
    path = tmp_path / "slot_registry.json"
    path.write_text(json.dumps(registry))

    loaded = load_registry(path, engine_version=ENGINE_VERSION)
    runtime = RegistryRuntime(loaded)

    result = await a_fixtures.run(registry=runtime, fixtures_root=tmp_path)
    assert result.status == "pass"
    assert len(result.details["fixtures"]) == 2
