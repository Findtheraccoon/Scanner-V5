"""Dependencies compartidas entre routers de la API.

- `get_session(request)`: provee un `AsyncSession` abierto por request,
  leyendo la factory desde `app.state.session_factory`. Se cierra
  automáticamente al final del handler.
- `get_archive_session(request)`: idem pero sobre el archive. Yield
  `None` si el archive no está configurado (AR.3 — transparent reads
  son opt-in).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency que provee una `AsyncSession` por request."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


async def get_archive_session(
    request: Request,
) -> AsyncIterator[AsyncSession | None]:
    """Provee una `AsyncSession` sobre el archive, o `None`.

    Si el app se construyó sin `archive_db_url`, `app.state.archive_session_factory`
    es `None` y la dependency yield-ea `None` directamente — el endpoint
    puede pasar `None` a los helpers y se comportan como sin archive.
    """
    factory = getattr(request.app.state, "archive_session_factory", None)
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session
