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
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

router = APIRouter()


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
    try:
        while True:
            # Server-push only: ignoramos mensajes entrantes del cliente.
            # `receive_text` bloquea hasta que llegue algo o se desconecte.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unregister(websocket)
