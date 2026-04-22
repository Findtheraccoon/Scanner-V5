"""Endpoints REST del Validator Module (`/api/v1/validator`).

**Run + lectura de reportes:**

- `POST /api/v1/validator/run` — corre la batería completa (7 tests
  D→A→B→C→E→F→G). Bloqueante — emite `validator.progress` durante la
  corrida y retorna el reporte.
- `POST /api/v1/validator/connectivity` — corre solo Check G.
- `GET /api/v1/validator/report/latest` — último reporte en memoria
  (compatibilidad — devuelve el cache `app.state.last_validator_report`).
- `GET /api/v1/validator/reports?cursor=&limit=&trigger=&overall_status=`
  — histórico paginado desde DB. Transparent read op + archive.
- `GET /api/v1/validator/reports/latest` — último reporte de la DB
  (vs `/report/latest` que es el cache in-memory).
- `GET /api/v1/validator/reports/{id}` — detalle por id desde DB.

**Persistencia (AR.4):** cada corrida (startup/manual/hot_reload/
connectivity) se guarda en la tabla `validator_reports`. El endpoint
`/run` persiste con `trigger="manual"`, el startup factory con
`trigger="startup"`, `run_slot_revalidation()` con `"hot_reload"` y
`/connectivity` con `"connectivity"`.

**Auth:** Bearer token.

**Dependencia del wiring:** el `Validator` debe estar seteado en
`app.state.validator` antes de usar estos endpoints. V.7 lo hace en
el lifespan. Sin él, los endpoints retornan 503.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_archive_session, get_session
from modules.db import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    ValidatorTrigger,
    read_validator_report_by_id,
    read_validator_reports_history,
    read_validator_reports_latest,
    write_validator_report,
)
from modules.validator import Validator, ValidatorReport
from modules.validator.log_writer import write_report_log

router = APIRouter(prefix="/validator", tags=["validator"])


def _persist_report_log(request: Request, report: ValidatorReport) -> None:
    """Escribe el TXT a `app.state.log_dir` si está configurado.

    Silencioso: un fallo de disco no rompe el endpoint.
    """
    log_dir = getattr(request.app.state, "log_dir", None)
    if log_dir is None:
        return
    try:
        write_report_log(report, Path(log_dir))
    except OSError:
        logger.exception(
            f"could not write validator TXT log to {log_dir}",
        )


async def _persist_report_db(
    request: Request,
    report: ValidatorReport,
    *,
    trigger: ValidatorTrigger,
) -> None:
    """Persiste el reporte a la tabla `validator_reports`. Silencioso."""
    factory = request.app.state.session_factory
    try:
        async with factory() as session:
            await write_validator_report(
                session, report=report, trigger=trigger,
            )
    except Exception:
        logger.exception("could not persist validator report to DB")


def _get_validator(request: Request) -> Validator:
    v = getattr(request.app.state, "validator", None)
    if v is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Validator not initialized. The backend entrypoint must "
                "attach a Validator instance to app.state.validator."
            ),
        )
    return v


def _report_to_dict(report: ValidatorReport) -> dict:
    return {
        "run_id": report.run_id,
        "started_at": report.started_at.isoformat(),
        "finished_at": (
            report.finished_at.isoformat() if report.finished_at else None
        ),
        "overall_status": report.overall_status,
        "tests": [t.model_dump() for t in report.tests],
    }


@router.post("/run")
async def run_full_battery(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Dispara la batería completa. Bloqueante, retorna el reporte."""
    validator = _get_validator(request)
    report = await validator.run_full_battery()
    request.app.state.last_validator_report = report
    _persist_report_log(request, report)
    await _persist_report_db(request, report, trigger="manual")
    return _report_to_dict(report)


@router.post("/connectivity")
async def run_connectivity(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Corre solo el Check G — conectividad externa."""
    validator = _get_validator(request)
    result = await validator.run_single_check("G")
    return result.model_dump()


@router.get("/report/latest")
async def get_latest_report(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Cache in-memory del último reporte. Prefiera `/reports/latest`
    para fuente persistente."""
    report = getattr(request.app.state, "last_validator_report", None)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No validator report available yet in this session.",
        )
    return _report_to_dict(report)


# ──────────────────────────────────────────────────────────────────────
# /reports — historia persistente en DB (AR.4)
# ──────────────────────────────────────────────────────────────────────


@router.get("/reports/latest")
async def get_db_latest_report(
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Último reporte persistido en DB (transparent op + archive)."""
    report = await read_validator_reports_latest(
        session, archive_session=archive_session,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No persisted validator report found.",
        )
    return report


@router.get("/reports")
async def list_reports(
    cursor: int | None = Query(None, ge=1),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    trigger: ValidatorTrigger | None = Query(None),
    overall_status: str | None = Query(
        None, pattern=r"^(pass|fail|partial)$",
    ),
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Histórico paginado cursor-based.

    Filtros opcionales por `trigger` y `overall_status`.
    """
    items, next_cursor = await read_validator_reports_history(
        session,
        archive_session=archive_session,
        trigger=trigger,
        overall_status=overall_status,
        cursor=cursor,
        limit=limit,
    )
    return {"items": items, "next_cursor": next_cursor}


@router.get("/reports/{report_id}")
async def get_report_by_id(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Reporte completo por id. Transparent read op + archive."""
    report = await read_validator_report_by_id(
        session, report_id, archive_session=archive_session,
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
