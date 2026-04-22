"""Tests de lectura transparente op + archive (AR.3, spec §3.7 Opción X).

Insertamos filas en 2 DBs independientes (simulando post-rotación) y
verificamos que los helpers mergean correctamente.
"""

from __future__ import annotations

import datetime as _dt

import pytest
import pytest_asyncio

from modules.db import (
    ET_TZ,
    CandleDaily,
    Signal,
    init_db,
    make_engine,
    make_session_factory,
    read_candles_window,
    read_signal_by_id,
    read_signals_history,
)


@pytest_asyncio.fixture
async def op_and_archive():
    op_engine = make_engine("sqlite+aiosqlite:///:memory:")
    archive_engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(op_engine)
    await init_db(archive_engine)
    op_factory = make_session_factory(op_engine)
    archive_factory = make_session_factory(archive_engine)
    yield op_factory, archive_factory
    await op_engine.dispose()
    await archive_engine.dispose()


def _sig(
    id_: int, *, slot_id: int = 1, ticker: str = "QQQ", days_ago: int = 0,
) -> Signal:
    now = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
    ts = now - _dt.timedelta(days=days_ago)
    return Signal(
        id=id_,
        ticker=ticker,
        slot_id=slot_id,
        engine_version="5.2.0",
        fixture_id="qqq_test", fixture_version="5.2.0",
        compute_timestamp=ts, candle_timestamp=ts,
        score=1.0 + id_, conf="NEUTRAL", signal=False, blocked=False,
        layers_json={}, ind_json={}, patterns_json=[],
    )


class TestHistoryMerge:
    @pytest.mark.asyncio
    async def test_merges_in_id_desc_order(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive

        # 3 filas viejas en archive (ids 1-3), 2 recientes en op (ids 10-11)
        async with archive_factory() as ar:
            for i in (1, 2, 3):
                ar.add(_sig(i, days_ago=400 - i))
            await ar.commit()
        async with op_factory() as op:
            for i in (10, 11):
                op.add(_sig(i, days_ago=11 - i))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            items, next_cursor = await read_signals_history(
                op, archive_session=ar, limit=100,
            )

        ids = [s["id"] for s in items]
        assert ids == [11, 10, 3, 2, 1]
        assert next_cursor is None

    @pytest.mark.asyncio
    async def test_cursor_paginates_across_both(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            for i in (1, 2, 3):
                ar.add(_sig(i, days_ago=400 - i))
            await ar.commit()
        async with op_factory() as op:
            for i in (10, 11, 12):
                op.add(_sig(i, days_ago=12 - i))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            first, cur = await read_signals_history(
                op, archive_session=ar, limit=3,
            )
            assert [s["id"] for s in first] == [12, 11, 10]
            assert cur == 10

            second, cur2 = await read_signals_history(
                op, archive_session=ar, cursor=cur, limit=3,
            )
        assert [s["id"] for s in second] == [3, 2, 1]
        assert cur2 is None

    @pytest.mark.asyncio
    async def test_without_archive_session_ignores_archive(
        self, op_and_archive,
    ) -> None:
        """Archive session None → solo devuelve filas de op."""
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(1, days_ago=400))
            await ar.commit()
        async with op_factory() as op:
            op.add(_sig(10, days_ago=1))
            await op.commit()

        async with op_factory() as op:
            items, _ = await read_signals_history(op, limit=100)
        assert [s["id"] for s in items] == [10]

    @pytest.mark.asyncio
    async def test_slot_filter_applied_to_both(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(1, slot_id=1, days_ago=300))
            ar.add(_sig(2, slot_id=2, days_ago=300))
            await ar.commit()
        async with op_factory() as op:
            op.add(_sig(10, slot_id=1, days_ago=1))
            op.add(_sig(11, slot_id=2, days_ago=1))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            items, _ = await read_signals_history(
                op, archive_session=ar, slot_id=1, limit=100,
            )
        assert {s["id"] for s in items} == {1, 10}

    @pytest.mark.asyncio
    async def test_dedup_op_wins(self, op_and_archive) -> None:
        """Defensivo: si la misma id está en ambas DBs, prevalece op."""
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(5, ticker="OLD", days_ago=300))
            await ar.commit()
        async with op_factory() as op:
            op.add(_sig(5, ticker="NEW", days_ago=1))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            items, _ = await read_signals_history(
                op, archive_session=ar, limit=100,
            )
        assert len(items) == 1
        assert items[0]["ticker"] == "NEW"


