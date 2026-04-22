"""Endpoints REST del Database Engine (`/api/v1/database`).

**Scope AR.1:**

- `POST /api/v1/database/rotate` — botón "Correr limpieza ahora" del
  Dashboard (spec §5.3). Si hay archive configurado, corre
  `rotate_with_archive` (mueve + borra). Si no, modo legacy `rotate_expired`
  (solo borra).
- `GET /api/v1/database/stats` — filas por tabla en la DB operativa
  y (si aplica) en el archive + retention_seconds. Alimenta los cards
  del Dashboard sección "Base de datos".

**Auth:** Bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from api.auth import require_auth
from engines.database.rotation import (
    compute_stats,
    rotate_expired,
    rotate_with_archive,
)

router = APIRouter(prefix="/database", tags=["database"])


@router.post("/rotate")
async def rotate(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Dispara la rotación manual.

    - Con archive configurado: `rotate_with_archive` (mueve + borra).
      Retorna `{table: {archived, deleted}}`.
    - Sin archive: `rotate_expired` (solo borra, modo legacy).
      Retorna `{table: deleted_count}`.
    """
    session_factory = request.app.state.session_factory
    archive_factory = request.app.state.archive_session_factory

    if archive_factory is not None:
        async with session_factory() as op, archive_factory() as ar:
            result = await rotate_with_archive(op, ar)
        return {"mode": "archive", "result": result}

    async with session_factory() as op:
        result = await rotate_expired(op)
    return {"mode": "delete_only", "result": result}


@router.get("/stats")
async def get_stats(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Snapshot de filas por tabla en operativa + archive + retención."""
    session_factory = request.app.state.session_factory
    archive_factory = request.app.state.archive_session_factory

    async with session_factory() as op:
        if archive_factory is not None:
            async with archive_factory() as ar:
                stats = await compute_stats(op, ar)
        else:
            stats = await compute_stats(op, None)

    return {"archive_configured": archive_factory is not None, "tables": stats}
