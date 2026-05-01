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

import asyncio
import sys
from pathlib import Path

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
from engines.scoring.healthcheck import run_healthcheck as run_scoring_healthcheck
from modules.db import (
    default_url,
    make_engine,
    make_session_factory,
    write_validator_report,
)
from modules.slot_registry import RegistryError, load_registry
from modules.validator import Validator
from modules.validator.log_writer import write_report_log
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

    key_configs = [ApiKeyConfig(**k) for k in td_keys]
    pool = KeyPool(key_configs)
    db_engine = make_engine(default_url(settings.db_path))
    session_factory = make_session_factory(db_engine)
    client = TwelveDataClient(pool)
    data_engine = DataEngine(
        pool=pool, client=client, session_factory=session_factory,
    )
    runtime = RegistryRuntime(registry, registry_path=settings.registry_path)

    return {
        "pool": pool,
        "client": client,
        "data_engine": data_engine,
        "session_factory": session_factory,
        "registry": runtime,
        "delay_after_close_s": settings.scan_delay_after_close_s,
        "key_configs": key_configs,
    }


def build_scan_loop_factory_for_app(
    *,
    app_broadcaster,
    data_engine: DataEngine,
    session_factory,
    registry: RegistryRuntime,
    delay_after_close_s: float,
    running: asyncio.Event,
):
    """Crea la corutina factory que el lifespan de `create_app` usa.

    `running` se construye fuera y se expone vía `app.state` para que
    `POST /api/v1/scan/auto/{pause,resume}` pueda alternar el flag.
    """

    async def factory():
        await auto_scan_loop(
            data_engine=data_engine,
            session_factory=session_factory,
            broadcaster=app_broadcaster,
            registry=registry,
            delay_after_close_s=delay_after_close_s,
            running=running,
        )

    return factory


def _build_validator(
    settings: Settings,
    app,
    scan_context: dict | None,
) -> Validator:
    """Construye el Validator con los inputs disponibles del entrypoint.

    - `scan_context` presente → wire registry, registry_path, td_probe.
    - `scan_context` None → validator stand-alone (D + F funcionan con
      paths default; A/B/C/E/G harán `skip` por falta de inputs).
    """
    from engines.data.probes import build_td_probe

    registry_runtime = scan_context["registry"] if scan_context else None
    registry_path = settings.registry_path if scan_context else None
    td_probe = None
    if scan_context is not None:
        td_probe = build_td_probe(
            scan_context["key_configs"], scan_context["client"],
        )

    return Validator(
        session_factory=app.state.session_factory,
        broadcaster=app.state.broadcaster,
        log_dir=Path(settings.log_dir),
        registry=registry_runtime,
        registry_path=registry_path,
        td_probe=td_probe,
        parity_enabled=settings.validator_parity_enabled,
        parity_limit=settings.validator_parity_limit,
    )


