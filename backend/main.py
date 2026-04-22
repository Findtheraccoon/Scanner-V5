#!/usr/bin/env python3
"""Entrypoint del backend Scanner V5.

Levanta FastAPI (REST + WebSocket) + workers de background (heartbeat,
auto scheduler stub). Config via Pydantic Settings (ver `settings.py`)
que lee de variables de entorno con prefix `SCANNER_`.

**Uso local:**

    SCANNER_API_KEYS="sk-dev-1,sk-dev-2" python -m backend.main

    # Con auto scheduler stub + intervalo corto para testing:
    SCANNER_API_KEYS="sk-dev" \\
    SCANNER_AUTO_SCHEDULER_ENABLED=true \\
    SCANNER_AUTO_SCHEDULER_INTERVAL_S=10 \\
    python -m backend.main

**Shutdown graceful (spec §4.3):** Uvicorn captura SIGINT/SIGTERM y
dispara el shutdown del lifespan, que cancela workers + dispose del
engine. Timeout de 30s default (configurable).
"""

from __future__ import annotations

import sys

import uvicorn
from loguru import logger

from api import create_app
from modules.db import default_url
from settings import Settings


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}:{function}:{line}</cyan> "
            "<level>{message}</level>"
        ),
    )


def main() -> int:
    settings = Settings()
    _configure_logging(settings.log_level)

    keys = settings.api_keys_set
    if not keys:
        logger.error(
            "SCANNER_API_KEYS env var missing or empty. "
            "Set it to a CSV of allowed Bearer tokens before starting."
        )
        return 1

    logger.info(
        "Starting Scanner V5 backend — "
        f"host={settings.host} port={settings.port} "
        f"db={settings.db_path} keys={len(keys)} "
        f"heartbeat={settings.heartbeat_interval_s}s "
        f"auto_scheduler={'on' if settings.auto_scheduler_enabled else 'off'} "
        f"shutdown_timeout={settings.shutdown_timeout_s}s"
    )

    app = create_app(
        valid_api_keys=keys,
        db_url=default_url(settings.db_path),
        auto_init_db=True,
        enable_heartbeat=True,
        heartbeat_interval_s=settings.heartbeat_interval_s,
        enable_auto_scheduler=settings.auto_scheduler_enabled,
        auto_scheduler_interval_s=settings.auto_scheduler_interval_s,
    )

    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        timeout_graceful_shutdown=int(settings.shutdown_timeout_s),
    )
    server = uvicorn.Server(config)
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
