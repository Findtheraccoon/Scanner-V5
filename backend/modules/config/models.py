"""Modelos del Config del usuario (spec §3.5 + §4.8).

Schema del archivo `config_*.json` que persiste el estado configurable
del scanner. Los campos sensibles (API keys TD, credenciales S3, API
bearer token del scanner) se encriptan **inline** al guardar y se
desencriptan al cargar.

**Diseño de encripción:**

Los secretos viven en el `UserConfig` como plaintext strings en
runtime. La persistencia JSON los serializa como ciphertext en campos
separados con sufijo `_enc`:

    {
      "name": "trader-alvaro",
      "twelvedata_keys_enc": "<fernet-token-base64>",
      "s3_config_enc": "<fernet-token-base64>",
      "api_bearer_token_enc": "<fernet-token-base64>",
      "preferences": {...},
      "fixture_path_by_slot": {...},
      ...
    }

El loader (`load_config`) desencripta; el writer (`save_config`)
encripta. El objeto `UserConfig` en memoria tiene los plaintext en
sus fields regulares — el caller no necesita saber de encripción.

**Pydantic frozen + extra=forbid** — cambios al schema requieren bump
explícito del `schema_version`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class S3Config(BaseModel):
    """Credenciales + ubicación del bucket S3-compatible.

    Mismo shape que `modules.db.backup.S3Config`, pero separado porque
    aquí vive en el Config del usuario (encriptado) y allá se acepta
    en el body de requests transitorios.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint_url: str | None = None
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"
    key_prefix: str = "scanner-backups/"


class TDKeyConfig(BaseModel):
    """Una API key de Twelve Data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key_id: str
    secret: str
    credits_per_minute: int = 8
    credits_per_day: int = 800
    enabled: bool = True


class UserConfig(BaseModel):
    """Config del usuario. Los secretos viven en plaintext acá; la
    persistencia los encripta al serializar."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0.0")
    name: str = Field(default="default")

    # Secretos (encriptados en persistencia)
    twelvedata_keys: list[TDKeyConfig] = Field(default_factory=list)
    s3_config: S3Config | None = None
    api_bearer_token: str | None = Field(
        default=None,
        description=(
            "Bearer token del propio scanner (ADR-0001). Autogenerado "
            "al primer arranque si es None."
        ),
    )

    # No-secretos
    registry_path: str = Field(default="slot_registry.json")
    preferences: dict[str, Any] = Field(default_factory=dict)
    auto_last_enabled: bool = Field(default=False)

    def has_td_keys(self) -> bool:
        return bool(self.twelvedata_keys)

    def enabled_td_keys(self) -> list[TDKeyConfig]:
        return [k for k in self.twelvedata_keys if k.enabled]
