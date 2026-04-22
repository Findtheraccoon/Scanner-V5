"""Factory `create_app()` — punto de entrada del backend HTTP.

La función construye una `FastAPI` con:

- Routers REST bajo `/api/v1/...` (ver `api/routes/`).
- Auth Bearer token via dependency (`api.auth.require_auth`).
- Engine + session factory de SQLAlchemy en `app.state`.
- Shutdown graceful: `app.state.db_engine.dispose()` al cerrar.

**Config:** todo via parámetros. Sin dependencias globales, sin
lectura de `os.environ` acá — el entrypoint principal del backend
(por fuera de este módulo) construye los inputs y los pasa.

**Tests:** `create_app(valid_api_keys={...}, db_url=":memory:")`
alcanza para armar la app sin efectos de DB real.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from modules.db import default_url, init_db, make_engine, make_session_factory

_APP_TITLE = "Scanner V5 Backend"
_APP_VERSION = "0.1.0"


def create_app(
    *,
    valid_api_keys: set[str] | None = None,
    db_url: str | None = None,
    auto_init_db: bool = True,
) -> FastAPI:
    """Construye una `FastAPI` lista para correr.

    Args:
        valid_api_keys: set de API keys aceptadas por el middleware
            Bearer. Si se pasa `None`, arranca con set vacío y 100% de
            los requests retornarán 401 — útil para tests de auth pero
            no para producción.
        db_url: URL de conexión (default: `sqlite+aiosqlite:///data/
            scanner.db`). Pasar `":memory:"` para tests.
        auto_init_db: si `True`, corre `init_db()` en el startup para
            `create_all()` o `alembic upgrade` según corresponda.

    Returns:
        `FastAPI` con lifecycle y routers registrados.
    """
    resolved_url = db_url or default_url()
    engine = make_engine(resolved_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if auto_init_db:
            await init_db(engine)
        yield
        await engine.dispose()

    app = FastAPI(title=_APP_TITLE, version=_APP_VERSION, lifespan=lifespan)
    app.state.valid_api_keys = valid_api_keys or set()
    app.state.db_engine = engine
    app.state.session_factory = session_factory

    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    """Registra los routers REST. Sub-fases futuras (ws) agregan."""
    from api.routes.health import router as health_router
    from api.routes.signals import router as signals_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(signals_router, prefix="/api/v1")


# Helpers exportados para testing (evitan replicar el acceso a state).
def get_engine(app: FastAPI) -> AsyncEngine:
    return app.state.db_engine


def get_session_factory(app: FastAPI) -> async_sessionmaker:
    return app.state.session_factory
