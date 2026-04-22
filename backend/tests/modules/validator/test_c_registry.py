"""Tests del Check C — validación del Slot Registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from engines.scoring import ENGINE_VERSION
from modules.slot_registry import REG_001, REG_002
from modules.validator.checks import c_registry
from tests.modules.slot_registry.test_loader import _write_registry


@pytest.mark.asyncio
async def test_skip_when_no_path() -> None:
    result = await c_registry.run(
        registry_path=None, engine_version=ENGINE_VERSION,
    )
    assert result.status == "skip"


@pytest.mark.asyncio
async def test_pass_healthy_registry(tmp_path: Path) -> None:
    registry_path = _write_registry(tmp_path)
    result = await c_registry.run(
        registry_path=registry_path,
        engine_version=ENGINE_VERSION,
        fixtures_root=tmp_path,
    )
    assert result.status == "pass"
    assert result.details["operative_count"] == 1
    assert result.details["degraded_count"] == 0
    assert result.details["disabled_count"] == 5


@pytest.mark.asyncio
async def test_fatal_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.json"
    result = await c_registry.run(
        registry_path=missing, engine_version=ENGINE_VERSION,
    )
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert result.error_code == REG_001


@pytest.mark.asyncio
async def test_fatal_when_file_malformed(tmp_path: Path) -> None:
    bad = tmp_path / "slot_registry.json"
    bad.write_text("{ not valid json")
    result = await c_registry.run(
        registry_path=bad, engine_version=ENGINE_VERSION,
    )
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert result.error_code == REG_002


@pytest.mark.asyncio
async def test_degraded_when_fixture_missing(tmp_path: Path) -> None:
    """Slot con fixture_path que apunta a archivo inexistente → DEGRADED."""
    registry_path = _write_registry(
        tmp_path,
        slot_overrides=[
            {"slot": 1, "ticker": "QQQ", "fixture": "fixtures/ghost.json",
             "benchmark": "SPY", "enabled": True},
            *[
                {"slot": i, "ticker": None, "fixture": None,
                 "benchmark": None, "enabled": False}
                for i in range(2, 7)
            ],
        ],
    )
    result = await c_registry.run(
        registry_path=registry_path,
        engine_version=ENGINE_VERSION,
        fixtures_root=tmp_path,
    )
    assert result.status == "fail"
    assert result.severity == "degraded"
    assert result.error_code is not None
    assert result.details["degraded_count"] == 1
    assert result.details["operative_count"] == 0
