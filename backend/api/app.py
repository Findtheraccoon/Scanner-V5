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
from collections.abc import AsyncIterator, Callable
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
    heartbeat_healthcheck_fn: Callable[[], dict] | None = None,
    enable_auto_scheduler: bool = False,
    auto_scheduler_interval_s: float = DEFAULT_AUTO_SCHEDULER_INTERVAL_S,
    extra_workers: list | None = None,
    rotate_on_shutdown: bool = False,
    db_size_limit_mb: int = 5000,
    last_config_path_file: str = "data/last_config_path.json",
    fixtures_dir: str = "fixtures",
    static_dir: str | None = None,
    frontend_bearer: str | None = None,
    restart_flag_path: str = "data/restart_requested.flag",
    ws_idle_shutdown_s: float | None = None,
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
        db_size_limit_mb: umbral para rotación agresiva (§9.4). Se
            expone vía `app.state.db_size_limit_mb` para que el
            endpoint `/database/rotate/aggressive` lo consulte.

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
            # Heartbeat del scoring engine (con healthcheck mini-parity).
            workers.append(
                asyncio.create_task(
                    heartbeat_worker(
                        session_factory,
                        broadcaster,
                        engine_name="scoring",
                        interval_s=heartbeat_interval_s,
                        healthcheck_fn=heartbeat_healthcheck_fn,
                    ),
                    name="heartbeat_worker_scoring",
                ),
            )
            # Heartbeats simples para data + database — sin healthcheck
            # propio. Reportan green mientras el lifespan corre. Si los
            # motores fallan, el lifespan se cae y los heartbeats dejan
            # de emitirse → el endpoint /engine/health los reporta
            # offline tras el TTL natural (24h con rotate_expired). Es
            # el mecanismo más simple sin agregar hooks específicos.
            for sub_engine in ("data", "database"):
                workers.append(
                    asyncio.create_task(
                        heartbeat_worker(
                            session_factory,
                            broadcaster,
                            engine_name=sub_engine,
                            interval_s=heartbeat_interval_s,
                            healthcheck_fn=None,
                        ),
                        name=f"heartbeat_worker_{sub_engine}",
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
    app.state.db_size_limit_mb = db_size_limit_mb
    # Config runtime (Configuración Paso 1). El usuario carga un .config
    # explícitamente vía POST /config/load — sin .config cargado el
    # scanner arranca de cero (UserConfig vacío en RAM).
    from pathlib import Path as _Path

    app.state.user_config = None
    app.state.user_config_path = None
    app.state.last_config_path_file = _Path(last_config_path_file)
    app.state.key_pool = None
    app.state.fixtures_dir = _Path(fixtures_dir)
    app.state.restart_flag_path = _Path(restart_flag_path)
    # WS idle shutdown — si `ws_idle_shutdown_s` está set, cuando el
    # contador de conexiones WS llega a 0, dispara un timer y mata el
    # backend tras esa cantidad de segundos sin reconexión.
    app.state.ws_count = 0
    app.state.ws_idle_shutdown_s = ws_idle_shutdown_s
    app.state.ws_idle_timer: object | None = None

    _register_routes(app)
    _mount_frontend(app, static_dir, frontend_bearer)
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
    from api.routes.config import router as config_router
    from api.routes.database import router as database_router
    from api.routes.fixtures import router as fixtures_router
    from api.routes.health import router as health_router
    from api.routes.scan import router as scan_router
    from api.routes.signals import router as signals_router
    from api.routes.slots import router as slots_router
    from api.routes.system import router as system_router
    from api.routes.validator import router as validator_router
    from api.routes.websocket import router as websocket_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")
    app.include_router(scan_router, prefix="/api/v1")
    app.include_router(slots_router, prefix="/api/v1")
    app.include_router(validator_router, prefix="/api/v1")
    app.include_router(database_router, prefix="/api/v1")
    app.include_router(config_router, prefix="/api/v1")
    app.include_router(fixtures_router, prefix="/api/v1")
    app.include_router(system_router, prefix="/api/v1")
    app.include_router(websocket_router)  # `/ws` sin prefijo /api/v1


def _mount_frontend(app: FastAPI, static_dir: str | None, bearer: str | None) -> None:
    """Monta `frontend/dist/` (si existe) en `/` con SPA fallback.

    El index.html se sirve desde un handler custom que inyecta el
    bearer como `<meta name="scanner-bearer" content="...">` cuando el
    launcher provee uno. El frontend lo lee al primer load y lo guarda
    en localStorage.

    Si `static_dir` es None o no existe, el mount queda fuera y el
    backend funciona solo como API (modo dev clásico con Vite proxy).
    """
    from pathlib import Path as _Path

    from fastapi import HTTPException
    from fastapi.responses import FileResponse, HTMLResponse, Response
    from fastapi.staticfiles import StaticFiles

    if static_dir is None:
        return
    base = _Path(static_dir)
    if not base.is_dir():
        return
    index_path = base / "index.html"
    if not index_path.is_file():
        return

    # Cache del index.html con el meta inyectado (sólo se calcula una
    # vez al arrancar — el bearer no cambia en runtime).
    raw_index = index_path.read_text(encoding="utf-8")
    if bearer:
        meta = (
            f'<meta name="scanner-bearer" content="{bearer}">\n'
        )
        # Inyectar en el <head> — buscamos el primer <head> y lo
        # ampliamos. Si no hay, prepend al body.
        if "<head>" in raw_index:
            raw_index = raw_index.replace("<head>", f"<head>\n    {meta}", 1)
    cached_index = raw_index

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def serve_index() -> HTMLResponse:
        return HTMLResponse(content=cached_index)

    # Static mount para todos los assets (CSS, JS, etc).
    app.mount("/assets", StaticFiles(directory=str(base / "assets")), name="assets")

    # SPA fallback: cualquier path que no matchee API/WS/static cae
    # en el index.html para que React Router maneje el routing.
    #
    # SEC-001: el handler valida containment del path antes de servir
    # un archivo real. Sin esa validación, `/..%2Fdata%2Fbearer.txt`
    # leería `data/bearer.txt` (relativo al cwd del backend) y filtraría
    # el token al caller anónimo. Defensa en 2 capas:
    #   1. rechazo explícito de `..` y rutas absolutas en path segments.
    #   2. resolve()+relative_to(base) — si el resolved escapa del
    #      static_dir, fallback al SPA index.
    base_resolved = base.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    async def spa_fallback(path: str) -> Response:
        # Excluir paths de API/WS — esos ya tienen sus rutas y devuelven
        # 404 si no matchean. La regex no aplica acá; FastAPI matchea
        # primero las rutas registradas con prefijo.
        if path.startswith("api/") or path.startswith("ws"):
            raise HTTPException(status_code=404)
        # SEC-001: rechazar traversal antes de tocar el filesystem.
        if path.startswith("/") or ".." in path.split("/"):
            return HTMLResponse(content=cached_index)
        try:
            candidate = (base / path).resolve()
            candidate.relative_to(base_resolved)
        except (ValueError, OSError):
            return HTMLResponse(content=cached_index)
        if candidate.is_file():
            return FileResponse(str(candidate))
        # Cualquier otro path → React Router lo maneja.
        return HTMLResponse(content=cached_index)


# Helpers exportados para testing (evitan replicar el acceso a state).
def get_engine(app: FastAPI) -> AsyncEngine:
    return app.state.db_engine


def get_session_factory(app: FastAPI) -> async_sessionmaker:
    return app.state.session_factory
