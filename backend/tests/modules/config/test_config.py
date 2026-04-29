"""Tests del Config plaintext (`modules/config/`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from modules.config import (
    S3Config,
    StartupFlags,
    TDKeyConfig,
    UserConfig,
    load_config,
    save_config,
)


class TestSaveLoadRoundTrip:
    def test_empty_config(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "config.json"
        cfg = UserConfig()
        save_config(cfg, cfg_path)
        assert cfg_path.is_file()

        loaded = load_config(cfg_path)
        assert loaded == cfg

    def test_with_td_keys_and_s3(self, tmp_path: Path) -> None:
        cfg = UserConfig(
            name="trader-alvaro",
            twelvedata_keys=[
                TDKeyConfig(
                    key_id="k1", secret="super-secret-td",
                    credits_per_minute=8, credits_per_day=800,
                ),
                TDKeyConfig(
                    key_id="k2", secret="another-secret",
                    enabled=False,
                ),
            ],
            s3_config=S3Config(
                bucket="my-bucket",
                access_key_id="aws-key-123",
                secret_access_key="aws-secret-xyz",
                region="us-east-1",
            ),
            api_bearer_token="sk-scanner-abc",
            registry_path="slot_registry.json",
            preferences={"theme": "dark"},
            auto_last_enabled=True,
        )
        cfg_path = tmp_path / "config.json"
        save_config(cfg, cfg_path)

        loaded = load_config(cfg_path)
        assert loaded == cfg
        assert loaded.twelvedata_keys[0].secret == "super-secret-td"
        assert loaded.s3_config is not None
        assert loaded.s3_config.access_key_id == "aws-key-123"
        assert loaded.api_bearer_token == "sk-scanner-abc"

    def test_with_startup_flags(self, tmp_path: Path) -> None:
        cfg = UserConfig(
            startup_flags=StartupFlags(
                validator_run_at_startup=False,
                validator_parity_enabled=True,
                validator_parity_limit=None,
                heartbeat_interval_s=60.0,
                rotate_on_shutdown=True,
                aggressive_rotation_enabled=True,
                aggressive_rotation_interval_s=1800.0,
                db_size_limit_mb=10000,
            ),
        )
        cfg_path = tmp_path / "c.json"
        save_config(cfg, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded.startup_flags.validator_run_at_startup is False
        assert loaded.startup_flags.validator_parity_limit is None
        assert loaded.startup_flags.heartbeat_interval_s == 60.0
        assert loaded.startup_flags.aggressive_rotation_enabled is True


class TestPlaintextOnDisk:
    def test_secrets_written_as_plaintext(self, tmp_path: Path) -> None:
        """Modelo plaintext — los secretos viven en claro en el archivo
        por decisión de producto. La seguridad depende de dónde el
        usuario almacene el `.config`."""
        cfg = UserConfig(
            twelvedata_keys=[
                TDKeyConfig(key_id="k1", secret="td-secret-123"),
            ],
            s3_config=S3Config(
                bucket="b",
                access_key_id="ACCESS-KEY",
                secret_access_key="SECRET-KEY",
            ),
            api_bearer_token="bearer-xyz",
        )
        cfg_path = tmp_path / "c.json"
        save_config(cfg, cfg_path)

        raw = cfg_path.read_text()
        # En plaintext los secretos sí aparecen — el contrato es ese.
        assert "td-secret-123" in raw
        assert "ACCESS-KEY" in raw
        assert "SECRET-KEY" in raw
        assert "bearer-xyz" in raw

        # No hay campos `_enc` (modelo plaintext, no encriptado).
        data = json.loads(raw)
        assert "twelvedata_keys" in data
        assert "twelvedata_keys_enc" not in data


class TestAtomicWrite:
    def test_existing_file_unchanged_on_error(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        p = tmp_path / "config.json"
        save_config(UserConfig(name="original"), p)
        original_bytes = p.read_bytes()

        import os as _os
        orig = _os.replace

        def _fail(*a, **kw):
            raise OSError("simulated")

        monkeypatch.setattr(_os, "replace", _fail)
        with pytest.raises(OSError, match="simulated"):
            save_config(UserConfig(name="new"), p)
        monkeypatch.setattr(_os, "replace", orig)

        assert p.read_bytes() == original_bytes
        leftovers = [
            f for f in tmp_path.iterdir()
            if f.name.startswith(f".{p.name}.") and f.name.endswith(".tmp")
        ]
        assert leftovers == []


class TestSchemaValidation:
    def test_rejects_extra_fields_on_load(self, tmp_path: Path) -> None:
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"name": "x", "unknown_field": True}))
        with pytest.raises(ValidationError, match=r"[Ee]xtra"):
            load_config(p)

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")
