"""Persistencia del Config del usuario con encripción inline.

`load_config(path)` y `save_config(cfg, path)` son las dos operaciones
públicas. Internamente:

- **Save:** serializa `UserConfig`, encripta los 3 campos sensibles
  (`twelvedata_keys`, `s3_config`, `api_bearer_token`) como JSON blobs
  → Fernet ciphertext, y escribe el JSON final con los secretos como
  ciphertext en campos `<name>_enc`.
- **Load:** lee el JSON, desencripta cada `*_enc` a su field plaintext
  original, y construye el `UserConfig`.

**Atomic write:** tempfile + `os.replace`. Un crash a mitad no deja
el Config corrupto.

**Naming del archivo:** `data/config_<name>.json` por default. La
`master.key` vive al lado, en `data/master.key`.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from modules.config.crypto import decrypt_str, encrypt_str
from modules.config.models import S3Config, TDKeyConfig, UserConfig

_SECRET_FIELDS = ("twelvedata_keys", "s3_config", "api_bearer_token")


def save_config(
    cfg: UserConfig,
    path: str | Path,
    *,
    master_key: bytes | None = None,
) -> None:
    """Encripta secretos + escribe JSON atómicamente."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    plain = cfg.model_dump(mode="json")
    payload: dict[str, Any] = {}

    for key, value in plain.items():
        if key in _SECRET_FIELDS:
            # Encriptar el sub-payload (incluso si es None se serializa).
            ciphertext = encrypt_str(
                json.dumps(value, ensure_ascii=False), master_key,
            )
            payload[f"{key}_enc"] = ciphertext
        else:
            payload[key] = value

    raw = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(raw)
        os.replace(tmp_path, target)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def load_config(
    path: str | Path,
    *,
    master_key: bytes | None = None,
) -> UserConfig:
    """Lee el JSON, desencripta los `*_enc` y construye el modelo.

    Raises:
        FileNotFoundError: si `path` no existe.
        MasterKeyError: si algún secreto no se puede desencriptar.
        ValidationError: si el schema cambió y el archivo no matchea.
    """
    target = Path(path)
    raw = json.loads(target.read_text(encoding="utf-8"))

    payload: dict[str, Any] = {}
    for key, value in raw.items():
        if key.endswith("_enc"):
            base = key[:-4]
            if base not in _SECRET_FIELDS:
                continue
            plain_str = decrypt_str(value, master_key)
            payload[base] = json.loads(plain_str)
        else:
            payload[key] = value

    # Reconstruir sub-modelos explícitos (Pydantic acepta dicts).
    if payload.get("twelvedata_keys"):
        payload["twelvedata_keys"] = [
            TDKeyConfig(**k) for k in payload["twelvedata_keys"]
        ]
    if payload.get("s3_config"):
        payload["s3_config"] = S3Config(**payload["s3_config"])

    return UserConfig(**payload)
