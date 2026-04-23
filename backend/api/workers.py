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
from collections.abc import Callable

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.broadcaster import Broadcaster
from api.events import EVENT_ENGINE_STATUS
from engines.database import emit_engine_heartbeat

DEFAULT_HEARTBEAT_INTERVAL_S: float = 120.0
DEFAULT_AUTO_SCHEDULER_INTERVAL_S: float = 60.0

# Callable sync opcional que corre un healthcheck y devuelve
# `{status, error_code, message, duration_ms}`. Usado por el heartbeat
# del scoring engine (spec §3.4 — mini parity cada 2 min). Si es
# `None`, el heartbeat se reporta siempre green sin verificar nada.
HealthcheckFn = Callable[[], dict]


async def heartbeat_worker(
    session_factory: async_sessionmaker,
    broadcaster: Broadcaster,
    *,
    engine_name: str = "scoring",
    interval_s: float = DEFAULT_HEARTBEAT_INTERVAL_S,
    healthcheck_fn: HealthcheckFn | None = None,
) -> None:
    """Emite heartbeats periódicamente hasta que lo cancelen.

    Loop infinito: corre healthcheck (si se pasó) → persiste en DB +
    broadcast `engine.status`. Si la DB falla, loguea y reintenta en
    el próximo tick. Si el broadcast falla, loguea.

    Args:
        session_factory: async factory de sesiones (DB).
        broadcaster: broadcaster para emitir engine.status.
        engine_name: qué motor reporta (default "scoring").
        interval_s: segundos entre heartbeats (default 120 = 2 min).
        healthcheck_fn: callable sync opcional que corre el mini
            parity del motor (ver `engines/scoring/healthcheck.py`).
            Retorna `{status, error_code, message, duration_ms}`. Si
            lanza, el status del heartbeat pasa a `red` con `ENG-001`.
            Si es `None`, el heartbeat es siempre green sin verificar.
    """
    logger.info(
        f"Heartbeat worker started — engine={engine_name} "
        f"interval={interval_s}s "
        f"healthcheck={'on' if healthcheck_fn else 'off'}",
    )
    try:
        while True:
            status = "green"
            error_code: str | None = None
            message: str | None = None

            if healthcheck_fn is not None:
                try:
                    result = await asyncio.to_thread(healthcheck_fn)
                    status = result.get("status", "green")
                    error_code = result.get("error_code")
                    message = result.get("message")
                    if status != "green":
                        logger.warning(
                            f"Healthcheck {engine_name}: status={status} "
                            f"code={error_code} msg={message}",
                        )
                except Exception as e:
                    status = "red"
                    error_code = "ENG-001"
                    message = f"healthcheck lanzó: {e.__class__.__name__}: {e}"
                    logger.exception(f"Healthcheck {engine_name} crashed")

            try:
                await emit_engine_heartbeat(
                    session_factory,
                    engine=engine_name,
                    status=status,
                    error_code=error_code,
                )
            except Exception:
                logger.exception(
                    f"Heartbeat DB write failed for engine={engine_name}",
                )

            payload: dict = {"engine": engine_name, "status": status}
            if error_code:
                payload["error_code"] = error_code
            if message:
                payload["message"] = message
            try:
                await broadcaster.broadcast(EVENT_ENGINE_STATUS, payload)
            except Exception:
                logger.exception(
                    f"Heartbeat broadcast failed for engine={engine_name}",
                )
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info(f"Heartbeat worker cancelled — engine={engine_name}")
        raise


async def auto_scheduler_worker(
    broadcaster: Broadcaster,
    *,
    interval_s: float = DEFAULT_AUTO_SCHEDULER_INTERVAL_S,
) -> None:
    """Scheduler AUTO stub — emite tick cada N segundos.

    Stub MVP (D.3) sin detección real de cierre de velas 15M. En
    producción (Capa 1 completa), este worker será reemplazado por
    el Data Engine con la lógica del spec §3.1:

        cierre_15M → delay 3s → fetch data → verify integrity →
        trigger scan para cada slot operativo

    Por ahora solo emite un envelope `engine.status` del Data Engine
    con status amarillo y `message="stub"` para que el frontend sepa
    que el scheduler está conectado pero sin datos reales.

    Args:
        broadcaster: broadcaster para emitir engine.status.
        interval_s: segundos entre ticks (default 60s). En producción
            el intervalo real está atado al cierre de vela 15M.
    """
    logger.info(f"Auto-scheduler stub started (interval={interval_s}s)")
    try:
        while True:
            await asyncio.sleep(interval_s)
            try:
                await broadcaster.broadcast(
                    EVENT_ENGINE_STATUS,
                    {
                        "engine": "data",
                        "status": "yellow",
                        "message": "Data Engine stub — scheduler tick",
                    },
                )
            except Exception:
                logger.exception("Auto-scheduler broadcast failed")
    except asyncio.CancelledError:
        logger.info("Auto-scheduler cancelled")
        raise
