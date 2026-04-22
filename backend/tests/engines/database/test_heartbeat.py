"""Tests de `emit_engine_heartbeat` (C5.7)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select

from engines.database import emit_engine_heartbeat
from modules.db import (
    Heartbeat,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


class TestEmitEngineHeartbeat:
    @pytest.mark.asyncio
    async def test_minimal_heartbeat(self, session_factory) -> None:
        hb_id = await emit_engine_heartbeat(
            session_factory, engine="scoring", status="green",
        )
        assert isinstance(hb_id, int)
        assert hb_id > 0

    @pytest.mark.asyncio
    async def test_heartbeat_persisted(self, session_factory) -> None:
        await emit_engine_heartbeat(
            session_factory, engine="data", status="yellow", memory_pct=75.0,
        )
        async with session_factory() as session:
            result = await session.execute(select(Heartbeat))
            rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].engine == "data"
        assert rows[0].status == "yellow"
        assert rows[0].memory_pct == 75.0

    @pytest.mark.asyncio
    async def test_heartbeat_with_error_code(self, session_factory) -> None:
        await emit_engine_heartbeat(
            session_factory, engine="scoring", status="red",
            error_code="ENG-099",
        )
        async with session_factory() as session:
            result = await session.execute(select(Heartbeat))
            hb = result.scalar_one()
        assert hb.status == "red"
        assert hb.error_code == "ENG-099"

    @pytest.mark.asyncio
    async def test_multiple_heartbeats_accumulate(self, session_factory) -> None:
        for status in ("green", "yellow", "green", "red"):
            await emit_engine_heartbeat(
                session_factory, engine="scoring", status=status,
            )
        async with session_factory() as session:
            result = await session.execute(select(Heartbeat))
            rows = result.scalars().all()
        assert len(rows) == 4
