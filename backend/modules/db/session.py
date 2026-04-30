"""Engine + session factory async para SQLAlchemy 2.0.

Tres funciones públicas:

- `default_url(path)` → construye una URL `sqlite+aiosqlite:///<path>`.
- `make_engine(url)` → crea un `AsyncEngine` con configuración estándar.
- `make_session_factory(engine)` → crea `async_sessionmaker` con
  `expire_on_commit=False` (default para operaciones async).

**Uso típico (app o test):**

    engine = make_engine(default_url("data/scanner.db"))
    Session = make_session_factory(engine)
    async with Session() as session:
        session.add(Signal(...))
        await session.commit()
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def default_url(path: str = "data/scanner.db") -> str:
    """Construye la URL de conexión async para SQLite.

    Args:
        path: ruta al archivo `.db` o `":memory:"` para una DB in-memory
            (útil para tests).

    Returns:
        `"sqlite+aiosqlite:///<path>"` (absoluta vía triple slash) o
        `"sqlite+aiosqlite:///:memory:"` para in-memory.
    """
    if path == ":memory:":
        return "sqlite+aiosqlite:///:memory:"
    return f"sqlite+aiosqlite:///{path}"


def make_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Crea un `AsyncEngine` con la configuración estándar del proyecto.

    Si `url` apunta a un archivo SQLite local (no `:memory:`), garantiza
    que el directorio padre exista — SQLite no crea directorios
    automáticamente y `init_db()` reventaría con `unable to open
    database file` al primer arranque sobre un clone limpio.

    Args:
        url: URL del engine (ver `default_url()`).
        echo: si `True`, loguea cada query (útil para debug).
    """
    _ensure_sqlite_dir(url)
    return create_async_engine(url, echo=echo, future=True)


_SQLITE_FILE_PREFIX = "sqlite+aiosqlite:///"


def _ensure_sqlite_dir(url: str) -> None:
    """Crea el dir padre del archivo SQLite si la URL apunta a uno.

    No-op para `:memory:`, otros dialects, o paths sin parent (`.db`
    en el cwd).
    """
    if not url.startswith(_SQLITE_FILE_PREFIX):
        return
    raw_path = url[len(_SQLITE_FILE_PREFIX):]
    if not raw_path or raw_path == ":memory:":
        return
    parent = Path(raw_path).expanduser().parent
    if str(parent) and str(parent) != ".":
        parent.mkdir(parents=True, exist_ok=True)


def make_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Crea una factory de `AsyncSession` con `expire_on_commit=False`.

    `expire_on_commit=False` es el default recomendado en modo async
    porque evita refetches automáticos después de commit, lo cual
    requeriría awaits adicionales.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
