"""Tests de tablas de candles + helpers (DE.1)."""

from __future__ import annotations

import datetime as dt

import pytest
import pytest_asyncio

from modules.db import (
    ET_TZ,
    default_url,
    init_db,
    latest_candle_dt,
    make_engine,
    make_session_factory,
    read_candles_window,
    write_candles_batch,
)


@pytest_asyncio.fixture
async def session():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
    await engine.dispose()


def _candle(
    *,
    year: int = 2026,
    month: int = 4,
    day: int = 22,
    hour: int = 10,
    minute: int = 30,
    c: float = 500.0,
) -> dict:
    return {
        "dt": dt.datetime(year, month, day, hour, minute, tzinfo=ET_TZ),
        "o": c - 1,
        "h": c + 1,
        "l": c - 2,
        "c": c,
        "v": 1_000_000,
    }


# ═══════════════════════════════════════════════════════════════════════════
# write_candles_batch — UPSERT idempotente por (ticker, dt)
# ═══════════════════════════════════════════════════════════════════════════


class TestWriteCandlesBatch:
    @pytest.mark.asyncio
    async def test_empty_list_noop(self, session) -> None:
        n = await write_candles_batch(
            session, timeframe="15m", ticker="QQQ", candles=[],
        )
        assert n == 0

    @pytest.mark.asyncio
    async def test_insert_batch(self, session) -> None:
        candles = [_candle(minute=m) for m in (0, 15, 30, 45)]
        n = await write_candles_batch(
            session, timeframe="15m", ticker="QQQ", candles=candles,
        )
        assert n == 4

    @pytest.mark.asyncio
    async def test_roundtrip_tz_aware(self, session) -> None:
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ",
            candles=[_candle(c=500.25)],
        )
        got = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
        )
        assert len(got) == 1
        assert got[0]["dt"].tzinfo is not None
        assert got[0]["c"] == 500.25

    @pytest.mark.asyncio
    async def test_upsert_same_dt_updates(self, session) -> None:
        """Insertar 2x el mismo (ticker, dt) → sobreescribe valores."""
        c1 = _candle(c=500.0)
        c2 = _candle(c=510.0)  # mismo dt, distinto close

        await write_candles_batch(
            session, timeframe="1h", ticker="QQQ", candles=[c1],
        )
        await write_candles_batch(
            session, timeframe="1h", ticker="QQQ", candles=[c2],
        )

        got = await read_candles_window(
            session, timeframe="1h", ticker="QQQ",
        )
        assert len(got) == 1  # Sin duplicado
        assert got[0]["c"] == 510.0  # Valor nuevo

    @pytest.mark.asyncio
    async def test_tables_are_isolated_per_tf(self, session) -> None:
        """Candles en 15m NO aparecen en queries de daily."""
        await write_candles_batch(
            session, timeframe="15m", ticker="QQQ", candles=[_candle()],
        )
        got_daily = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
        )
        assert got_daily == []


# ═══════════════════════════════════════════════════════════════════════════
# read_candles_window — filtros + orden
# ═══════════════════════════════════════════════════════════════════════════


class TestReadCandlesWindow:
    @pytest.mark.asyncio
    async def test_empty_table_returns_empty(self, session) -> None:
        got = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
        )
        assert got == []

    @pytest.mark.asyncio
    async def test_orders_ascending_by_dt(self, session) -> None:
        candles = [
            _candle(day=22),
            _candle(day=20),
            _candle(day=21),
        ]
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ", candles=candles,
        )
        got = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
        )
        dts = [c["dt"].day for c in got]
        assert dts == [20, 21, 22]

    @pytest.mark.asyncio
    async def test_filter_by_range(self, session) -> None:
        candles = [_candle(day=d) for d in (18, 20, 22, 24)]
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ", candles=candles,
        )
        got = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
            from_ts=dt.datetime(2026, 4, 20, 0, 0, tzinfo=ET_TZ),
            to_ts=dt.datetime(2026, 4, 22, 23, 59, tzinfo=ET_TZ),
        )
        assert [c["dt"].day for c in got] == [20, 22]

    @pytest.mark.asyncio
    async def test_limit_returns_most_recent(self, session) -> None:
        candles = [_candle(day=d) for d in (18, 20, 22, 24)]
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ", candles=candles,
        )
        got = await read_candles_window(
            session, timeframe="daily", ticker="QQQ", limit=2,
        )
        # Las últimas 2, ordenadas asc
        assert [c["dt"].day for c in got] == [22, 24]

    @pytest.mark.asyncio
    async def test_filter_by_ticker(self, session) -> None:
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ", candles=[_candle(c=500)],
        )
        await write_candles_batch(
            session, timeframe="daily", ticker="SPY", candles=[_candle(c=600)],
        )
        got_qqq = await read_candles_window(
            session, timeframe="daily", ticker="QQQ",
        )
        assert len(got_qqq) == 1
        assert got_qqq[0]["c"] == 500


# ═══════════════════════════════════════════════════════════════════════════
# latest_candle_dt — gap detection para consulta DB antes de fetch
# ═══════════════════════════════════════════════════════════════════════════


class TestLatestCandleDt:
    @pytest.mark.asyncio
    async def test_empty_returns_none(self, session) -> None:
        result = await latest_candle_dt(
            session, timeframe="daily", ticker="QQQ",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_max_dt(self, session) -> None:
        candles = [_candle(day=d) for d in (18, 20, 22, 19)]
        await write_candles_batch(
            session, timeframe="daily", ticker="QQQ", candles=candles,
        )
        result = await latest_candle_dt(
            session, timeframe="daily", ticker="QQQ",
        )
        assert result is not None
        assert result.day == 22

    @pytest.mark.asyncio
    async def test_tz_aware_at_read(self, session) -> None:
        await write_candles_batch(
            session, timeframe="15m", ticker="QQQ", candles=[_candle()],
        )
        result = await latest_candle_dt(
            session, timeframe="15m", ticker="QQQ",
        )
        assert result.tzinfo is not None
