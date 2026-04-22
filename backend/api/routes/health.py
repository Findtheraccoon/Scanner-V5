"""Health check endpoint — `GET /api/v1/engine/health`.

Devuelve un snapshot del estado del motor de scoring. En sub-fase C5.3
reportamos solo campos estáticos (version); C5.7 (Database Engine
supervisor) lo llena con la última entrada real de la tabla
`heartbeat`.

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

from api.auth import require_auth
from engines.scoring import ENGINE_VERSION
from modules.db import now_et

router = APIRouter(tags=["engine"])


@router.get("/engine/health")
async def engine_health(_token: str = Depends(require_auth)) -> dict:
    """Estado actual del motor de scoring.

    Placeholder C5.3 — retorna status hardcoded `green` + metadata
    básica. En C5.7 se leerá de la tabla `heartbeat`.
    """
    return {
        "status": "green",
        "engine": "scoring",
        "engine_version": ENGINE_VERSION,
        "memory_pct": None,
        "error_code": None,
        "ts": now_et().isoformat(),
    }
