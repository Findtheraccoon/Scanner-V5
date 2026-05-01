"""Health check endpoint — `GET /api/v1/engine/health`.

Devuelve un snapshot **agregado** del estado de los 4 motores del
backend (scoring, data, database, validator). Cada motor tiene su
propio sub-objeto con `status` + `message?` + `error_code?`. Si un
motor nunca emitió heartbeat, su status es `"offline"`.

**Auth:** requiere Bearer token válido.

**Response shape:**

    {
      "status":  overall ("green"|"yellow"|"red"|"offline"),
      "scoring": {"status", "message?", "error_code?", "last_heartbeat_at?"},
      "data":    {"status", "message?", "error_code?", "last_heartbeat_at?"},
      "database":{"status", "message?", "error_code?", "last_heartbeat_at?"},
      "validator": {"status", "message?", "error_code?", "last_run_at?"},
      "engine_version": str,
      "ts": ISO8601
    }

`scoring`, `data`, `database` se leen de la tabla `heartbeats` (último
row por motor). El `validator` se deriva del `overall_status` del
último `ValidatorReport` (corre on-demand, no tiene heartbeat propio).

**Compute del overall:**

- offline si TODOS los motores son offline.
- red si alguno es red.
- yellow si alguno es yellow / paused.
- green si todos los reportados son green.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_session
from engines.scoring import ENGINE_VERSION
from modules.db import Heartbeat, ValidatorReportRecord, now_et

router = APIRouter(tags=["engine"])

_TRACKED_ENGINES = ("scoring", "data", "database")


def _compute_overall(statuses: list[str]) -> str:
    """Agrega los statuses de los 4 motores en uno solo.

    Reglas:
    - "offline" si TODOS son offline.
    - "red" si alguno es red.
    - "yellow" si alguno es yellow o paused.
    - "green" en caso contrario.
    """
    if all(s == "offline" for s in statuses):
        return "offline"
    if any(s == "red" for s in statuses):
        return "red"
    if any(s in ("yellow", "paused") for s in statuses):
        return "yellow"
    return "green"


async def _last_heartbeat(session: AsyncSession, engine: str) -> dict:
    """Devuelve el sub-objeto del motor leyendo el último heartbeat.

    Si nunca hubo heartbeat, retorna `{"status": "offline"}` con los
    demás campos en None.
    """
    stmt = (
        select(Heartbeat)
        .where(Heartbeat.engine == engine)
        .order_by(desc(Heartbeat.ts))
        .limit(1)
    )
    result = await session.execute(stmt)
    last = result.scalar_one_or_none()

    if last is None:
        return {
            "status": "offline",
            "message": None,
            "error_code": None,
            "last_heartbeat_at": None,
        }

    return {
        "status": last.status,
        "message": None,
        "error_code": last.error_code,
        "last_heartbeat_at": last.ts.isoformat(),
    }


async def _validator_status(session: AsyncSession) -> dict:
    """El validator no emite heartbeats — su estado es el
    `overall_status` del último reporte. Mapeo:

    - "pass" → "green"
    - "warning" → "yellow"
    - "fail" → "red"
    - sin reportes → "offline"
    """
    stmt = (
        select(ValidatorReportRecord)
        .order_by(desc(ValidatorReportRecord.finished_at))
        .limit(1)
    )
    result = await session.execute(stmt)
    last = result.scalar_one_or_none()

    if last is None:
        return {
            "status": "offline",
            "message": None,
            "error_code": None,
            "last_run_at": None,
        }

    overall = last.overall_status
    status = (
        "green" if overall == "pass"
        else "yellow" if overall == "warning"
        else "red"
    )
    return {
        "status": status,
        "message": f"último run: {overall}",
        "error_code": None,
        "last_run_at": last.finished_at.isoformat(),
    }


@router.get("/engine/health")
async def engine_health(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Estado consolidado de los 4 motores del backend.

    BUG-008: incluye `registry_load_error` cuando el bootstrap del
    registry usó el fallback in-memory por un load fallido (REG-020,
    REG-002, etc.). Permite a la UI mostrar el error al usuario en
    vez de quedarse mudo con un registry vacío.
    """
    sub_engines: dict[str, dict] = {}
    for name in _TRACKED_ENGINES:
        sub_engines[name] = await _last_heartbeat(session, name)
    sub_engines["validator"] = await _validator_status(session)

    overall = _compute_overall([sub["status"] for sub in sub_engines.values()])

    payload: dict = {
        "status": overall,
        "scoring": sub_engines["scoring"],
        "data": sub_engines["data"],
        "database": sub_engines["database"],
        "validator": sub_engines["validator"],
        "engine_version": ENGINE_VERSION,
        "ts": now_et().isoformat(),
        # BUG-014: si hay un launcher supervisando el subprocess, el
        # botón "reiniciar backend" en Box1 funciona como espera el
        # usuario (mata + relanza). Sin launcher, /system/restart deja
        # el proceso muerto. El frontend usa este flag para decidir
        # si habilitar el botón. Detección: env var `SCANNER_LAUNCHER_PID`
        # que el launcher.py setea antes de importar main.
        "launcher_attached": os.environ.get("SCANNER_LAUNCHER_PID") is not None,
    }
    registry_error = getattr(request.app.state, "registry_load_error", None)
    if registry_error:
        payload["registry_load_error"] = registry_error
    return payload
