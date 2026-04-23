"""Encriptación simétrica para secretos del Config del usuario.

Usa `cryptography.fernet.Fernet` (AES-128-CBC + HMAC-SHA256) para
encriptar strings sensibles in-place en el JSON del Config.

**Master key:**

- Viene de la env var `SCANNER_MASTER_KEY` (base64url-encoded, 32 bytes).
- Si la env var no está, se lee (o crea) `data/master.key` con una key
  generada automáticamente al primer arranque.
- El archivo `master.key` debe quedar fuera del Config — vive al lado
  de la DB. Si se pierde, los secretos del Config no se pueden
  desencriptar (deben re-ingresarse).

**API:**

- `get_master_key(path=None)` → bytes Fernet key.
- `encrypt_str(plaintext)` → base64 ciphertext (str).
- `decrypt_str(ciphertext)` → plaintext (str).

Los helpers aceptan `master_key` override explícito para testing —
sin pasar nada usan `get_master_key()`.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_DEFAULT_KEY_PATH = Path("data/master.key")
_ENV_VAR = "SCANNER_MASTER_KEY"


class MasterKeyError(Exception):
    """La master key es inválida o no se puede cargar/generar."""


def get_master_key(
    path: Path | None = None,
    *,
    auto_generate: bool = True,
) -> bytes:
    """Devuelve la master key como bytes Fernet (base64url, 32 bytes).

    Orden de resolución:
    1. Env var `SCANNER_MASTER_KEY` (si está seteada).
    2. Archivo en disco `path` (default `data/master.key`).
    3. Si `auto_generate=True` y (1)+(2) fallan, genera nueva + escribe.

    Raises:
        MasterKeyError: si la key no es Fernet-válida o no se puede
            persistir cuando se requiere auto-generate.
    """
    env_val = os.environ.get(_ENV_VAR)
    if env_val:
        try:
            Fernet(env_val.encode())
        except Exception as e:
            raise MasterKeyError(
                f"{_ENV_VAR} no es una Fernet key válida: {e}",
            ) from e
        return env_val.encode()

    key_path = path or _DEFAULT_KEY_PATH
    if key_path.is_file():
        raw = key_path.read_bytes().strip()
        try:
            Fernet(raw)
        except Exception as e:
            raise MasterKeyError(
                f"{key_path} contiene una key inválida: {e}",
            ) from e
        return raw

    if not auto_generate:
        raise MasterKeyError(
            f"No hay master key en {_ENV_VAR} ni {key_path}, y "
            "auto_generate=False.",
        )

    # Auto-generate + persistir.
    new_key = Fernet.generate_key()
    try:
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(new_key)
        # Restringir permisos (POSIX). En Windows el chmod se ignora.
        with contextlib.suppress(OSError):
            os.chmod(key_path, 0o600)
    except OSError as e:
        raise MasterKeyError(
            f"No se pudo escribir master key en {key_path}: {e}",
        ) from e
    return new_key


def encrypt_str(plaintext: str, master_key: bytes | None = None) -> str:
    """Encripta `plaintext` y retorna el ciphertext base64 (str)."""
    key = master_key or get_master_key()
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_str(ciphertext: str, master_key: bytes | None = None) -> str:
    """Desencripta el ciphertext base64 y retorna el plaintext (str).

    Raises:
        MasterKeyError: si el ciphertext no puede desencriptarse con la
            master key actual (token corrupto o key incorrecta).
    """
    key = master_key or get_master_key()
    try:
        plain = Fernet(key).decrypt(ciphertext.encode("ascii"))
    except InvalidToken as e:
        raise MasterKeyError(
            "No se pudo desencriptar el ciphertext — master key "
            "probablemente distinta a la que lo generó",
        ) from e
    return plain.decode("utf-8")
