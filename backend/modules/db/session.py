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

    Args:
        url: URL del engine (ver `default_url()`).
        echo: si `True`, loguea cada query (útil para debug).
    """
    return create_async_engine(url, echo=echo, future=True)


def make_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Crea una factory de `AsyncSession` con `expire_on_commit=False`.

    `expire_on_commit=False` es el default recomendado en modo async
    porque evita refetches automáticos después de commit, lo cual
    requeriría awaits adicionales.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
