"""Tests de integración del endpoint WebSocket (C5.5).

Usa `starlette.testclient.TestClient` (sync wrapper sobre la app async)
para establecer una conexión WebSocket real y verificar el handshake +
recepción de envelopes broadcast.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api import create_app
from api.events import EVENT_SIGNAL_NEW


@pytest.fixture
def client():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
    )
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# Auth via ?token=
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSocketAuth:
    def test_missing_token_rejects(self, client) -> None:
        """Sin `?token=` FastAPI devuelve 403 (validation error en query)."""
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
            pass

    def test_invalid_token_closes_with_policy_violation(self, client) -> None:
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect("/ws?token=sk-wrong"),
        ):
            pass
        assert exc_info.value.code == 1008

    def test_valid_token_accepts(self, client) -> None:
        with client.websocket_connect("/ws?token=sk-test") as ws:
            # Conexión establecida — no recibe nada por default
            assert ws is not None


# ═══════════════════════════════════════════════════════════════════════════
# Broadcast integration
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSocketBroadcast:
    def test_connected_client_receives_broadcast(self, client) -> None:
        """Cliente conectado debe recibir un envelope cuando el broadcaster
        emite un evento. Se invoca el broadcaster directamente desde la app."""
        import asyncio

        app = client.app
        broadcaster = app.state.broadcaster

        with client.websocket_connect("/ws?token=sk-test") as ws:
            # Disparar broadcast desde el event loop del TestClient
            asyncio.run(broadcaster.broadcast(
                EVENT_SIGNAL_NEW, {"ticker": "QQQ", "score": 8.0},
            ))
            envelope = ws.receive_json()
            assert envelope["event"] == EVENT_SIGNAL_NEW
            assert envelope["payload"] == {"ticker": "QQQ", "score": 8.0}
            assert "timestamp" in envelope

    def test_multiple_clients_all_receive(self, client) -> None:
        """Todos los clients conectados reciben el mismo broadcast."""
        import asyncio

        app = client.app
        broadcaster = app.state.broadcaster

        with (
            client.websocket_connect("/ws?token=sk-test") as ws1,
            client.websocket_connect("/ws?token=sk-test") as ws2,
        ):
            asyncio.run(broadcaster.broadcast(EVENT_SIGNAL_NEW, {"n": 1}))
            e1 = ws1.receive_json()
            e2 = ws2.receive_json()
            assert e1["payload"] == {"n": 1}
            assert e2["payload"] == {"n": 1}


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle: unregister al cerrar
# ═══════════════════════════════════════════════════════════════════════════


class TestWebSocketLifecycle:
    def test_client_count_increments_on_connect(self, client) -> None:
        import asyncio

        app = client.app
        broadcaster = app.state.broadcaster
        assert asyncio.run(broadcaster.client_count()) == 0

        with client.websocket_connect("/ws?token=sk-test"):
            # Count dentro del context manager
            assert asyncio.run(broadcaster.client_count()) == 1
