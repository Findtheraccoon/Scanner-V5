"""Endpoints REST del Validator Module (`/api/v1/validator`).

**Scope V.6:**

- `POST /api/v1/validator/run` — corre la batería completa (7 tests
  D→A→B→C→E→F→G). El endpoint es sync: bloquea hasta que la corrida
  termina y devuelve el reporte. La batería también emite
  `validator.progress` via WebSocket durante la corrida — clientes
  adicionales pueden seguir el progreso sin disparar.
- `POST /api/v1/validator/connectivity` — corre solo Check G, útil
  para el botón "Test conectividad API" del Dashboard.
- `GET /api/v1/validator/report/latest` — devuelve el último reporte
  (404 si todavía no se corrió ninguno en esta sesión).

**Persistencia:** el último reporte vive en `app.state.last_validator_report`.
Solo se mantiene el último — los históricos no están soportados.

**Auth:** Bearer token.

**Dependencia del wiring:** el `Validator` debe estar seteado en
`app.state.validator` antes de usar estos endpoints. V.7 lo hace en
el lifespan. Sin él, los endpoints retornan 503.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from api.auth import require_auth
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
    report = getattr(request.app.state, "last_validator_report", None)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No validator report available yet in this session.",
        )
    return _report_to_dict(report)
