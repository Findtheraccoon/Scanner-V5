"""Rotación de datos vencidos según políticas de retención (spec §3.7).

Políticas default:

| Tabla         | Retención operativa | Acción             |
|---------------|--------------------|--------------------|
| `signals`     | 1 año              | Delete (→ archive en fase siguiente) |
| `heartbeat`   | 24h                | Delete (sin archive)                 |
| `system_log`  | 30 días            | Delete (→ archive en fase siguiente) |

**Scope C5.7:** implementamos solo el DELETE desde la DB operativa.
El move-to-archive (`data/archive/scanner_archive.db`) requiere
conexión cross-DB y queda para la fase siguiente de la Capa 5.

**Uso típico desde el Database Engine:**

    async def rotation_worker(session_factory):
        while True:
            async with session_factory() as session:
                deleted = await rotate_expired(session)
                if any(deleted.values()):
                    logger.info(f"Rotated: {deleted}")
            await asyncio.sleep(24 * 3600)  # diario
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from modules.db import Heartbeat, Signal, SystemLog, now_et

# Default del spec §3.7
DEFAULT_RETENTION_POLICIES: Mapping[str, _dt.timedelta] = {
    "signals": _dt.timedelta(days=365),
    "heartbeat": _dt.timedelta(hours=24),
    "system_log": _dt.timedelta(days=30),
}


async def rotate_expired(
    session: AsyncSession,
    policies: Mapping[str, _dt.timedelta] | None = None,
    *,
    now: _dt.datetime | None = None,
) -> dict[str, int]:
    """Borra filas vencidas de cada tabla según la política.

    Args:
        session: sesión async abierta (commit lo hace este helper).
        policies: mapping `tabla → timedelta`. Default: políticas del
            spec. Si una tabla no está en `policies`, no se rota.
        now: timestamp de referencia para calcular cutoffs. Default
            `now_et()`. Útil para tests con `freezegun` o explícitos.

    Returns:
        Dict con la cantidad de filas eliminadas por tabla.
    """
    policies = policies or DEFAULT_RETENTION_POLICIES
    now = now or now_et()
    result: dict[str, int] = {}

    for table, retention in policies.items():
        cutoff = now - retention
        if table == "signals":
            stmt = delete(Signal).where(Signal.compute_timestamp < cutoff)
        elif table == "heartbeat":
            stmt = delete(Heartbeat).where(Heartbeat.ts < cutoff)
        elif table == "system_log":
            stmt = delete(SystemLog).where(SystemLog.ts < cutoff)
        else:
            # Tabla desconocida — se skipea silenciosamente.
            result[table] = 0
            continue
        res = await session.execute(stmt)
        result[table] = res.rowcount or 0

    await session.commit()
    return result
