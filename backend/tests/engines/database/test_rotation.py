"""Tests de `rotate_expired` (C5.7) — rotación por políticas de retención."""

from __future__ import annotations

import datetime as dt

import pytest
import pytest_asyncio
from sqlalchemy import select

from engines.database import DEFAULT_RETENTION_POLICIES, rotate_expired
from modules.db import (
    ET_TZ,
    Heartbeat,
    Signal,
    SystemLog,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
    write_heartbeat,
    write_system_log,
)


@pytest_asyncio.fixture
async def session():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
    await engine.dispose()


def _analyze_out() -> dict:
    return {
        "ticker": "QQQ", "engine_version": "5.2.0",
        "fixture_id": "qqq_v1", "fixture_version": "5.2.0",
        "score": 4.0, "conf": "B", "signal": "REVISAR", "dir": "CALL",
        "blocked": None, "error": False, "error_code": None,
        "layers": {}, "ind": {}, "patterns": [],
        "sec_rel": None, "div_spy": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Default policies
# ═══════════════════════════════════════════════════════════════════════════


class TestDefaultPolicies:
    def test_signals_one_year(self) -> None:
        assert DEFAULT_RETENTION_POLICIES["signals"] == dt.timedelta(days=365)

    def test_heartbeat_24h(self) -> None:
        assert DEFAULT_RETENTION_POLICIES["heartbeat"] == dt.timedelta(hours=24)

    def test_system_log_30_days(self) -> None:
        assert DEFAULT_RETENTION_POLICIES["system_log"] == dt.timedelta(days=30)


# ═══════════════════════════════════════════════════════════════════════════
# Rotación con `now` fijo
# ═══════════════════════════════════════════════════════════════════════════


class TestRotateExpired:
    @pytest.mark.asyncio
    async def test_empty_db_no_deletes(self, session) -> None:
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        deleted = await rotate_expired(session, now=now_fake)
        assert all(v == 0 for v in deleted.values())

    @pytest.mark.asyncio
    async def test_heartbeat_older_than_24h_deleted(self, session) -> None:
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        # Insertar 1 hb viejo (hace 2 días) y 1 reciente (hace 1h)
        old_hb = Heartbeat(
            ts=now_fake - dt.timedelta(days=2),
            engine="scoring", status="green",
        )
        new_hb = Heartbeat(
            ts=now_fake - dt.timedelta(hours=1),
            engine="scoring", status="green",
        )
        session.add_all([old_hb, new_hb])
        await session.commit()

        deleted = await rotate_expired(session, now=now_fake)
        assert deleted["heartbeat"] == 1

        # Solo queda el reciente
        result = await session.execute(select(Heartbeat))
        rows = result.scalars().all()
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_system_log_older_than_30_days_deleted(self, session) -> None:
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        old = SystemLog(
            ts=now_fake - dt.timedelta(days=31),
            level="info", source="test", message="old",
        )
        new = SystemLog(
            ts=now_fake - dt.timedelta(days=15),
            level="info", source="test", message="new",
        )
        session.add_all([old, new])
        await session.commit()

        deleted = await rotate_expired(session, now=now_fake)
        assert deleted["system_log"] == 1

    @pytest.mark.asyncio
    async def test_signals_older_than_1y_deleted(self, session) -> None:
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        old_sig = Signal(
            candle_timestamp=now_fake - dt.timedelta(days=400),
            compute_timestamp=now_fake - dt.timedelta(days=400),
            engine_version="5.2.0", fixture_id="qqq", fixture_version="5.2.0",
            ticker="QQQ", conf="B",
            layers_json={}, ind_json={}, patterns_json=[],
        )
        new_sig = Signal(
            candle_timestamp=now_fake - dt.timedelta(days=30),
            compute_timestamp=now_fake - dt.timedelta(days=30),
            engine_version="5.2.0", fixture_id="qqq", fixture_version="5.2.0",
            ticker="QQQ", conf="A",
            layers_json={}, ind_json={}, patterns_json=[],
        )
        session.add_all([old_sig, new_sig])
        await session.commit()

        deleted = await rotate_expired(session, now=now_fake)
        assert deleted["signals"] == 1

    @pytest.mark.asyncio
    async def test_custom_policies_override_defaults(self, session) -> None:
        """Si se pasa un subset de políticas, solo esas rotan."""
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        # Inserta 1 log viejo y 1 hb viejo — con política solo para hb
        await write_heartbeat(session, engine="scoring", status="green")
        # Retrocedo el ts manualmente
        result = await session.execute(select(Heartbeat))
        hb = result.scalar_one()
        hb.ts = now_fake - dt.timedelta(hours=25)
        await session.commit()

        await write_system_log(session, level="info", source="t", message="m")
        result = await session.execute(select(SystemLog))
        log = result.scalar_one()
        log.ts = now_fake - dt.timedelta(days=31)
        await session.commit()

        # Política solo para heartbeat
        policies = {"heartbeat": dt.timedelta(hours=24)}
        deleted = await rotate_expired(session, policies=policies, now=now_fake)
        assert deleted == {"heartbeat": 1}

        # El log NO se tocó
        result = await session.execute(select(SystemLog))
        assert len(result.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_unknown_table_skipped(self, session) -> None:
        now_fake = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        policies = {"unknown_table": dt.timedelta(days=1)}
        deleted = await rotate_expired(session, policies=policies, now=now_fake)
        assert deleted == {"unknown_table": 0}

    @pytest.mark.asyncio
    async def test_rotation_uses_now_et_by_default(self, session) -> None:
        """Sin `now` explícito, usa `now_et()`."""
        await write_heartbeat(session, engine="scoring", status="green")
        # Default policies — el hb recién insertado (hace segundos) NO
        # debería ser eliminado (< 24h)
        deleted = await rotate_expired(session)
        assert deleted["heartbeat"] == 0
