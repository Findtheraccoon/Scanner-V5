"""Tests del heartbeat worker (D.1)."""

from __future__ import annotations

import asyncio
import contextlib

import pytest
import pytest_asyncio
from sqlalchemy import select

from api.broadcaster import Broadcaster
from api.events import EVENT_ENGINE_STATUS
from api.workers import auto_scheduler_worker, heartbeat_worker
from modules.db import (
    Heartbeat,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
)


@pytest_asyncio.fixture
async def db():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


class RecordingWS:
    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, data) -> None:
        self.received.append(data)


class TestHeartbeatWorker:
    @pytest.mark.asyncio
    async def test_emits_and_broadcasts(self, db) -> None:
        """El worker debe persistir + broadcast en cada tick."""
        broadcaster = Broadcaster()
        ws = RecordingWS()
        await broadcaster.register(ws)

        # Interval corto para que dispare al menos una vez.
        task = asyncio.create_task(
            heartbeat_worker(db, broadcaster, interval_s=0.05),
        )
        # Esperar al menos un ciclo completo con margen
        await asyncio.sleep(0.3)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Al menos un heartbeat en DB
        async with db() as session:
            result = await session.execute(select(Heartbeat))
            hbs = result.scalars().all()
        assert len(hbs) >= 1
        assert hbs[0].engine == "scoring"
        assert hbs[0].status == "green"

        # Al menos un envelope broadcast
        assert len(ws.received) >= 1
        assert ws.received[0]["event"] == EVENT_ENGINE_STATUS
        assert ws.received[0]["payload"] == {
            "engine": "scoring", "status": "green",
        }

    @pytest.mark.asyncio
    async def test_cancel_is_clean(self, db) -> None:
        """Al cancelar el task debe terminar sin raise hacia el caller."""
        broadcaster = Broadcaster()
        task = asyncio.create_task(
            heartbeat_worker(db, broadcaster, interval_s=60.0),
        )
        # Dar tiempo mínimo para que arranque
        await asyncio.sleep(0.01)
        task.cancel()
        # Si `CancelledError` se maneja mal, esto raisearía. Con
        # `suppress` validamos que el loop se limpia sin error colateral.
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.done()

    @pytest.mark.asyncio
    async def test_custom_engine_name(self, db) -> None:
        broadcaster = Broadcaster()
        task = asyncio.create_task(
            heartbeat_worker(
                db, broadcaster,
                engine_name="data", interval_s=0.05,
            ),
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        async with db() as session:
            result = await session.execute(select(Heartbeat))
            hbs = result.scalars().all()
        assert all(h.engine == "data" for h in hbs)


# ═══════════════════════════════════════════════════════════════════════════
# Auto-scheduler worker (stub D.3)
# ═══════════════════════════════════════════════════════════════════════════


class TestAutoSchedulerWorker:
    @pytest.mark.asyncio
    async def test_emits_ticks(self) -> None:
        """El worker debe emitir engine.status del Data Engine (stub)."""
        broadcaster = Broadcaster()
        ws = RecordingWS()
        await broadcaster.register(ws)

        task = asyncio.create_task(
            auto_scheduler_worker(broadcaster, interval_s=0.05),
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Al menos un envelope
        assert len(ws.received) >= 1
        env = ws.received[0]
        assert env["event"] == EVENT_ENGINE_STATUS
        assert env["payload"]["engine"] == "data"
        assert env["payload"]["status"] == "yellow"
        assert "stub" in env["payload"]["message"]

    @pytest.mark.asyncio
    async def test_cancel_is_clean(self) -> None:
        broadcaster = Broadcaster()
        task = asyncio.create_task(
            auto_scheduler_worker(broadcaster, interval_s=60.0),
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.done()
