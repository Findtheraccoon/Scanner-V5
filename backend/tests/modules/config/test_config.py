"""Tests del Config encriptado (B — `modules/config/`)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modules.config import (
    MasterKeyError,
    S3Config,
    TDKeyConfig,
    UserConfig,
    decrypt_str,
    encrypt_str,
    get_master_key,
    load_config,
    save_config,
)

# ══════════════════════════════════════════════════════════════════
# crypto.py
# ══════════════════════════════════════════════════════════════════


class TestMasterKey:
    def test_env_var_takes_precedence(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """Si `SCANNER_MASTER_KEY` está seteada, se usa sobre cualquier file."""
        from cryptography.fernet import Fernet

        env_key = Fernet.generate_key()
        monkeypatch.setenv("SCANNER_MASTER_KEY", env_key.decode())

        file_path = tmp_path / "master.key"
        file_path.write_bytes(Fernet.generate_key())

        # Debe devolver la del env, no la del file.
        assert get_master_key(file_path) == env_key

    def test_loads_from_file(self, tmp_path: Path, monkeypatch) -> None:
        from cryptography.fernet import Fernet

        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = Fernet.generate_key()
        p = tmp_path / "master.key"
        p.write_bytes(key)
        assert get_master_key(p) == key

    def test_autogenerate_when_missing(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        from cryptography.fernet import Fernet

        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        p = tmp_path / "master.key"
        assert not p.exists()
        key = get_master_key(p)
        # Debe haberse creado el archivo
        assert p.is_file()
        assert p.read_bytes() == key
        # Y es una Fernet key válida
        Fernet(key)

    def test_autogenerate_false_raises(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        with pytest.raises(MasterKeyError, match="auto_generate=False"):
            get_master_key(tmp_path / "missing.key", auto_generate=False)

    def test_invalid_env_key_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("SCANNER_MASTER_KEY", "not-a-valid-fernet-key")
        with pytest.raises(MasterKeyError, match="válida"):
            get_master_key()

    def test_invalid_file_key_raises(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        p = tmp_path / "master.key"
        p.write_bytes(b"garbage")
        with pytest.raises(MasterKeyError, match="inválida"):
            get_master_key(p)


class TestEncryptDecrypt:
    def test_round_trip(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = get_master_key(tmp_path / "master.key")
        ct = encrypt_str("hello world", key)
        assert ct != "hello world"  # encrypted
        assert decrypt_str(ct, key) == "hello world"

    def test_decrypt_with_wrong_key_raises(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        from cryptography.fernet import Fernet

        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key1 = get_master_key(tmp_path / "k1.key")
        key2 = Fernet.generate_key()
        ct = encrypt_str("secret", key1)
        with pytest.raises(MasterKeyError, match="No se pudo desencriptar"):
            decrypt_str(ct, key2)


# ══════════════════════════════════════════════════════════════════
# loader.py + models.py
# ══════════════════════════════════════════════════════════════════


class TestSaveLoadRoundTrip:
    def test_empty_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = get_master_key(tmp_path / "master.key")
        cfg_path = tmp_path / "config.json"
        cfg = UserConfig()
        save_config(cfg, cfg_path, master_key=key)
        assert cfg_path.is_file()

        loaded = load_config(cfg_path, master_key=key)
        assert loaded == cfg

    def test_with_td_keys_and_s3(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = get_master_key(tmp_path / "master.key")
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
        save_config(cfg, cfg_path, master_key=key)

        loaded = load_config(cfg_path, master_key=key)
        assert loaded == cfg
        assert loaded.twelvedata_keys[0].secret == "super-secret-td"
        assert loaded.s3_config.access_key_id == "aws-key-123"
        assert loaded.api_bearer_token == "sk-scanner-abc"


class TestSecretsAreEncryptedOnDisk:
    def test_plaintext_not_present(self, tmp_path: Path, monkeypatch) -> None:
        """Verifica que los secretos NO aparezcan en cleartext en el JSON."""
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = get_master_key(tmp_path / "master.key")
        cfg = UserConfig(
            twelvedata_keys=[
                TDKeyConfig(key_id="k1", secret="LEAKED-IF-PLAINTEXT"),
            ],
            s3_config=S3Config(
                bucket="b",
                access_key_id="LEAKED-KEY",
                secret_access_key="LEAKED-SECRET",
            ),
            api_bearer_token="LEAKED-TOKEN",
        )
        cfg_path = tmp_path / "config.json"
        save_config(cfg, cfg_path, master_key=key)

        raw = cfg_path.read_text()
        # Ninguno de los secretos aparece en el JSON raw
        for needle in (
            "LEAKED-IF-PLAINTEXT", "LEAKED-KEY",
            "LEAKED-SECRET", "LEAKED-TOKEN",
        ):
            assert needle not in raw, f"secret {needle!r} leaked to disk"

        # Los campos `_enc` sí están
        data = json.loads(raw)
        assert "twelvedata_keys_enc" in data
        assert "s3_config_enc" in data
        assert "api_bearer_token_enc" in data

    def test_load_with_wrong_key_fails(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        from cryptography.fernet import Fernet

        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        k1 = get_master_key(tmp_path / "k1.key")
        k2 = Fernet.generate_key()

        cfg = UserConfig(api_bearer_token="secret-token")
        p = tmp_path / "c.json"
        save_config(cfg, p, master_key=k1)

        with pytest.raises(MasterKeyError):
            load_config(p, master_key=k2)


class TestAtomicWrite:
    def test_existing_file_unchanged_on_error(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        monkeypatch.delenv("SCANNER_MASTER_KEY", raising=False)
        key = get_master_key(tmp_path / "master.key")
        p = tmp_path / "config.json"
        save_config(UserConfig(name="original"), p, master_key=key)
        original_bytes = p.read_bytes()

        # Forzar fallo en os.replace
        import os as _os
        orig = _os.replace

        def _fail(*a, **kw):
            raise OSError("simulated")

        monkeypatch.setattr(_os, "replace", _fail)
        with pytest.raises(OSError, match="simulated"):
            save_config(UserConfig(name="new"), p, master_key=key)
        monkeypatch.setattr(_os, "replace", orig)

        assert p.read_bytes() == original_bytes
        # Sin tempfile residual
        leftovers = [
            f for f in tmp_path.iterdir()
            if f.name.startswith(f".{p.name}.") and f.name.endswith(".tmp")
        ]
        assert leftovers == []
