"""Factory `create_app()` — punto de entrada del backend HTTP.

La función construye una `FastAPI` con:

- Routers REST bajo `/api/v1/...` (ver `api/routes/`).
- Auth Bearer token via dependency (`api.auth.require_auth`).
- Engine + session factory de SQLAlchemy en `app.state`.
- Shutdown graceful: `app.state.db_engine.dispose()` al cerrar.
- Background workers opcionales (heartbeat) arrancados en el lifespan
  y cancelados limpiamente al shutdown.

**Config:** todo via parámetros. Sin dependencias globales, sin
lectura de `os.environ` acá — el entrypoint principal del backend
(`backend/main.py`) construye los inputs y los pasa.

**Tests:** `create_app(valid_api_keys={...}, db_url=":memory:")`
alcanza para armar la app sin efectos de DB real. Los workers son
opt-in (`enable_heartbeat=False` por default para tests unitarios).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from api.broadcaster import Broadcaster
from api.workers import (
    DEFAULT_AUTO_SCHEDULER_INTERVAL_S,
    DEFAULT_HEARTBEAT_INTERVAL_S,
    auto_scheduler_worker,
    heartbeat_worker,
)
from modules.db import default_url, init_db, make_engine, make_session_factory

_APP_TITLE = "Scanner V5 Backend"
_APP_VERSION = "0.1.0"


def create_app(
    *,
    valid_api_keys: set[str] | None = None,
    db_url: str | None = None,
    archive_db_url: str | None = None,
    auto_init_db: bool = True,
    enable_heartbeat: bool = False,
    heartbeat_interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
    enable_auto_scheduler: bool = False,
    auto_scheduler_interval_s: float = DEFAULT_AUTO_SCHEDULER_INTERVAL_S,
    extra_workers: list | None = None,
    rotate_on_shutdown: bool = False,
) -> FastAPI:
    """Construye una `FastAPI` lista para correr.

    Args:
        valid_api_keys: set de API keys aceptadas por el middleware
            Bearer. Si se pasa `None`, arranca con set vacío y 100% de
            los requests retornarán 401.
        db_url: URL de conexión operativa (default: `sqlite+aiosqlite:///data/
            scanner.db`). Pasar `":memory:"` para tests.
        archive_db_url: URL del archive (spec §3.7). Si es `None`, no
            se construye archive — el endpoint `/database/rotate` usa
            modo legacy (solo borra) y `/database/stats` omite
            `rows_archive`. El entrypoint productivo setea
            `"data/archive/scanner_archive.db"`.
        auto_init_db: si `True`, corre `init_db()` en el startup para
            `create_all()` o `alembic upgrade` según corresponda.
            Aplica tanto a la DB operativa como al archive (si está).
        enable_heartbeat: si `True`, arranca el `heartbeat_worker` en
            background. Default `False` — los tests unitarios no lo
            necesitan. El entrypoint productivo (`backend/main.py`) lo
            activa.
        heartbeat_interval_s: intervalo entre heartbeats (default 120s).
        enable_auto_scheduler: si `True`, arranca el `auto_scheduler_worker`
            (stub actual) — reemplazado por el Data Engine real cuando
            esté disponible. Default `False`.
        auto_scheduler_interval_s: intervalo del scheduler stub
            (default 60s).
        extra_workers: lista de factories `() -> Coroutine` que devuelven
            la corutina a lanzar como task de background. Permite al
            entrypoint registrar el `auto_scan_loop` real sin acoplar el
            app factory a Data Engine. Cada factory se invoca una vez al
            arranque del lifespan.
        rotate_on_shutdown: si `True` y `archive_db_url` está presente,
            dispara `rotate_with_archive` en el shutdown del lifespan
            (spec §3.7 — opción configurable). Logea el resultado y no
            crashea si falla.

    Returns:
        `FastAPI` con lifecycle, routers y workers registrados.
    """
    resolved_url = db_url or default_url()
    engine = make_engine(resolved_url)
    session_factory = make_session_factory(engine)

    archive_engine = None
    archive_session_factory = None
    if archive_db_url is not None:
        archive_engine = make_engine(archive_db_url)
        archive_session_factory = make_session_factory(archive_engine)

    broadcaster = Broadcaster()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if auto_init_db:
            await init_db(engine)
            if archive_engine is not None:
                await init_db(archive_engine)
        workers: list[asyncio.Task] = []
        if enable_heartbeat:
            workers.append(
                asyncio.create_task(
                    heartbeat_worker(
                        session_factory,
                        broadcaster,
                        interval_s=heartbeat_interval_s,
                    ),
                    name="heartbeat_worker",
                ),
            )
        if enable_auto_scheduler:
            workers.append(
                asyncio.create_task(
                    auto_scheduler_worker(
                        broadcaster,
                        interval_s=auto_scheduler_interval_s,
                    ),
                    name="auto_scheduler_worker",
                ),
            )
        if extra_workers:
            for idx, factory in enumerate(extra_workers):
                workers.append(
                    asyncio.create_task(
                        factory(),
                        name=f"extra_worker_{idx}",
                    ),
                )
        app.state.workers = workers
        try:
            yield
        finally:
            # Rotación al shutdown (spec §3.7 opcional configurable).
            if rotate_on_shutdown and archive_session_factory is not None:
                await _run_shutdown_rotation(
                    session_factory, archive_session_factory,
                )
            for w in workers:
                w.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            await engine.dispose()
            if archive_engine is not None:
                await archive_engine.dispose()

    app = FastAPI(title=_APP_TITLE, version=_APP_VERSION, lifespan=lifespan)
    app.state.valid_api_keys = valid_api_keys or set()
    app.state.db_engine = engine
    app.state.session_factory = session_factory
    app.state.archive_engine = archive_engine
    app.state.archive_session_factory = archive_session_factory
    app.state.broadcaster = broadcaster

    _register_routes(app)
    return app


async def _run_shutdown_rotation(
    op_session_factory: async_sessionmaker,
    archive_session_factory: async_sessionmaker,
) -> None:
    """Rotación en shutdown. Silencioso ante fallos — el shutdown no
    debe bloquearse por un error de rotación."""
    from loguru import logger

    from engines.database.rotation import rotate_with_archive

    try:
        async with op_session_factory() as op, archive_session_factory() as ar:
            result = await rotate_with_archive(op, ar)
            logger.info(f"shutdown rotation: {result}")
    except Exception:
        logger.exception("shutdown rotation failed")


def _register_routes(app: FastAPI) -> None:
    """Registra los routers REST + WebSocket."""
    from api.routes.database import router as database_router
    from api.routes.health import router as health_router
    from api.routes.scan import router as scan_router
    from api.routes.signals import router as signals_router
    from api.routes.slots import router as slots_router
    from api.routes.validator import router as validator_router
    from api.routes.websocket import router as websocket_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(scan_router, prefix="/api/v1")
    app.include_router(slots_router, prefix="/api/v1")
    app.include_router(validator_router, prefix="/api/v1")
    app.include_router(database_router, prefix="/api/v1")
    app.include_router(websocket_router)  # `/ws` sin prefijo /api/v1


# Helpers exportados para testing (evitan replicar el acceso a state).
def get_engine(app: FastAPI) -> AsyncEngine:
    return app.state.db_engine


def get_session_factory(app: FastAPI) -> async_sessionmaker:
    return app.state.session_factory
