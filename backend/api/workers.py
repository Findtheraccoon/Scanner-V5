"""Background workers del backend — heartbeat loop.

Corren como `asyncio.Task` durante el lifespan de la app. Se arrancan
en `create_app()` cuando los flags correspondientes están activos y se
cancelan limpiamente en el shutdown.

**Heartbeat worker:** emite `engine.status=green` al broadcaster cada
`interval_s` segundos y persiste un `Heartbeat` en la DB. Si la
escritura falla (DB caída, por ejemplo), loguea y continúa — nunca
crashea el backend por esto.

El loop es cancelable: `asyncio.CancelledError` se maneja para cerrar
limpio sin loguear error. Cualquier otra excepción se loguea con
`logger.exception` y el loop continúa.
"""

from __future__ import annotations

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.broadcaster import Broadcaster
from api.events import EVENT_ENGINE_STATUS
from engines.database import emit_engine_heartbeat

DEFAULT_HEARTBEAT_INTERVAL_S: float = 120.0


async def heartbeat_worker(
    session_factory: async_sessionmaker,
    broadcaster: Broadcaster,
    *,
    engine_name: str = "scoring",
    interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
) -> None:
    """Emite heartbeats periódicamente hasta que lo cancelen.

    Loop infinito: persiste en DB + broadcast `engine.status`. Si la DB
    falla, loguea y reintenta en el próximo tick. Si el broadcast falla
    (broadcaster crash, improbable), loguea.

    Args:
        session_factory: async factory de sesiones (DB).
        broadcaster: broadcaster para emitir engine.status.
        engine_name: qué motor reporta (default "scoring").
        interval_s: segundos entre heartbeats (default 120 = 2 min).
    """
    logger.info(
        f"Heartbeat worker started — engine={engine_name} interval={interval_s}s"
    )
    try:
        while True:
            try:
                await emit_engine_heartbeat(
                    session_factory, engine=engine_name, status="green",
                )
            except Exception:
                logger.exception(f"Heartbeat DB write failed for engine={engine_name}")
            try:
                await broadcaster.broadcast(
                    EVENT_ENGINE_STATUS,
                    {"engine": engine_name, "status": "green"},
                )
            except Exception:
                logger.exception(
                    f"Heartbeat broadcast failed for engine={engine_name}"
                )
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info(f"Heartbeat worker cancelled — engine={engine_name}")
        raise
