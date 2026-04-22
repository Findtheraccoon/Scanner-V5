"""Health check endpoint — `GET /api/v1/engine/health`.

Devuelve un snapshot del estado del motor de scoring leyendo la última
entrada de la tabla `heartbeat` filtrada por `engine="scoring"`. Si no
hay heartbeats aún, retorna `status="offline"` (sistema recién
iniciado o database engine caído).

**Auth:** requiere Bearer token válido.

**Response shape:**

    {
      "status": "green" | "yellow" | "red" | "offline",
      "engine": "scoring",
      "engine_version": str,
      "memory_pct": float | null,
      "error_code": str | null,
      "ts": ISO8601 tz-aware ET
    }
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_session
from engines.scoring import ENGINE_VERSION
from modules.db import Heartbeat, now_et

router = APIRouter(tags=["engine"])


@router.get("/engine/health")
async def engine_health(
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Estado actual del motor de scoring leído del último heartbeat.

    Si no hay heartbeats (sistema recién arrancado o database engine
    caído), retorna `status="offline"` con timestamp del momento del
    request.
    """
    stmt = (
        select(Heartbeat)
        .where(Heartbeat.engine == "scoring")
        .order_by(desc(Heartbeat.ts))
        .limit(1)
    )
    result = await session.execute(stmt)
    last = result.scalar_one_or_none()

    if last is None:
        return {
            "status": "offline",
            "engine": "scoring",
            "engine_version": ENGINE_VERSION,
            "memory_pct": None,
            "error_code": None,
            "ts": now_et().isoformat(),
        }

    return {
        "status": last.status,
        "engine": "scoring",
        "engine_version": ENGINE_VERSION,
        "memory_pct": last.memory_pct,
        "error_code": last.error_code,
        "ts": last.ts.isoformat(),
    }
