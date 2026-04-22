"""Tests de modelos SQLAlchemy + bootstrap (Sub-fase C5.1).

Cubre:
- `now_et()` devuelve tz-aware ET.
- `create_all()` crea las 3 tablas con sus índices.
- Insert/select básico de cada modelo preserva tz-aware en ET.
- `init_db()` bootstrapping en DB vacía (sin Alembic cfg).
"""

from __future__ import annotations

import datetime as dt
import zoneinfo

import pytest
import pytest_asyncio
from sqlalchemy import select

from modules.db import (
    ET_TZ,
    Heartbeat,
    Signal,
    SystemLog,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
    now_et,
)


@pytest_asyncio.fixture
async def session():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
    await engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# now_et() helper
# ═══════════════════════════════════════════════════════════════════════════


class TestNowEt:
    def test_returns_tz_aware(self) -> None:
        ts = now_et()
        assert ts.tzinfo is not None

    def test_tz_is_america_new_york(self) -> None:
        ts = now_et()
        assert ts.tzinfo == zoneinfo.ZoneInfo("America/New_York")

    def test_et_tz_singleton_matches(self) -> None:
        assert zoneinfo.ZoneInfo("America/New_York") == ET_TZ


# ═══════════════════════════════════════════════════════════════════════════
# Signal model
# ═══════════════════════════════════════════════════════════════════════════


class TestSignalModel:
    @pytest.mark.asyncio
    async def test_insert_minimal_signal(self, session) -> None:
        candle_ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        sig = Signal(
            candle_timestamp=candle_ts,
            engine_version="5.2.0",
            fixture_id="qqq_canonical_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="A",
            layers_json={"structure": {"pass": True}},
            ind_json={"price": 500.0},
            patterns_json=[],
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        assert sig.id is not None

    @pytest.mark.asyncio
    async def test_persisted_timestamp_preserves_tz(self, session) -> None:
        candle_ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        sig = Signal(
            candle_timestamp=candle_ts,
            engine_version="5.2.0",
            fixture_id="qqq_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="B",
            layers_json={},
            ind_json={},
            patterns_json=[],
        )
        session.add(sig)
        await session.commit()
        result = await session.execute(select(Signal).where(Signal.id == sig.id))
        fetched = result.scalar_one()
        # El timestamp leído debe seguir siendo tz-aware (ADR-0002).
        assert fetched.candle_timestamp.tzinfo is not None
        assert fetched.candle_timestamp == candle_ts

    @pytest.mark.asyncio
    async def test_compute_timestamp_defaults_to_now_et(self, session) -> None:
        sig = Signal(
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            engine_version="5.2.0",
            fixture_id="qqq_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="A",
            layers_json={},
            ind_json={},
            patterns_json=[],
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        assert sig.compute_timestamp.tzinfo is not None
        # El default debe estar cerca de ahora (dentro de 10 seg)
        delta = abs((now_et() - sig.compute_timestamp).total_seconds())
        assert delta < 10

    @pytest.mark.asyncio
    async def test_json_blobs_roundtrip(self, session) -> None:
        patterns = [
            {"cat": "TRIGGER", "w": 3.0, "sg": "CALL", "d": "Doble piso"},
            {"cat": "CONFIRM", "w": 4.0, "sg": "CONFIRM", "d": "FzaRel +1.5% vs SPY"},
        ]
        sig = Signal(
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            engine_version="5.2.0",
            fixture_id="qqq_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="A",
            layers_json={"structure": {"pass": True, "override": False}},
            ind_json={"price": 500.0, "bb_1h": [510.0, 500.0, 490.0]},
            patterns_json=patterns,
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        assert sig.layers_json == {"structure": {"pass": True, "override": False}}
        assert sig.patterns_json == patterns

    @pytest.mark.asyncio
    async def test_optional_fields_nullable(self, session) -> None:
        sig = Signal(
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            engine_version="5.2.0",
            fixture_id="qqq_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="—",
            layers_json={},
            ind_json={},
            patterns_json=[],
            # slot_id, score, dir, error_code, sec_rel_json, div_spy_json,
            # candles_snapshot_gzip: todos nullable / default
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        assert sig.slot_id is None
        assert sig.score is None
        assert sig.dir is None
        assert sig.error_code is None
        assert sig.sec_rel_json is None
        assert sig.div_spy_json is None
        assert sig.candles_snapshot_gzip is None

    @pytest.mark.asyncio
    async def test_defaults_bool_fields(self, session) -> None:
        sig = Signal(
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            engine_version="5.2.0",
            fixture_id="qqq_v1",
            fixture_version="5.2.0",
            ticker="QQQ",
            conf="—",
            layers_json={},
            ind_json={},
            patterns_json=[],
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        assert sig.signal is False
        assert sig.blocked is False
        assert sig.error is False


# ═══════════════════════════════════════════════════════════════════════════
# Heartbeat model
# ═══════════════════════════════════════════════════════════════════════════


class TestHeartbeatModel:
    @pytest.mark.asyncio
    async def test_insert_heartbeat(self, session) -> None:
        hb = Heartbeat(engine="scoring", status="green", memory_pct=12.5)
        session.add(hb)
        await session.commit()
        await session.refresh(hb)
        assert hb.id is not None
        assert hb.ts.tzinfo is not None

    @pytest.mark.asyncio
    async def test_heartbeat_optional_fields(self, session) -> None:
        hb = Heartbeat(engine="data", status="yellow")
        session.add(hb)
        await session.commit()
        await session.refresh(hb)
        assert hb.memory_pct is None
        assert hb.error_code is None


# ═══════════════════════════════════════════════════════════════════════════
# SystemLog model
# ═══════════════════════════════════════════════════════════════════════════


class TestSystemLogModel:
    @pytest.mark.asyncio
    async def test_insert_system_log(self, session) -> None:
        log = SystemLog(
            level="info",
            source="scoring_engine",
            message="Scan cycle completed",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        assert log.id is not None
        assert log.ts.tzinfo is not None

    @pytest.mark.asyncio
    async def test_error_log_with_code(self, session) -> None:
        log = SystemLog(
            level="error",
            source="data_engine",
            message="Rate limit exceeded",
            error_code="ENG-060",
        )
        session.add(log)
        await session.commit()
        await session.refresh(log)
        assert log.error_code == "ENG-060"


# ═══════════════════════════════════════════════════════════════════════════
# init_db bootstrapping
# ═══════════════════════════════════════════════════════════════════════════


class TestInitDb:
    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self) -> None:
        from sqlalchemy import inspect

        engine = make_engine(default_url(":memory:"))
        await init_db(engine)

        async with engine.begin() as conn:
            tables = await conn.run_sync(lambda c: inspect(c).get_table_names())

        assert "signals" in tables
        assert "heartbeat" in tables
        assert "system_log" in tables
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_init_db_idempotent(self) -> None:
        """Llamar init_db 2 veces no debe fallar (la segunda ve tablas existentes)."""
        engine = make_engine(default_url(":memory:"))
        await init_db(engine)
        await init_db(engine)  # segunda llamada no hace nada (sin Alembic cfg)
        await engine.dispose()
