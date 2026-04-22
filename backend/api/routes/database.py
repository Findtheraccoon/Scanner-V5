"""Endpoints REST del Database Engine (`/api/v1/database`).

**AR.1 — rotación + stats:**

- `POST /api/v1/database/rotate` — botón "Correr limpieza ahora" del
  Dashboard (spec §5.3). Con archive configurado corre
  `rotate_with_archive`; sin archive usa modo legacy `rotate_expired`.
- `POST /api/v1/database/rotate/aggressive` — rotación agresiva §9.4
  (50% de las retenciones normales). Solo dispara si la DB supera
  `SCANNER_DB_SIZE_LIMIT_MB`; si no, retorna `triggered=false`.
- `GET /api/v1/database/stats` — filas por tabla en operativa + (si
  aplica) archive + retention_seconds + size_mb_operative + umbrales.

**AR.2 — backup/restore S3:**

- `POST /api/v1/database/backup` — `VACUUM INTO` + gzip + upload al
  bucket. Multi-provider via `endpoint_url` (S3/B2/R2/custom).
- `POST /api/v1/database/restore` — baja el archivo a
  `<db_path>.restored-<stamp>.db` (NO reemplaza la DB viva).
- `GET /api/v1/database/backups` — lista objetos del bucket bajo el
  `key_prefix`, ordenados desc por `LastModified`.

**Auth:** Bearer token. Credenciales S3 viajan en el body del POST —
deuda técnica documentada en `modules/db/backup.py` hasta que exista
`modules/config/` encriptado.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from api.auth import require_auth
from engines.database.rotation import (
    DEFAULT_SIZE_LIMIT_MB,
    check_and_rotate_aggressive,
    compute_stats,
    rotate_expired,
    rotate_with_archive,
)
from modules.db import S3Config, backup_to_s3, list_backups, restore_from_s3

router = APIRouter(prefix="/database", tags=["database"])


class BackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    s3: S3Config


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    s3: S3Config
    key: str


class ListBackupsRequest(BaseModel):
    """POST en lugar de GET porque lleva credenciales en el body."""

    model_config = ConfigDict(extra="forbid")

    s3: S3Config


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
    """Snapshot de filas por tabla en operativa + archive + retención.

    Incluye también `size_mb_operative` y `size_limit_mb` — útil para
    el Dashboard §5.3 que dibuja una barra hacia el umbral agresivo.
    """
    session_factory = request.app.state.session_factory
    archive_factory = request.app.state.archive_session_factory

    async with session_factory() as op:
        if archive_factory is not None:
            async with archive_factory() as ar:
                stats = await compute_stats(op, ar)
        else:
            stats = await compute_stats(op, None)

    # Tamaño del archivo operativo (si existe).
    size_mb = None
    db_path = _try_derive_db_path(request)
    if db_path is not None:
        try:
            size_mb = db_path.stat().st_size / (1024 * 1024)
        except OSError:
            size_mb = None

    size_limit_mb = getattr(
        request.app.state, "db_size_limit_mb", DEFAULT_SIZE_LIMIT_MB,
    )

    return {
        "archive_configured": archive_factory is not None,
        "tables": stats,
        "size_mb_operative": size_mb,
        "size_limit_mb": size_limit_mb,
    }


@router.post("/rotate/aggressive")
async def rotate_aggressive(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Rotación agresiva (§9.4) — solo dispara si DB > `size_limit_mb`.

    Con archive configurado: mueve al archive con políticas agresivas
    (50% de las normales). Sin archive: 503, porque la versión
    agresiva no tiene sentido sin destino.

    Retorna `{triggered, size_mb_before, size_mb_after, rotation,
    vacuum_recommended}`.
    """
    session_factory = request.app.state.session_factory
    archive_factory = request.app.state.archive_session_factory

    if archive_factory is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Aggressive rotation requires an archive DB configured. "
                "Set SCANNER_ARCHIVE_DB_PATH."
            ),
        )

    db_path = _try_derive_db_path(request)
    if db_path is None:
        raise HTTPException(
            status_code=400,
            detail="Aggressive rotation requires a file-based SQLite DB.",
        )

    size_limit_mb = getattr(
        request.app.state, "db_size_limit_mb", DEFAULT_SIZE_LIMIT_MB,
    )

    async with session_factory() as op, archive_factory() as ar:
        result = await check_and_rotate_aggressive(
            op, ar, db_path, size_limit_mb=size_limit_mb,
        )
    return result


def _try_derive_db_path(request: Request):
    """`:memory:` → None. Archivo físico → `Path`."""
    from pathlib import Path as _Path

    engine = request.app.state.db_engine
    url = str(engine.url)
    if ":memory:" in url:
        return None
    if "///" in url:
        return _Path(url.split("///", 1)[1])
    return None


def _require_db_path(request: Request) -> Path:
    """Deriva el path del archivo SQLite operativo del engine activo."""
    engine = request.app.state.db_engine
    url = str(engine.url)
    # `sqlite+aiosqlite:///<path>` o `.../:memory:`
    if ":memory:" in url:
        raise HTTPException(
            status_code=400,
            detail="backup/restore no soportado para SQLite in-memory",
        )
    # Extraer el path después del triple slash
    if "///" in url:
        return Path(url.split("///", 1)[1])
    raise HTTPException(
        status_code=500,
        detail=f"no puedo derivar db_path de engine url: {url}",
    )


@router.post("/backup")
async def backup(
    req: BackupRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Dispara `VACUUM INTO` + gzip + upload al bucket S3-compatible."""
    db_path = _require_db_path(request)
    try:
        result = await backup_to_s3(db_path, req.s3)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"backup failed: {e}") from e
    return result


@router.post("/restore")
async def restore(
    req: RestoreRequest,
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Baja un backup a `<db_path>.restored-<stamp>.db`.

    **No reemplaza la DB operativa viva** — el trader debe apagar el
    backend y renombrar manualmente si quiere adoptar el restore.
    """
    db_path = _require_db_path(request)
    try:
        result = await restore_from_s3(db_path, req.s3, req.key)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"restore failed: {e}") from e
    return {
        **result,
        "notice": (
            "Archivo guardado al lado de la DB operativa. Para adoptarlo, "
            "apague el backend y renombre `restored_path` → `db_path`."
        ),
    }


@router.post("/backups")
async def list_bucket_backups(
    req: ListBackupsRequest,
    _token: str = Depends(require_auth),
) -> dict:
    """Lista los backups en el bucket bajo `key_prefix`."""
    try:
        objects = await list_backups(req.s3)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"list failed: {e}") from e
    return {
        "bucket": req.s3.bucket,
        "key_prefix": req.s3.key_prefix,
        "objects": objects,
    }
