"""Backup + Restore de la DB operativa a S3-compatible (spec §3.7).

**Flujo backup:**

    1. `VACUUM INTO <tempfile>` — snapshot atómico sin detener el backend.
    2. `gzip` en memoria.
    3. `boto3.upload_fileobj` al bucket con key `<prefix><stamp>.db.gz`.

**Flujo restore:**

    1. `boto3.download_fileobj` a BytesIO.
    2. `gunzip`.
    3. Escribe a `<db_path>.restored-<stamp>.db` (no reemplaza la DB
       operativa viva — se queda al lado esperando decisión manual
       del trader, spec §3.7 "requiere que el trader confirme").
    4. El caller reinicia el backend manualmente apuntando al archivo
       restaurado si corresponde.

**Multi-provider:** soporta cualquier S3-compatible (AWS S3, Backblaze
B2, Cloudflare R2, custom endpoint). El `endpoint_url` es opcional —
si es `None`, boto3 usa el default de AWS S3.

**Deuda técnica:** las credenciales vienen del body del request REST.
La spec pide credenciales encriptadas en el Config (`modules/config/`),
pero ese módulo aún no está implementado. Hasta entonces, el endpoint
acepta `S3Config` directamente en el POST.

**Boto3 es sync**, todas las funciones públicas envuelven las llamadas
con `asyncio.to_thread` para no bloquear el event loop.
"""

from __future__ import annotations

import asyncio
import gzip
import io
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field


class S3Config(BaseModel):
    """Credenciales + ubicación del bucket S3-compatible."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint_url: str | None = Field(
        default=None,
        description="URL custom (B2, R2, MinIO, etc.). None = AWS S3 estándar.",
    )
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = Field(default="us-east-1")
    key_prefix: str = Field(
        default="scanner-backups/",
        description="Prefix para organizar backups dentro del bucket.",
    )


def _make_s3_client(cfg: S3Config) -> Any:
    """Construye un boto3 S3 client. Sync — llamar desde `to_thread`."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint_url,
        aws_access_key_id=cfg.access_key_id,
        aws_secret_access_key=cfg.secret_access_key,
        region_name=cfg.region,
        config=Config(signature_version="s3v4"),
    )


def _make_backup_key(cfg: S3Config, *, when: datetime | None = None) -> str:
    """`<key_prefix>scanner-YYYYMMDD-HHMMSS.db.gz`."""
    when = when or datetime.utcnow()
    prefix = cfg.key_prefix
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}scanner-{when.strftime('%Y%m%d-%H%M%S')}.db.gz"


# ─────────────────────────────────────────────────────────────────────
# Backup
# ─────────────────────────────────────────────────────────────────────


async def backup_to_s3(
    db_path: Path,
    s3_config: S3Config,
    *,
    when: datetime | None = None,
) -> dict[str, Any]:
    """Sube un snapshot comprimido de la DB operativa al bucket.

    Returns:
        `{"bucket", "key", "size_bytes_raw", "size_bytes_gz", "timestamp"}`
    """
    if not await asyncio.to_thread(db_path.is_file):
        raise FileNotFoundError(f"DB operativa no existe: {db_path}")

    when = when or datetime.utcnow()
    key = _make_backup_key(s3_config, when=when)

    raw_bytes, size_raw = await asyncio.to_thread(_vacuum_snapshot, db_path)
    gz_bytes = await asyncio.to_thread(gzip.compress, raw_bytes)

    await asyncio.to_thread(
        _upload_s3, s3_config, key, gz_bytes,
    )

    logger.info(
        f"backup uploaded — bucket={s3_config.bucket} key={key} "
        f"raw={size_raw}B gz={len(gz_bytes)}B",
    )
    return {
        "bucket": s3_config.bucket,
        "key": key,
        "size_bytes_raw": size_raw,
        "size_bytes_gz": len(gz_bytes),
        "timestamp": when.isoformat() + "Z",
    }