class TestReadByIdMerge:
    @pytest.mark.asyncio
    async def test_found_in_archive_when_missing_op(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(1, days_ago=400))
            await ar.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await read_signal_by_id(op, 1, archive_session=ar)
        assert result is not None
        assert result["id"] == 1

    @pytest.mark.asyncio
    async def test_op_takes_precedence(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(1, ticker="STALE", days_ago=400))
            await ar.commit()
        async with op_factory() as op:
            op.add(_sig(1, ticker="FRESH", days_ago=1))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            result = await read_signal_by_id(op, 1, archive_session=ar)
        assert result is not None
        assert result["ticker"] == "FRESH"

    @pytest.mark.asyncio
    async def test_none_when_not_in_either(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        async with op_factory() as op, archive_factory() as ar:
            result = await read_signal_by_id(op, 9999, archive_session=ar)
        assert result is None

    @pytest.mark.asyncio
    async def test_without_archive_only_op_checked(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        async with archive_factory() as ar:
            ar.add(_sig(1, days_ago=400))
            await ar.commit()
        async with op_factory() as op:
            result = await read_signal_by_id(op, 1)
        assert result is None


class TestCandlesMerge:
    @pytest.mark.asyncio
    async def test_merges_and_sorts_asc(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        base = _dt.datetime(2026, 1, 1, tzinfo=ET_TZ)

        async with archive_factory() as ar:
            for i in range(3):  # 3 velas viejas
                ar.add(CandleDaily(
                    ticker="QQQ", dt=base + _dt.timedelta(days=i),
                    o=100 + i, h=101 + i, l=99 + i, c=100 + i, v=1000,
                ))
            await ar.commit()
        async with op_factory() as op:
            for i in (10, 11, 12):
                op.add(CandleDaily(
                    ticker="QQQ", dt=base + _dt.timedelta(days=i),
                    o=200 + i, h=201 + i, l=199 + i, c=200 + i, v=2000,
                ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            rows = await read_candles_window(
                op, timeframe="daily", ticker="QQQ",
                archive_session=ar,
            )
        # 6 velas, orden asc por dt, archive primero por datetime
        assert len(rows) == 6
        assert rows[0]["c"] == 100  # día 0 del archive
        assert rows[-1]["c"] == 212  # día 12 de op

    @pytest.mark.asyncio
    async def test_dedup_op_wins_on_same_dt(self, op_and_archive) -> None:
        op_factory, archive_factory = op_and_archive
        same_dt = _dt.datetime(2026, 1, 1, tzinfo=ET_TZ)
        async with archive_factory() as ar:
            ar.add(CandleDaily(
                ticker="QQQ", dt=same_dt,
                o=100, h=101, l=99, c=100, v=1000,  # viejo
            ))
            await ar.commit()
        async with op_factory() as op:
            op.add(CandleDaily(
                ticker="QQQ", dt=same_dt,
                o=200, h=201, l=199, c=200, v=2000,  # nuevo
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            rows = await read_candles_window(
                op, timeframe="daily", ticker="QQQ",
                archive_session=ar,
            )
        assert len(rows) == 1
        assert rows[0]["c"] == 200  # op gana

    @pytest.mark.asyncio
    async def test_from_ts_filter_applied_to_both(
        self, op_and_archive,
    ) -> None:
        op_factory, archive_factory = op_and_archive
        base = _dt.datetime(2026, 1, 1, tzinfo=ET_TZ)
        async with archive_factory() as ar:
            ar.add(CandleDaily(
                ticker="QQQ", dt=base, o=0, h=0, l=0, c=0, v=0,
            ))
            await ar.commit()
        async with op_factory() as op:
            op.add(CandleDaily(
                ticker="QQQ", dt=base + _dt.timedelta(days=10),
                o=0, h=0, l=0, c=0, v=0,
            ))
            await op.commit()

        async with op_factory() as op, archive_factory() as ar:
            rows = await read_candles_window(
                op, timeframe="daily", ticker="QQQ",
                archive_session=ar,
                from_ts=base + _dt.timedelta(days=5),
            )
        # Solo la de op (día 10) pasa el filtro
        assert len(rows) == 1
