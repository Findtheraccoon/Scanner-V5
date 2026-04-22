#!/usr/bin/env python3
"""Entrypoint del backend Scanner V5.

Levanta FastAPI (REST + WebSocket) + workers de background:

- Heartbeat (`scoring=green` cada `heartbeat_interval_s` s).
- Scan loop AUTO (si `twelvedata_keys` + `registry_path` apuntan a un
  `slot_registry.json` válido): al cierre de cada vela 15M + delay,
  fetch por slot scannable y `scan_and_emit`.
- Scheduler stub (si `auto_scheduler_enabled` y el scan real no está
  habilitado): tick periódico para frontend.

**Uso local (sin provider real, solo stub):**

    SCANNER_API_KEYS="sk-dev" \\
    SCANNER_AUTO_SCHEDULER_ENABLED=true \\
    SCANNER_AUTO_SCHEDULER_INTERVAL_S=10 \\
    python -m backend.main

**Uso con provider real (scan loop completo):**

    SCANNER_API_KEYS="sk-dev" \\
    SCANNER_TWELVEDATA_KEYS="k1:sk-td-1:8:800,k2:sk-td-2:8:800" \\
    SCANNER_SCAN_TICKERS="QQQ,SPY,AAPL,NVDA" \\
    SCANNER_SCAN_FIXTURE_PATH="fixtures/qqq_canonical_v1.json" \\
    python -m backend.main

**Shutdown graceful (spec §4.3):** Uvicorn captura SIGINT/SIGTERM y
dispara el shutdown del lifespan, que cancela workers + dispose del
engine.
"""

from __future__ import annotations

import sys

import uvicorn
from loguru import logger

from api import create_app
from engines.data import (
    ApiKeyConfig,
    DataEngine,
    KeyPool,
    TwelveDataClient,
)
from engines.data.scan_loop import auto_scan_loop
from engines.registry_runtime import RegistryRuntime
from engines.scoring import ENGINE_VERSION
from modules.db import default_url, make_engine, make_session_factory
from modules.slot_registry import RegistryError, load_registry
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


def _build_scan_loop_factory(settings: Settings):
    """Si la config incluye provider + slot_registry, construye el
    factory del scan loop real. Si no, retorna `None` — el stub queda
    activo en su lugar.

    El registry (spec §3.3) es ahora la fuente de verdad de qué slots
    operan y con qué fixture — reemplaza la env var `scan_tickers` +
    `scan_fixture_path` estáticos.
    """
    td_keys = settings.parse_twelvedata_keys()
    if not td_keys:
        return None

    try:
        registry = load_registry(
            settings.registry_path, engine_version=ENGINE_VERSION,
        )
    except FileNotFoundError:
        logger.error(
            f"Slot registry not found at {settings.registry_path}. "
            "Scan loop NOT enabled.",
        )
        return None
    except RegistryError as e:
        logger.error(
            f"Slot registry invalid ({e.code}): {e.detail}. "
            "Scan loop NOT enabled.",
        )
        return None

    try:
        registry.ensure_at_least_one_operative()
    except RegistryError as e:
        logger.error(
            f"Slot registry has no operative slots ({e.code}). "
            "Scan loop NOT enabled.",
        )
        return None

    pool = KeyPool([ApiKeyConfig(**k) for k in td_keys])
    db_engine = make_engine(default_url(settings.db_path))
    session_factory = make_session_factory(db_engine)
    client = TwelveDataClient(pool)
    data_engine = DataEngine(
        pool=pool, client=client, session_factory=session_factory,
    )
    runtime = RegistryRuntime(registry)

    return {
        "pool": pool,
        "client": client,
        "data_engine": data_engine,
        "session_factory": session_factory,
        "registry": runtime,
        "delay_after_close_s": settings.scan_delay_after_close_s,
    }


def build_scan_loop_factory_for_app(
    *,
    app_broadcaster,
    data_engine: DataEngine,
    session_factory,
    registry: RegistryRuntime,
    delay_after_close_s: float,
):
    """Crea la corutina factory que el lifespan de `create_app` usa."""

    async def factory():
        await auto_scan_loop(
            data_engine=data_engine,
            session_factory=session_factory,
            broadcaster=app_broadcaster,
            registry=registry,
            delay_after_close_s=delay_after_close_s,
        )

    return factory


def main() -> int:
    settings = Settings()
    _configure_logging(settings.log_level)

    keys = settings.api_keys_set
    if not keys:
        logger.error(
            "SCANNER_API_KEYS env var missing or empty. "
            "Set it to a CSV of allowed Bearer tokens before starting.",
        )
        return 1

    # Scan loop real si el config lo permite
    scan_context = _build_scan_loop_factory(settings)
    use_real_scan_loop = scan_context is not None
    use_stub_scheduler = (
        settings.auto_scheduler_enabled and not use_real_scan_loop
    )

    logger.info(
        "Starting Scanner V5 backend — "
        f"host={settings.host} port={settings.port} "
        f"db={settings.db_path} keys={len(keys)} "
        f"heartbeat={settings.heartbeat_interval_s}s "
        f"scan_loop={'real' if use_real_scan_loop else 'stub' if use_stub_scheduler else 'off'} "
        f"shutdown_timeout={settings.shutdown_timeout_s}s",
    )

    extra_workers: list = []
    app = create_app(
        valid_api_keys=keys,
        db_url=default_url(settings.db_path),
        auto_init_db=True,
        enable_heartbeat=True,
        heartbeat_interval_s=settings.heartbeat_interval_s,
        enable_auto_scheduler=use_stub_scheduler,
        auto_scheduler_interval_s=settings.auto_scheduler_interval_s,
        extra_workers=extra_workers,
    )

    if use_real_scan_loop:
        factory = build_scan_loop_factory_for_app(
            app_broadcaster=app.state.broadcaster,
            data_engine=scan_context["data_engine"],
            session_factory=scan_context["session_factory"],
            registry=scan_context["registry"],
            delay_after_close_s=scan_context["delay_after_close_s"],
        )
        extra_workers.append(factory)
        # Expose registry via app.state para que endpoints REST (SR.3)
        # puedan consultarlo.
        app.state.registry_runtime = scan_context["registry"]

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
