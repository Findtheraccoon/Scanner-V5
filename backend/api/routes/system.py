"""Endpoints REST de control del proceso del backend (`/api/v1/system`).

**Scope:**

- `POST /api/v1/system/shutdown` — mata el proceso del backend
  (graceful — uvicorn corre el lifespan cleanup completo).
- `POST /api/v1/system/restart` — touchea un flag y mata el proceso;
  el launcher detecta el flag y vuelve a arrancar uvicorn.

**Modelo:** el launcher Python (`backend/launcher.py`) es el supervisor.
El backend solo señaliza intención de restart con un archivo flag; el
launcher decide qué hacer al detectar el exit del subprocess.

**Auth:** Bearer token. Sin auth, cualquiera con acceso a localhost
podría matar el backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from loguru import logger

from api.auth import require_auth

router = APIRouter(prefix="/system", tags=["system"])

# Path del flag que el launcher lee al detectar exit del subprocess.
# Si el flag existe, el launcher unlink + re-arranca; si no existe,
# el launcher exit limpio.
DEFAULT_RESTART_FLAG = Path("data/restart_requested.flag")


def _get_restart_flag(request: Request) -> Path:
    return getattr(request.app.state, "restart_flag_path", DEFAULT_RESTART_FLAG)


async def _send_sigint_after(delay_s: float) -> None:
    """Schedula un SIGINT al propio proceso tras `delay_s` segundos.

    El delay permite que la response HTTP del shutdown llegue al
    cliente antes de que uvicorn empiece el cleanup.
    """
    await asyncio.sleep(delay_s)
    logger.info("system: enviando SIGINT al proceso para shutdown limpio")
    os.kill(os.getpid(), signal.SIGINT)


@router.post("/shutdown")
async def shutdown(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Mata el proceso del backend (graceful)."""
    flag = _get_restart_flag(request)
    # Asegurar que NO hay flag de restart (caso: shutdown después de un
    # restart fallido). El launcher debe salir limpio.
    if flag.is_file():
        with contextlib.suppress(OSError):
            flag.unlink()

    logger.info("system: shutdown solicitado via REST")
    # Schedule SIGINT en background para que esta response complete.
    task = asyncio.create_task(_send_sigint_after(0.3), name="system_shutdown")
    tasks = getattr(request.app.state, "system_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state.system_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    return {"shutdown": True, "message": "backend exiting in ~300ms"}


@router.post("/restart")
async def restart(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Pide restart al launcher.

    Mecanismo: touchea `data/restart_requested.flag` y dispara SIGINT.
    El launcher detecta el flag al volver del subprocess, lo borra y
    vuelve a arrancar uvicorn.

    Si no hay launcher (backend corriendo standalone con `python
    main.py`), el flag queda colgado pero el SIGINT mata el proceso
    igual — efecto = shutdown puro. El launcher es opcional.
    """
    flag = _get_restart_flag(request)
    flag.parent.mkdir(parents=True, exist_ok=True)
    try:
        flag.touch()
    except OSError as e:
        logger.warning(f"system: no se pudo crear flag de restart: {e}")

    logger.info("system: restart solicitado via REST")
    task = asyncio.create_task(_send_sigint_after(0.3), name="system_restart")
    tasks = getattr(request.app.state, "system_tasks", None)
    if tasks is None:
        tasks = set()
        request.app.state.system_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)

    return {
        "restart": True,
        "flag_path": str(flag),
        "message": "backend exiting in ~300ms; launcher reiniciará",
    }
