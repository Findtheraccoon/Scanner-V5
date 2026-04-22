"""Tests del `writer.py` del slot_registry.

Validan:

- Round-trip con `load_registry()`: save → load reproduce el mismo
  registro (lo que importa: slot/ticker/fixture/benchmark/enabled).
- Escritura atómica: si el destino existe y la escritura falla, el
  archivo original queda intacto (no corrupto).
- Mapeo `status → enabled`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.slot_registry import (
    SlotRegistry,
    load_registry,
    save_registry,
)
from tests.modules.slot_registry.test_loader import (
    ENGINE_V,
    _write_registry,
)


class TestSerializationShape:
    def test_top_level_keys(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(registry, out)
        data = json.loads(out.read_text())
        assert set(data.keys()) == {"registry_metadata", "slots"}

    def test_slot_fields(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(registry, out)
        data = json.loads(out.read_text())
        slot1 = data["slots"][0]
        assert set(slot1.keys()) == {
            "slot", "enabled", "ticker", "fixture",
            "benchmark", "priority", "notes",
        }
        assert slot1["slot"] == 1
        assert slot1["enabled"] is True
        assert slot1["ticker"] == "QQQ"
        assert slot1["fixture"] == "fixtures/qqq_v5_2_0.json"

    def test_six_slots_always(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(registry, out)
        data = json.loads(out.read_text())
        assert len(data["slots"]) == 6
        assert [s["slot"] for s in data["slots"]] == [1, 2, 3, 4, 5, 6]

    def test_disabled_slots_serialize_as_enabled_false(
        self, tmp_path: Path,
    ) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(registry, out)
        data = json.loads(out.read_text())
        for raw_slot in data["slots"][1:]:  # slots 2-6 están DISABLED
            assert raw_slot["enabled"] is False


class TestRoundTrip:
    def test_save_then_load_preserves_operative_slot(
        self, tmp_path: Path,
    ) -> None:
        path = _write_registry(tmp_path)
        original = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(original, out)

        # Copiar la fixture + canonical al mismo dir para que load_registry
        # las encuentre con fixtures_root=tmp_path.
        reloaded = load_registry(
            out, engine_version=ENGINE_V, fixtures_root=tmp_path,
        )
        assert isinstance(reloaded, SlotRegistry)
        assert len(reloaded.operative_slots) == 1
        assert reloaded.operative_slots[0].ticker == "QQQ"
        assert reloaded.operative_slots[0].slot == 1

    def test_save_then_load_preserves_disabled_slots(
        self, tmp_path: Path,
    ) -> None:
        path = _write_registry(tmp_path)
        original = load_registry(path, engine_version=ENGINE_V)
        out = tmp_path / "copy.json"
        save_registry(original, out)

        reloaded = load_registry(
            out, engine_version=ENGINE_V, fixtures_root=tmp_path,
        )
        assert len(reloaded.disabled_slots) == 5


class TestAtomicWrite:
    def test_existing_file_unchanged_if_write_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Si `os.replace` falla, el archivo original no queda corrupto."""
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)

        # Snapshot del archivo original
        original_bytes = path.read_bytes()

        # Forzar un fallo en os.replace
        import os as _os
        original_replace = _os.replace

        def _fail_replace(src, dst):  # type: ignore[no-untyped-def]
            raise OSError("simulated failure")

        monkeypatch.setattr(_os, "replace", _fail_replace)

        with pytest.raises(OSError, match="simulated failure"):
            save_registry(registry, path)

        # Restaurar por las dudas (pytest lo hace igual)
        monkeypatch.setattr(_os, "replace", original_replace)

        # El archivo destino sigue intacto
        assert path.read_bytes() == original_bytes

        # Y no quedó basura de tempfile en el dir
        leftover = [
            p for p in tmp_path.iterdir()
            if p.name.startswith(f".{path.name}.") and p.name.endswith(".tmp")
        ]
        assert leftover == []

    def test_creates_parent_dir_if_missing(self, tmp_path: Path) -> None:
        path = _write_registry(tmp_path)
        registry = load_registry(path, engine_version=ENGINE_V)
        nested = tmp_path / "sub" / "dir" / "registry.json"
        save_registry(registry, nested)
        assert nested.is_file()
