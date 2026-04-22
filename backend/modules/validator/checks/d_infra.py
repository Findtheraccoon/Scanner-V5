"""Check D — Diagnóstico de infraestructura.

Verifica que el sistema puede operar a nivel OS + DB:

1. **DB accesible:** `SELECT 1` sobre la sesión async. Cubre tanto
   "driver cargado" como "archivo accesible/esquema inicializado".
2. **Filesystem escribible:** crea un archivo temporal en el directorio
   de logs (si se pasó) y lo borra. Cubre permisos + espacio mínimo.

**Resultado:**

- Ambos checks OK → `status="pass"`.
- Al menos uno falla → `status="fail"`, `severity="fatal"` (sin DB o
  sin FS escribible el sistema no puede operar).

**Dependencias por motor quedan para V.7** (handshake con workers ya
arrancados) — no es scope de este check.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from modules.validator.models import TestResult


def _probe_fs_sync(log_dir: Path) -> None:
    """Escribe+borra un probe file. Sync para ejecutarse en `to_thread`."""
    log_dir.mkdir(parents=True, exist_ok=True)
    probe = log_dir / ".validator_fs_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


async def run(
    *,
    session_factory: async_sessionmaker,
    log_dir: Path | None = None,
) -> TestResult:
    """Corre el check D. Nunca lanza — todo se traduce a TestResult."""
    start = time.perf_counter()
    checks: dict[str, bool] = {}
    failures: list[str] = []

    # 1. DB accesible
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["db_reachable"] = True
    except Exception as e:
        checks["db_reachable"] = False
        failures.append(f"DB no accesible: {e.__class__.__name__}: {e}")

    # 2. FS escribible (solo si se pasó log_dir — si no, skip ese sub-check).
    # Las operaciones de FS son bloqueantes: `asyncio.to_thread` para no
    # colgar el event loop.
    if log_dir is not None:
        try:
            await asyncio.to_thread(_probe_fs_sync, log_dir)
            checks["fs_writable"] = True
        except OSError as e:
            checks["fs_writable"] = False
            failures.append(f"FS no escribible en {log_dir}: {e}")

    duration_ms = (time.perf_counter() - start) * 1000.0

    if failures:
        return TestResult(
            test_id="D",
            status="fail",
            severity="fatal",
            message="; ".join(failures),
            error_code=None,
            details={"checks": checks},
            duration_ms=duration_ms,
        )
    return TestResult(
        test_id="D",
        status="pass",
        details={"checks": checks},
        duration_ms=duration_ms,
    )
