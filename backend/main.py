#!/usr/bin/env python3
"""Entrypoint del backend Scanner V5.

Corre el stack completo: FastAPI (REST + WebSocket) + workers de
background (heartbeat). Carga config desde variables de entorno —
cuando exista el módulo `modules.config/` encriptado, las keys se
leerán desde ahí.

**Uso local:**

    SCANNER_API_KEYS="sk-dev-1,sk-dev-2" python -m backend.main

    # O con override de puerto:
    SCANNER_API_KEYS="sk-dev" SCANNER_PORT=9000 python -m backend.main

**Variables de entorno reconocidas:**

- `SCANNER_API_KEYS` — CSV de API keys aceptadas (obligatorio).
- `SCANNER_DB_PATH` — ruta al archivo SQLite (default `data/scanner.db`).
- `SCANNER_HOST` — host del server (default `127.0.0.1`).
- `SCANNER_PORT` — puerto (default `8000`).
- `SCANNER_HEARTBEAT_INTERVAL_S` — intervalo heartbeat (default `120`).
- `SCANNER_LOG_LEVEL` — nivel de loguru (default `INFO`).

**Shutdown graceful (spec §4.3):** Uvicorn captura SIGINT/SIGTERM y
dispara el shutdown del lifespan, que cancela workers + cierra engine.
Timeout de 30s configurable via `SCANNER_SHUTDOWN_TIMEOUT_S`.
"""

from __future__ import annotations

import os
import sys

import uvicorn
from loguru import logger

from api import create_app
from modules.db import default_url


def _load_api_keys() -> set[str]:
    raw = os.environ.get("SCANNER_API_KEYS", "")
    keys = {k.strip() for k in raw.split(",") if k.strip()}
    return keys


def _configure_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "<level>{level: <8}</level> "
            "<cyan>{name}:{function}:{line}</cyan> "
            "<level>{message}</level>"
        ),
    )


def main() -> int:
    _configure_logging(os.environ.get("SCANNER_LOG_LEVEL", "INFO"))

    keys = _load_api_keys()
    if not keys:
        logger.error(
            "SCANNER_API_KEYS env var missing or empty. "
            "Set it to a CSV of allowed Bearer tokens before starting."
        )
        return 1

    db_path = os.environ.get("SCANNER_DB_PATH", "data/scanner.db")
    host = os.environ.get("SCANNER_HOST", "127.0.0.1")
    port = int(os.environ.get("SCANNER_PORT", "8000"))
    heartbeat_s = float(os.environ.get("SCANNER_HEARTBEAT_INTERVAL_S", "120"))
    shutdown_s = float(os.environ.get("SCANNER_SHUTDOWN_TIMEOUT_S", "30"))

    logger.info(
        "Starting Scanner V5 backend — "
        f"host={host} port={port} db={db_path} keys={len(keys)} "
        f"heartbeat={heartbeat_s}s shutdown_timeout={shutdown_s}s"
    )

    app = create_app(
        valid_api_keys=keys,
        db_url=default_url(db_path),
        auto_init_db=True,
        enable_heartbeat=True,
        heartbeat_interval_s=heartbeat_s,
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        timeout_graceful_shutdown=int(shutdown_s),
    )
    server = uvicorn.Server(config)
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
