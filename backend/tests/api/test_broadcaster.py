"""Tests del Broadcaster in-process (C5.5).

Tests unitarios sin FastAPI — usan un mock `WSLike` para verificar el
comportamiento del broadcaster directamente.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest

from api.broadcaster import Broadcaster
from api.events import (
    ALL_EVENTS,
    EVENT_ENGINE_STATUS,
    EVENT_SIGNAL_NEW,
    EVENT_SYSTEM_LOG,
)


class MockWS:
    """WebSocket simulado para tests — acumula los envelopes recibidos."""

    def __init__(self, *, fail_on_send: bool = False) -> None:
        self.received: list[dict] = []
        self.fail_on_send = fail_on_send

    async def send_json(self, data: Any) -> None:
        if self.fail_on_send:
            raise RuntimeError("simulated disconnect")
        self.received.append(data)


# ═══════════════════════════════════════════════════════════════════════════
# Registration / unregistration
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistration:
    @pytest.mark.asyncio
    async def test_initial_count_zero(self) -> None:
        b = Broadcaster()
        assert await b.client_count() == 0

    @pytest.mark.asyncio
    async def test_register_increments_count(self) -> None:
        b = Broadcaster()
        ws = MockWS()
        await b.register(ws)
        assert await b.client_count() == 1

    @pytest.mark.asyncio
    async def test_unregister_decrements_count(self) -> None:
        b = Broadcaster()
        ws = MockWS()
        await b.register(ws)
        await b.unregister(ws)
        assert await b.client_count() == 0

    @pytest.mark.asyncio
    async def test_unregister_idempotent(self) -> None:
        b = Broadcaster()
        ws = MockWS()
        await b.unregister(ws)  # nunca estuvo
        await b.register(ws)
        await b.unregister(ws)
        await b.unregister(ws)  # segunda vez
        assert await b.client_count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# Broadcast
# ═══════════════════════════════════════════════════════════════════════════


class TestBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_with_no_clients_noop(self) -> None:
        b = Broadcaster()
        await b.broadcast(EVENT_SIGNAL_NEW, {"ticker": "QQQ"})
        # No raise, no side effect

    @pytest.mark.asyncio
    async def test_broadcast_delivers_to_all_clients(self) -> None:
        b = Broadcaster()
        ws1, ws2, ws3 = MockWS(), MockWS(), MockWS()
        await b.register(ws1)
        await b.register(ws2)
        await b.register(ws3)

        payload = {"ticker": "QQQ", "score": 8.0}
        await b.broadcast(EVENT_SIGNAL_NEW, payload)

        for ws in (ws1, ws2, ws3):
            assert len(ws.received) == 1

    @pytest.mark.asyncio
    async def test_envelope_shape(self) -> None:
        b = Broadcaster()
        ws = MockWS()
        await b.register(ws)
        await b.broadcast(EVENT_SYSTEM_LOG, {"level": "info", "message": "ok"})

        env = ws.received[0]
        assert env["event"] == EVENT_SYSTEM_LOG
        assert env["payload"] == {"level": "info", "message": "ok"}
        # timestamp ISO8601 tz-aware
        ts = dt.datetime.fromisoformat(env["timestamp"])
        assert ts.tzinfo is not None

    @pytest.mark.asyncio
    async def test_failing_client_gets_unregistered(self) -> None:
        b = Broadcaster()
        ok = MockWS()
        bad = MockWS(fail_on_send=True)
        await b.register(ok)
        await b.register(bad)

        await b.broadcast(EVENT_ENGINE_STATUS, {"engine": "data"})
        # ok recibió, bad falló y se deregistró
        assert len(ok.received) == 1
        assert await b.client_count() == 1

    @pytest.mark.asyncio
    async def test_multiple_broadcasts_accumulate(self) -> None:
        b = Broadcaster()
        ws = MockWS()
        await b.register(ws)
        for i in range(5):
            await b.broadcast(EVENT_SIGNAL_NEW, {"seq": i})
        assert len(ws.received) == 5
        assert [e["payload"]["seq"] for e in ws.received] == [0, 1, 2, 3, 4]


# ═══════════════════════════════════════════════════════════════════════════
# Event catálogo
# ═══════════════════════════════════════════════════════════════════════════


class TestEventCatalog:
    def test_all_events_set_has_6(self) -> None:
        assert len(ALL_EVENTS) == 6

    def test_all_events_match_spec(self) -> None:
        expected = {
            "signal.new", "slot.status", "engine.status",
            "api_usage.tick", "validator.progress", "system.log",
        }
        assert expected == ALL_EVENTS
