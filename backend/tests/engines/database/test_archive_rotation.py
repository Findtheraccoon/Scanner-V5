"""Tests de `rotate_with_archive` + `compute_stats` (AR.1)."""

from __future__ import annotations

import datetime as _dt

import pytest
import pytest_asyncio

from engines.database.rotation import (
    DEFAULT_RETENTION_POLICIES,
    compute_stats,
    rotate_with_archive,
)
from modules.db import (
    ET_TZ,
    CandleDaily,
    Heartbeat,
    Signal,
    SystemLog,
    init_db,
    make_engine,
    make_session_factory,
)


@pytest_asyncio.fixture
async def op_and_archive():
    """Dos engines `:memory:` independientes — uno operativa, uno archive."""
    op_engine = make_engine("sqlite+aiosqlite:///:memory:")
    archive_engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(op_engine)
    await init_db(archive_engine)
    op_factory = make_session_factory(op_engine)
    archive_factory = make_session_factory(archive_engine)
    yield op_factory, archive_factory
    await op_engine.dispose()
    await archive_engine.dispose()


def _dt_et(year, month, day, hour=10, minute=0) -> _dt.datetime:
    return _dt.datetime(year, month, day, hour, minute, tzinfo=ET_TZ)


class TestSignalsRotation:
    @pytest.mark.asyncio
    async def test_moves_expired_signals(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)

        # Insertar 2 señales: 1 vencida (400 días atrás) + 1 fresca (10 días)
        async with op_factory() as op:
            op.add(Signal(
                ticker="QQQ",
                engine_version="5.2.0",
                compute_timestamp=now - _dt.timedelta(days=400),
                candle_timestamp=now - _dt.timedelta(days=400),
                fixture_id="qqq_test", fixture_version="5.2.0",
                score=5.0, conf="NEUTRAL", signal=False, blocked=False,
                layers_json={}, ind_json={}, patterns_json=[],
            ))
            op.add(Signal(
                ticker="SPY",
                engine_version="5.2.0",
                compute_timestamp=now - _dt.timedelta(days=10),
                candle_timestamp=now - _dt.timedelta(days=10),
                fixture_id="qqq_test", fixture_version="5.2.0",
                score=5.0, conf="NEUTRAL", signal=False, blocked=False,
                layers_json={}, ind_json={}, patterns_json=[],
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await rotate_with_archive(op, ar, now=now)

        assert result["signals"]["archived"] == 1
        assert result["signals"]["deleted"] == 1

        # Op queda con 1 (SPY fresco); archive tiene 1 (QQQ vencido)
        async with op_factory() as op:
            from sqlalchemy import select
            rows = (await op.execute(select(Signal))).scalars().all()
            assert len(rows) == 1
            assert rows[0].ticker == "SPY"

        async with archive_factory() as ar:
            from sqlalchemy import select
            rows = (await ar.execute(select(Signal))).scalars().all()
            assert len(rows) == 1
            assert rows[0].ticker == "QQQ"


class TestHeartbeatRotation:
    @pytest.mark.asyncio
    async def test_heartbeat_deletes_without_archive(
        self, op_and_archive,
    ) -> None:
        """`heartbeat` se borra sin copiar al archive (spec §3.7)."""
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)

        async with op_factory() as op:
            op.add(Heartbeat(
                engine="scoring",
                status="green",
                ts=now - _dt.timedelta(hours=48),  # vencido
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await rotate_with_archive(op, ar, now=now)

        assert result["heartbeat"]["archived"] == 0
        assert result["heartbeat"]["deleted"] == 1

        # Archive sin heartbeats
        async with archive_factory() as ar:
            from sqlalchemy import select
            rows = (await ar.execute(select(Heartbeat))).scalars().all()
            assert rows == []


class TestCandlesRotation:
    @pytest.mark.asyncio
    async def test_candles_daily_moves_when_older_than_3_years(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)

        async with op_factory() as op:
            # 1 vela vencida (4 años atrás) + 1 fresca (1 año atrás)
            op.add(CandleDaily(
                ticker="QQQ", dt=now - _dt.timedelta(days=365 * 4),
                o=100, h=101, l=99, c=100.5, v=1000,
            ))
            op.add(CandleDaily(
                ticker="QQQ", dt=now - _dt.timedelta(days=365),
                o=200, h=201, l=199, c=200.5, v=2000,
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await rotate_with_archive(op, ar, now=now)

        assert result["candles_daily"]["archived"] == 1
        assert result["candles_daily"]["deleted"] == 1

        async with op_factory() as op:
            from sqlalchemy import select
            rows = (await op.execute(select(CandleDaily))).scalars().all()
            assert len(rows) == 1
            assert rows[0].c == 200.5

        async with archive_factory() as ar:
            from sqlalchemy import select
            rows = (await ar.execute(select(CandleDaily))).scalars().all()
            assert len(rows) == 1
            assert rows[0].c == 100.5


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_second_rotation_is_noop(self, op_and_archive) -> None:
        """Re-correr la rotación no duplica filas en archive."""
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)

        async with op_factory() as op:
            op.add(SystemLog(
                level="warning",
                source="test",
                message="old event",
                ts=now - _dt.timedelta(days=90),
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            await rotate_with_archive(op, ar, now=now)

        # Re-correr — nada debería pasar
        async with op_factory() as op, archive_factory() as ar:
            result2 = await rotate_with_archive(op, ar, now=now)

        assert result2["system_log"]["archived"] == 0
        assert result2["system_log"]["deleted"] == 0

        # Archive sigue con exactamente 1 fila
        async with archive_factory() as ar:
            from sqlalchemy import select
            rows = (await ar.execute(select(SystemLog))).scalars().all()
            assert len(rows) == 1


class TestNoWorkCase:
    @pytest.mark.asyncio
    async def test_no_expired_rows_returns_zero(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)

        async with op_factory() as op:
            op.add(Signal(
                ticker="QQQ",
                engine_version="5.2.0",
                compute_timestamp=now - _dt.timedelta(days=10),
                candle_timestamp=now - _dt.timedelta(days=10),
                fixture_id="qqq_test", fixture_version="5.2.0",
                score=5.0, conf="NEUTRAL", signal=False, blocked=False,
                layers_json={}, ind_json={}, patterns_json=[],
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await rotate_with_archive(op, ar, now=now)

        for table in DEFAULT_RETENTION_POLICIES:
            assert result.get(table, {"archived": 0, "deleted": 0})["archived"] == 0


class TestComputeStats:
    @pytest.mark.asyncio
    async def test_empty_db_stats(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        async with op_factory() as op, archive_factory() as ar:
            stats = await compute_stats(op, ar)
        for table in ("signals", "heartbeat", "system_log", "candles_daily"):
            assert table in stats
            assert stats[table]["rows_operative"] == 0

    @pytest.mark.asyncio
    async def test_stats_shape_without_archive(
        self, op_and_archive,
    ) -> None:
        op_factory, _ = op_and_archive
        async with op_factory() as op:
            stats = await compute_stats(op, None)
        s = stats["signals"]
        assert s["rows_archive"] is None
        assert s["archives_to_disk"] is True
        h = stats["heartbeat"]
        assert h["archives_to_disk"] is False

    @pytest.mark.asyncio
    async def test_stats_counts_rows_in_both_dbs(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        now = _dt_et(2026, 4, 22)
        async with op_factory() as op:
            op.add(Signal(
                ticker="QQQ",
                engine_version="5.2.0",
                compute_timestamp=now,
                candle_timestamp=now,
                fixture_id="qqq_test", fixture_version="5.2.0",
                score=5.0, conf="NEUTRAL", signal=False, blocked=False,
                layers_json={}, ind_json={}, patterns_json=[],
            ))
            await op.commit()
        async with archive_factory() as ar:
            ar.add(Signal(
                ticker="AAPL",
                engine_version="5.2.0",
                compute_timestamp=now - _dt.timedelta(days=400),
                candle_timestamp=now - _dt.timedelta(days=400),
                fixture_id="qqq_test", fixture_version="5.2.0",
                score=5.0, conf="NEUTRAL", signal=False, blocked=False,
                layers_json={}, ind_json={}, patterns_json=[],
            ))
            await ar.commit()

        async with op_factory() as op, archive_factory() as ar:
            stats = await compute_stats(op, ar)

        assert stats["signals"]["rows_operative"] == 1
        assert stats["signals"]["rows_archive"] == 1
        assert stats["signals"]["retention_seconds"] == 365 * 86400
