"""Watchdog automático para rotación agresiva (§9.4).

Worker que corre cada `interval_s` segundos y dispara
`check_and_rotate_aggressive` si la DB operativa supera el umbral
configurado. Complementa al endpoint manual
`POST /api/v1/database/rotate/aggressive` — el botón sigue disponible
para disparo on-demand desde el Dashboard, el watchdog es la red de
seguridad si el trader olvida apagar la DB o deja crecer indefinidamente.

**Conservador por default:** `SCANNER_AGGRESSIVE_ROTATION_ENABLED=false`
— la rotación agresiva es destructiva (reduce retenciones 50% y
mueve filas al archive). Debe activarse explícitamente.

**Intervalo por default:** 1 hora. La rotación agresiva no necesita
chequearse más seguido — el crecimiento del DB es lento (señales,
heartbeats, logs).

**Log:** cada tick loguea el resultado (triggered + size_before +
size_after). Si el rotate falla, loguea la excepción y sigue.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from engines.database.rotation import (
    DEFAULT_SIZE_LIMIT_MB,
    check_and_rotate_aggressive,
)

DEFAULT_WATCHDOG_INTERVAL_S: float = 3600.0  # 1 hora


async def aggressive_rotation_watchdog(
    op_session_factory: async_sessionmaker,
    archive_session_factory: async_sessionmaker,
    db_path: Path,
    *,
    size_limit_mb: int = DEFAULT_SIZE_LIMIT_MB,
    interval_s: float = DEFAULT_WATCHDOG_INTERVAL_S,
) -> None:
    """Loop async que chequea tamaño DB y dispara rotación agresiva.

    Args:
        op_session_factory: factory de la DB operativa.
        archive_session_factory: factory del archive.
        db_path: path del archivo SQLite operativo (para medir tamaño).
        size_limit_mb: umbral de disparo (default 5000 = 5 GB).
        interval_s: segundos entre chequeos (default 3600 = 1h).

    Silencioso ante fallos: si la rotación lanza, loguea y sigue.
    Cancelable vía `asyncio.CancelledError`.
    """
    logger.info(
        f"Aggressive rotation watchdog started — "
        f"db_path={db_path} limit={size_limit_mb}MB interval={interval_s}s",
    )
    try:
        while True:
            try:
                async with (
                    op_session_factory() as op,
                    archive_session_factory() as ar,
                ):
                    result = await check_and_rotate_aggressive(
                        op, ar, db_path, size_limit_mb=size_limit_mb,
                    )
                if result["triggered"]:
                    logger.warning(
                        f"Aggressive rotation triggered — "
                        f"size_before={result['size_mb_before']:.1f}MB "
                        f"size_after={result['size_mb_after']:.1f}MB "
                        f"rotation={result['rotation']}",
                    )
                else:
                    logger.debug(
                        f"Aggressive rotation check — no trigger "
                        f"(size={result['size_mb_before']:.1f}MB, "
                        f"limit={size_limit_mb}MB)",
                    )
            except Exception:
                logger.exception("Aggressive rotation watchdog iteration failed")
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        logger.info("Aggressive rotation watchdog cancelled")
        raise
