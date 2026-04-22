"""Dependencies compartidas entre routers de la API.

- `get_session(request)`: provee un `AsyncSession` abierto por request,
  leyendo la factory desde `app.state.session_factory`. Se cierra
  automáticamente al final del handler.
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