def _vacuum_snapshot(db_path: Path) -> tuple[bytes, int]:
    """`VACUUM INTO <tmp>` → lee los bytes. Sync.

    Crea el tempfile en el mismo dir del db_path para que `VACUUM
    INTO` no cruce filesystems y falle en hosts con `/tmp` separado.
    """
    with tempfile.NamedTemporaryFile(
        prefix=".backup-", suffix=".db", dir=db_path.parent, delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # VACUUM INTO requiere que el target NO exista (SQLite error si
        # existe). Borramos el placeholder del NamedTemporaryFile.
        tmp_path.unlink()

        conn = sqlite3.connect(db_path)
        try:
            conn.execute(f"VACUUM INTO '{tmp_path}'")
        finally:
            conn.close()

        data = tmp_path.read_bytes()
        return data, len(data)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _upload_s3(cfg: S3Config, key: str, data: bytes) -> None:
    client = _make_s3_client(cfg)
    client.upload_fileobj(
        Fileobj=io.BytesIO(data),
        Bucket=cfg.bucket,
        Key=key,
        ExtraArgs={"ContentType": "application/gzip"},
    )


# ─────────────────────────────────────────────────────────────────────
# Restore
# ─────────────────────────────────────────────────────────────────────


async def restore_from_s3(
    db_path: Path,
    s3_config: S3Config,
    key: str,
    *,
    when: datetime | None = None,
) -> dict[str, Any]:
    """Baja un backup y lo deja como `<db_path>.restored-<stamp>.db`.

    **No reemplaza** la DB operativa — para evitar corrupción si el
    backend tiene conexiones abiertas. El caller (UI/trader) reinicia
    el backend apuntando al archivo restaurado si corresponde.

    Returns:
        `{"bucket", "key", "restored_path", "size_bytes"}`
    """
    when = when or datetime.utcnow()

    gz_bytes = await asyncio.to_thread(_download_s3, s3_config, key)
    raw_bytes = await asyncio.to_thread(gzip.decompress, gz_bytes)

    stamp = when.strftime("%Y%m%d-%H%M%S")
    restored_path = db_path.parent / f"{db_path.name}.restored-{stamp}.db"
    restored_path.parent.mkdir(parents=True, exist_ok=True)

    await asyncio.to_thread(restored_path.write_bytes, raw_bytes)

    logger.info(
        f"backup restored — bucket={s3_config.bucket} key={key} "
        f"path={restored_path} size={len(raw_bytes)}B",
    )
    return {
        "bucket": s3_config.bucket,
        "key": key,
        "restored_path": str(restored_path),
        "size_bytes": len(raw_bytes),
    }


def _download_s3(cfg: S3Config, key: str) -> bytes:
    client = _make_s3_client(cfg)
    buf = io.BytesIO()
    client.download_fileobj(Bucket=cfg.bucket, Key=key, Fileobj=buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────
# Listado
# ─────────────────────────────────────────────────────────────────────


async def list_backups(s3_config: S3Config) -> list[dict[str, Any]]:
    """Lista objetos bajo `key_prefix` del bucket.

    Ordenados **desc por key** — el naming `scanner-YYYYMMDD-HHMMSS.db.gz`
    hace que el orden alfabético coincida con el cronológico del
    snapshot capturado (no del upload). Más robusto que ordenar por
    `LastModified` cuando se suben múltiples backups en la misma
    fracción de segundo.
    """
    objects = await asyncio.to_thread(_list_s3, s3_config)
    result: list[dict[str, Any]] = []
    for obj in objects:
        result.append(
            {
                "key": obj["Key"],
                "size_bytes": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            },
        )
    result.sort(key=lambda x: x["key"], reverse=True)
    return result


def _list_s3(cfg: S3Config) -> list[dict[str, Any]]:
    client = _make_s3_client(cfg)
    resp = client.list_objects_v2(Bucket=cfg.bucket, Prefix=cfg.key_prefix)
    return list(resp.get("Contents", []))
