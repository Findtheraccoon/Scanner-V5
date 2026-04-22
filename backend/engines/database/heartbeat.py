"""Emisión de heartbeats periódicos por motor.

Un **heartbeat** es el latido que cada motor del backend (data,
scoring, database, validator) emite cada ~2 min para que el Dashboard
sepa si el sistema está vivo. Se persiste en la tabla `heartbeat` con
TTL 24h (limpieza por `rotate_expired`).

**Uso:** `emit_engine_heartbeat` es el helper one-shot. El loop
periódico se arma desde el backend startup con `asyncio.create_task`
+ `asyncio.sleep(interval)`.

    async def heartbeat_worker(session_factory, interval_s=120):
        while True:
            await emit_engine_heartbeat(session_factory, ...)
            await asyncio.sleep(interval_s)
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from modules.db import write_heartbeat


async def emit_engine_heartbeat(
    session_factory: async_sessionmaker,
    *,
    engine: str,
    status: str,
    memory_pct: float | None = None,
    error_code: str | None = None,
) -> int:
    """Persiste un heartbeat para el motor dado.

    Abre una sesión nueva, escribe, cierra. Fail-safe: si la escritura
    falla (DB caída, por ejemplo), propaga la excepción para que el
    caller decida (típicamente ignorar y reintentar al próximo tick).

    Args:
        session_factory: factory async de sesiones (`make_session_factory`).
        engine: nombre del motor — `"data"`, `"scoring"`, `"database"`,
            `"validator"`.
        status: `"green"`, `"yellow"`, `"red"` o `"offline"`.
        memory_pct: porcentaje de uso de memoria relativo al límite del
            motor (0-100). `None` si no se reporta.
        error_code: código si el estado es red/offline.

    Returns:
        El `id` del heartbeat insertado.
    """
    async with session_factory() as session:
        return await write_heartbeat(
            session,
            engine=engine,
            status=status,
            memory_pct=memory_pct,
            error_code=error_code,
        )