def _try_load_last_config(app, settings: Settings) -> None:
    """Si `data/last_config_path.json` apunta a un `.config` existente,
    cárgalo en `app.state.user_config` para que el scanner arranque
    con la última configuración del usuario sin tener que cargarla
    a mano cada vez.

    Silencioso ante errores: si algo falla, el scanner arranca con
    runtime vacío (`UserConfig() default`) y el usuario la carga
    manualmente desde el frontend.
    """
    import json
    from pathlib import Path

    from modules.config import load_config

    last_path_file = Path(settings.last_config_path_file)
    if not last_path_file.is_file():
        return
    try:
        meta = json.loads(last_path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(f"could not read {last_path_file} — skipping LAST")
        return
    cfg_path = Path(meta.get("path", ""))
    if not cfg_path.is_file():
        logger.info(
            f"LAST config path {cfg_path} does not exist — starting from scratch",
        )
        return
    try:
        cfg = load_config(cfg_path)
    except Exception:
        logger.exception(f"could not load LAST config {cfg_path} — skipping")
        return

    app.state.user_config = cfg
    app.state.user_config_path = cfg_path
    logger.info(f"LAST config loaded: {cfg_path} ({cfg.name})")


def _build_aggressive_watchdog_factory(app, settings: Settings):
    """Factory del watchdog automático de rotación agresiva (§9.4).

    Solo se agrega cuando `SCANNER_AGGRESSIVE_ROTATION_ENABLED=true` y
    hay archive configurado. El default es off (opt-in) porque la
    rotación agresiva es destructiva.
    """
    from pathlib import Path as _Path

    from engines.database import aggressive_rotation_watchdog

    db_path = _Path(settings.db_path)

    async def factory():
        await aggressive_rotation_watchdog(
            app.state.session_factory,
            app.state.archive_session_factory,
            db_path,
            size_limit_mb=settings.db_size_limit_mb,
            interval_s=settings.aggressive_rotation_interval_s,
        )

    return factory


def _build_validator_startup_factory(app):
    """Factory para el lifespan: corre la batería al arrancar, guarda
    el reporte en `app.state.last_validator_report` y escribe el TXT
    a `/LOG/` si hay `app.state.log_dir`.

    Loggea el `overall_status`. No crashea si algún test falla —
    continue-on-fatal según decisión de diseño V.7.
    """

    async def factory():
        validator: Validator = app.state.validator
        logger.info("Validator startup run — launching full battery")
        report = await validator.run_full_battery()
        app.state.last_validator_report = report
        log_dir = getattr(app.state, "log_dir", None)
        if log_dir is not None:
            try:
                target = write_report_log(report, Path(log_dir))
                logger.info(f"Validator TXT log written to {target}")
            except OSError:
                logger.exception(
                    f"could not write validator TXT log to {log_dir}",
                )
        # Persistir a la tabla validator_reports (AR.4). Silencioso.
        try:
            session_factory = app.state.session_factory
            async with session_factory() as session:
                await write_validator_report(
                    session, report=report, trigger="startup",
                )
        except Exception:
            logger.exception("could not persist startup validator report")
        logger.info(
            f"Validator startup run done — overall={report.overall_status} "
            f"run_id={report.run_id}",
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

    archive_db_url = (
        default_url(settings.archive_db_path) if settings.archive_db_path else None
    )

    extra_workers: list = []
    app = create_app(
        valid_api_keys=keys,
        db_url=default_url(settings.db_path),
        archive_db_url=archive_db_url,
        auto_init_db=True,
        enable_heartbeat=True,
        heartbeat_interval_s=settings.heartbeat_interval_s,
        heartbeat_healthcheck_fn=run_scoring_healthcheck,
        enable_auto_scheduler=use_stub_scheduler,
        auto_scheduler_interval_s=settings.auto_scheduler_interval_s,
        extra_workers=extra_workers,
        rotate_on_shutdown=settings.rotate_on_shutdown,
        db_size_limit_mb=settings.db_size_limit_mb,
        last_config_path_file=settings.last_config_path_file,
        fixtures_dir=settings.fixtures_dir,
        static_dir=settings.static_dir,
        frontend_bearer=settings.frontend_bearer_token,
        ws_idle_shutdown_s=settings.ws_idle_shutdown_s,
        restart_flag_path=settings.restart_flag_path,
    )

    if (
        settings.aggressive_rotation_enabled
        and archive_db_url is not None
    ):
        extra_workers.append(
            _build_aggressive_watchdog_factory(app, settings),
        )

    if use_real_scan_loop:
        # `running` por default empieza set → loop corre sin pausa. El
        # endpoint /scan/auto/{pause,resume} lo alterna en tiempo real.
        running = asyncio.Event()
        running.set()
        factory = build_scan_loop_factory_for_app(
            app_broadcaster=app.state.broadcaster,
            data_engine=scan_context["data_engine"],
            session_factory=scan_context["session_factory"],
            registry=scan_context["registry"],
            delay_after_close_s=scan_context["delay_after_close_s"],
            running=running,
        )
        extra_workers.append(factory)
        # Expose registry + data_engine + key_pool + td_client + running.
        app.state.registry_runtime = scan_context["registry"]
        app.state.data_engine = scan_context["data_engine"]
        app.state.key_pool = scan_context["pool"]
        # td_client se expone para que `PUT /config/twelvedata_keys`
        # pueda reconstruir el probe del Validator al hot-reload de
        # keys (BUG-001 capa 2).
        app.state.td_client = scan_context["client"]
        app.state.auto_scan_running = running

    # Carga del LAST .config si el archivo existe y el path apunta a un
    # `.config` válido en disco. Silencioso ante fallos — el scanner
    # arranca de cero si algo falla.
    _try_load_last_config(app, settings)

    # V.7 — Validator wiring. Se construye siempre (standalone si no
    # hay scan_context) y se engancha al app.state para que los
    # endpoints REST funcionen. Si `validator_run_at_startup`, se
    # agrega un worker que corre la batería completa post-startup.
    app.state.validator = _build_validator(settings, app, scan_context)
    app.state.log_dir = settings.log_dir
    if settings.validator_run_at_startup:
        extra_workers.append(_build_validator_startup_factory(app))

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
