"""Tests del Check B — validación de canonicals (hash SHA-256)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from engines.registry_runtime import RegistryRuntime
from engines.scoring import ENGINE_VERSION
from modules.slot_registry import REG_020, load_registry
from modules.validator.checks import b_canonicals
from tests.modules.slot_registry.test_loader import _fixture_dict, _write_registry


def _setup(tmp_path: Path, **kwargs) -> tuple[Path, RegistryRuntime]:
    registry_path = _write_registry(tmp_path, **kwargs)
    registry = load_registry(registry_path, engine_version=ENGINE_VERSION)
    runtime = RegistryRuntime(registry)
    return registry_path.parent, runtime


@pytest.mark.asyncio
async def test_skip_when_no_registry(tmp_path: Path) -> None:
    result = await b_canonicals.run(registry=None, fixtures_root=tmp_path)
    assert result.status == "skip"


@pytest.mark.asyncio
async def test_pass_valid_canonical(tmp_path: Path) -> None:
    root, runtime = _setup(tmp_path)
    result = await b_canonicals.run(registry=runtime, fixtures_root=root)
    assert result.status == "pass"
    canonicals = result.details["canonicals"]
    assert len(canonicals) == 1
    assert canonicals[0]["status"] == "ok"
    assert canonicals[0]["canonical_ref"] == "qqq_canonical_v1"


@pytest.mark.asyncio
async def test_fatal_on_hash_mismatch(tmp_path: Path) -> None:
    """Si el canonical fue modificado sin actualizar el .sha256 → fatal."""
    root, runtime = _setup(tmp_path)
    # Reescribo el canonical.json para que el hash no coincida
    canonical_json = root / "fixtures" / "qqq_canonical_v1.json"
    canonical_json.write_text('{"tampered": true}')

    result = await b_canonicals.run(registry=runtime, fixtures_root=root)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert result.error_code == REG_020

    canonicals = result.details["canonicals"]
    mismatches = [c for c in canonicals if c["status"] == "hash_mismatch"]
    assert len(mismatches) == 1
    # Verificamos que reporta el hash actual vs esperado
    assert "expected" in mismatches[0]
    assert "actual" in mismatches[0]
    new_hash = hashlib.sha256(canonical_json.read_bytes()).hexdigest().lower()
    assert mismatches[0]["actual"] == new_hash


@pytest.mark.asyncio
async def test_fatal_on_missing_canonical_files(tmp_path: Path) -> None:
    """Si el .json o .sha256 del canonical no existe → fatal."""
    root, runtime = _setup(tmp_path)
    (root / "fixtures" / "qqq_canonical_v1.json").unlink()

    result = await b_canonicals.run(registry=runtime, fixtures_root=root)
    assert result.status == "fail"
    assert result.severity == "fatal"
    canonicals = result.details["canonicals"]
    missing = [c for c in canonicals if c["status"] == "missing"]
    assert len(missing) == 1


@pytest.mark.asyncio
async def test_skip_canonical_when_fixture_has_no_canonical_ref(
    tmp_path: Path,
) -> None:
    """Fixtures sin canonical_ref no aportan al reporte (se omiten)."""
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    fx_no_canonical = _fixture_dict(ticker="QQQ", canonical_ref=None)
    (fixtures_dir / "qqq.json").write_text(json.dumps(fx_no_canonical))

    registry_data = {
        "registry_metadata": {
            "registry_version": "1.0.0",
            "engine_version_required": ">=5.2.0,<6.0.0",
            "generated_at": "2025-03-10T00:00:00Z",
        },
        "slots": [
            {"slot": 1, "ticker": "QQQ", "fixture": "fixtures/qqq.json",
             "benchmark": "SPY", "enabled": True},
            *[
                {"slot": i, "ticker": None, "fixture": None,
                 "benchmark": None, "enabled": False}
                for i in range(2, 7)
            ],
        ],
    }
    path = tmp_path / "slot_registry.json"
    path.write_text(json.dumps(registry_data))

    registry = load_registry(path, engine_version=ENGINE_VERSION)
    runtime = RegistryRuntime(registry)

    result = await b_canonicals.run(registry=runtime, fixtures_root=tmp_path)
    assert result.status == "pass"
    # Sin canonical_ref, no aparece nada en el reporte
    assert result.details["canonicals"] == []
