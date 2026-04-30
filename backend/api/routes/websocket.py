"""Endpoint WebSocket `/ws?token=sk-XXX`.

Auth via query param `?token=` en el handshake inicial (spec §5.3).
Las keys válidas viven en `app.state.valid_api_keys`. Tokens
inválidos cierran el socket con policy violation (1008).

**Comportamiento del socket:**

- Cliente conecta → se registra en el `Broadcaster` de `app.state`.
- Cliente recibe todos los eventos broadcast del backend.
- Mensajes entrantes del cliente se ignoran silenciosamente (canal
  server-push únicamente).
- En desconexión (normal o por error) → se deregistra.

**Auto-shutdown por idle (modo launcher):**

Si `app.state.ws_idle_shutdown_s` está set (típicamente 60s), llevamos
un contador `ws_count` de conexiones activas. Cuando llega a 0:

1. Schedulamos un timer asyncio de `ws_idle_shutdown_s` segundos.
2. Si llega un cliente nuevo antes → cancelamos el timer.
3. Si pasa el tiempo sin reconexión → SIGINT al proceso.

Esto permite que el launcher termine cuando el usuario cierra todas
las pestañas del browser. En modo dev (sin launcher) el setting es
`None` y el contador no produce shutdown.
"""

from __future__ import annotations

import asyncio
import os
import signal
from typing import TYPE_CHECKING

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from loguru import logger

if TYPE_CHECKING:
    from fastapi import FastAPI

router = APIRouter()


def _on_ws_connect(app: FastAPI) -> None:
    """Incrementa el contador y cancela un timer de idle si está corriendo."""
    state = app.state
    state.ws_count = getattr(state, "ws_count", 0) + 1
    timer = getattr(state, "ws_idle_timer", None)
    if timer is not None:
        timer.cancel()
        state.ws_idle_timer = None
        logger.info(
            f"ws: nuevo cliente · count={state.ws_count} · timer de idle cancelado",
        )


def _on_ws_disconnect(app: FastAPI) -> None:
    """Decrementa el contador. Si llega a 0 y `ws_idle_shutdown_s` está
    configurado, schedula un SIGINT tras esa cantidad de segundos."""
    state = app.state
    state.ws_count = max(0, getattr(state, "ws_count", 0) - 1)
    grace = getattr(state, "ws_idle_shutdown_s", None)
    if state.ws_count == 0 and grace is not None and grace > 0:
        logger.info(
            f"ws: 0 clientes · scheduling shutdown en {grace}s si no hay reconexión",
        )

        async def _sleep_and_kill() -> None:
            try:
                await asyncio.sleep(grace)
            except asyncio.CancelledError:
                return
            # Doble check: si llegó un cliente durante el sleep, abortar.
            if getattr(state, "ws_count", 0) > 0:
                logger.info("ws: cliente reconectó durante el grace · abort shutdown")
                return
            logger.info("ws: idle timeout · enviando SIGINT")
            os.kill(os.getpid(), signal.SIGINT)

        state.ws_idle_timer = asyncio.create_task(
            _sleep_and_kill(), name="ws_idle_shutdown",
        )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """Handshake + loop de recepción del WebSocket.

    El cliente debe conectar con `ws://.../ws?token=sk-XXX`. Si el
    token no está en `app.state.valid_api_keys`, el socket se cierra
    con código 1008 (policy violation).
    """
    valid = getattr(websocket.app.state, "valid_api_keys", None)
    if valid is None or token not in valid:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    broadcaster = websocket.app.state.broadcaster
    await broadcaster.register(websocket)
    _on_ws_connect(websocket.app)
    try:
        while True:
            # Server-push only: ignoramos mensajes entrantes del cliente.
            # `receive_text` bloquea hasta que llegue algo o se desconecte.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unregister(websocket)
        _on_ws_disconnect(websocket.app)
