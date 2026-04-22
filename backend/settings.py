"""Configuración del backend via Pydantic Settings (D.3).

Carga variables de entorno con prefix `SCANNER_`. Soporta `.env` para
desarrollo local. En producción (instalado en Windows vía Inno Setup,
spec §5.4), las credenciales encriptadas vendrán del Config via
`modules.config/` — eso es scope fuera de D.

**Variables de entorno reconocidas:**

| Var                              | Default               | Uso |
|----------------------------------|-----------------------|------|
| `SCANNER_API_KEYS`               | `""` (→ exit 1)       | CSV de Bearer tokens válidos |
| `SCANNER_DB_PATH`                | `"data/scanner.db"`   | Ruta al archivo SQLite |
| `SCANNER_HOST`                   | `"127.0.0.1"`         | Host del server |
| `SCANNER_PORT`                   | `8000`                | Puerto (1-65535) |
| `SCANNER_HEARTBEAT_INTERVAL_S`   | `120.0`               | Segundos entre heartbeats |
| `SCANNER_AUTO_SCHEDULER_ENABLED` | `false`               | Activa scheduler AUTO stub |
| `SCANNER_AUTO_SCHEDULER_INTERVAL_S` | `60.0`             | Segundos entre ticks stub |
| `SCANNER_SHUTDOWN_TIMEOUT_S`     | `30.0`                | Timeout graceful (spec §4.3) |
| `SCANNER_LOG_LEVEL`              | `"INFO"`              | Nivel de loguru |
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SCANNER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_keys: str = Field(default="", description="CSV de API keys")
    db_path: str = Field(default="data/scanner.db")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000, ge=1, le=65535)
    heartbeat_interval_s: float = Field(default=120.0, gt=0)
    auto_scheduler_enabled: bool = Field(default=False)
    auto_scheduler_interval_s: float = Field(default=60.0, gt=0)
    shutdown_timeout_s: float = Field(default=30.0, gt=0)
    log_level: str = Field(default="INFO")

    # Scan loop real (DE.3 + SR.2) — requiere provider + slot_registry
    twelvedata_keys: str = Field(
        default="",
        description="CSV de API keys de TwelveData (`key_id:secret:cpm:cpd`)",
    )
    registry_path: str = Field(
        default="slot_registry.json",
        description="Ruta al `slot_registry.json` (spec §3.3 — fuente de verdad de slots + fixtures)",
    )
    scan_delay_after_close_s: float = Field(default=3.0, gt=0)

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, v: str) -> str:
        return v.upper()

    @property
    def api_keys_set(self) -> set[str]:
        """Parsea el CSV de api_keys → set."""
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}

    def parse_twelvedata_keys(self) -> list[dict]:
        """Parsea `twelvedata_keys` en formato `key_id:secret:cpm:cpd` CSV.

        Returns:
            Lista de dicts `{key_id, secret, credits_per_minute,
            credits_per_day}` aptos para `ApiKeyConfig(**d)`.
        """
        out: list[dict] = []
        for entry in self.twelvedata_keys.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) != 4:
                raise ValueError(
                    f"TWELVEDATA_KEYS entry malformed: {entry!r}. "
                    "Expected `key_id:secret:cpm:cpd`.",
                )
            key_id, secret, cpm, cpd = parts
            out.append(
                {
                    "key_id": key_id,
                    "secret": secret,
                    "credits_per_minute": int(cpm),
                    "credits_per_day": int(cpd),
                },
            )
        return out
