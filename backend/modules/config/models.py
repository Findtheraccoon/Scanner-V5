"""Modelos del Config del usuario (spec §3.5 + §4.8).

Schema del archivo `config_*.json` que persiste el estado configurable
del scanner. **El archivo es plaintext** — el usuario maneja el
`.config` como un documento (Cargar / Guardar / LAST), y es su
responsabilidad almacenarlo en lugar seguro. El sistema mismo no
persiste secretos: si no se carga ningún `.config`, el scanner
arranca de cero.

**Pydantic frozen + extra=forbid** — cambios al schema requieren bump
explícito del `schema_version`.

**Flags de arranque:** los campos en `startup_flags` reflejan los
toggles que también existen en `Settings` (env vars). El `.config`
override los defaults de `Settings` cuando está cargado.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class S3Config(BaseModel):
    """Credenciales + ubicación del bucket S3-compatible.

    Mismo shape que `modules.db.backup.S3Config`. Cuando hay un
    `.config` cargado, los endpoints `/database/{backup,restore,
    backups}` pueden tomar las credenciales de acá vía
    `app.state.user_config.s3_config` en lugar de body.
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


class StartupFlags(BaseModel):
    """Toggles de arranque persistibles en el `.config`.

    Cuando hay un `.config` cargado, estos campos override los
    defaults de `Settings` (env vars). Los cambios requieren reinicio
    del backend para tomar efecto en runtime — el frontend muestra
    "se aplica al próximo arranque" tras el `PUT`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    validator_run_at_startup: bool = True
    validator_parity_enabled: bool = True
    validator_parity_limit: int | None = 30
    heartbeat_interval_s: float = Field(default=120.0, gt=0)
    rotate_on_shutdown: bool = False
    aggressive_rotation_enabled: bool = False
    aggressive_rotation_interval_s: float = Field(default=3600.0, gt=0)
    db_size_limit_mb: int = Field(default=5000, gt=0)


class UserConfig(BaseModel):
    """Config del usuario en plaintext."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default="1.0.0")
    name: str = Field(default="default")

    twelvedata_keys: list[TDKeyConfig] = Field(default_factory=list)
    s3_config: S3Config | None = None
    api_bearer_token: str | None = Field(
        default=None,
        description=(
            "Bearer token del propio scanner (ADR-0001). Autogenerado "
            "al primer arranque si es None."
        ),
    )

    registry_path: str = Field(default="slot_registry.json")
    preferences: dict[str, Any] = Field(default_factory=dict)
    auto_last_enabled: bool = Field(default=False)
    startup_flags: StartupFlags = Field(default_factory=StartupFlags)

    def has_td_keys(self) -> bool:
        return bool(self.twelvedata_keys)

    def enabled_td_keys(self) -> list[TDKeyConfig]:
        return [k for k in self.twelvedata_keys if k.enabled]
