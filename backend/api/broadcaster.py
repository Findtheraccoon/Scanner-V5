"""Broadcaster in-process para el WebSocket del Cockpit/Memento.

Mantiene el set de clientes WebSocket conectados y expone `broadcast()`
para que los motores del backend empujen eventos. Los 6 eventos del
catálogo oficial están declarados como constantes en `events.py`.

**Concurrencia:** el set de clientes se protege con un `asyncio.Lock`.
Las operaciones de registro/deregistro son atómicas. El broadcast
toma un snapshot del set antes de iterar, así que nuevos
registros/deregistros en paralelo no interrumpen la entrega.

**Tolerancia a desconexión:** si un `send_json` falla para un cliente,
se lo deregistra silenciosamente. El motor que emitió no se entera.

**Un broadcaster por FastAPI app** — vive en `app.state.broadcaster`,
construido en `create_app()`. Los handlers WS lo acceden via
`request.app.state.broadcaster`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from modules.db import now_et


class WSLike(Protocol):
    """Protocolo mínimo del WebSocket para testabilidad."""

    async def send_json(self, data: Any) -> None: ...


class Broadcaster:
    """Gestor de clientes WebSocket + emisor de eventos con envelope."""

    def __init__(self) -> None:
        self._clients: set[WSLike] = set()
        self._lock = asyncio.Lock()

    async def register(self, ws: WSLike) -> None:
        """Agrega un cliente al set de broadcast."""
        async with self._lock:
            self._clients.add(ws)

    async def unregister(self, ws: WSLike) -> None:
        """Quita un cliente del set. Idempotente."""
        async with self._lock:
            self._clients.discard(ws)

    async def client_count(self) -> int:
        """Cantidad de clientes conectados (útil para tests y métricas)."""
        async with self._lock:
            return len(self._clients)

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        """Emite un evento a todos los clientes conectados.

        Envelope:
            {"event": str, "timestamp": ISO8601 ET, "payload": dict}

        Clientes que fallen al recibir se deregistran automáticamente.
        """
        envelope = {
            "event": event,
            "timestamp": now_et().isoformat(),
            "payload": payload,
        }
        async with self._lock:
            clients = list(self._clients)

        failed: list[WSLike] = []
        for ws in clients:
            try:
                await ws.send_json(envelope)
            except Exception:
                failed.append(ws)

        for ws in failed:
            await self.unregister(ws)
