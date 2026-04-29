"""Persistencia plaintext del Config del usuario.

`load_config(path)` y `save_config(cfg, path)` son las dos operaciones
públicas. El archivo `.config` es JSON plaintext — el sistema **no
persiste secretos por su cuenta**: el `.config` es un documento que
el usuario maneja explícitamente (Cargar / Guardar / LAST). Si el
usuario no carga ningún `.config`, el scanner arranca de cero.

**Atomic write:** tempfile + `os.replace`. Un crash a mitad no deja
el archivo corrupto.

**Naming:** convención `data/config_<name>.json`, pero el path es
libre — el caller decide.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from modules.config.models import S3Config, TDKeyConfig, UserConfig


def save_config(cfg: UserConfig, path: str | Path) -> None:
    """Escribe el `UserConfig` como JSON plaintext atómicamente."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = cfg.model_dump(mode="json")
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


def load_config(path: str | Path) -> UserConfig:
    """Lee el JSON plaintext y construye el `UserConfig`.

    Raises:
        FileNotFoundError: si `path` no existe.
        ValidationError: si el schema no matchea (Pydantic).
        json.JSONDecodeError: si el archivo no es JSON válido.
    """
    target = Path(path)
    raw = json.loads(target.read_text(encoding="utf-8"))

    payload: dict[str, Any] = dict(raw)
    if payload.get("twelvedata_keys"):
        payload["twelvedata_keys"] = [
            TDKeyConfig(**k) for k in payload["twelvedata_keys"]
        ]
    if payload.get("s3_config"):
        payload["s3_config"] = S3Config(**payload["s3_config"])

    return UserConfig(**payload)
