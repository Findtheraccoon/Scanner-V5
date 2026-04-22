"""Tests de DB-first optimization en `DataEngine.warmup()` (DE.3.1 / ADR-0003).

Verifica:

- DB vacía → fetch completo (baseline).
- DB llena + fresco → skip fetch, usa DB. El handler NO se llama.
- DB llena pero stale → fetch completo (ignora DB obsoleta).
- DB con menos de N velas → fetch completo (la DB no cubre el warmup).
- Mix: un ticker cached, otro stale → solo el stale fetchea.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
import pytest_asyncio

from engines.data import DataEngine, KeyPool, TwelveDataClient
from engines.data.models import ApiKeyConfig, Timeframe
from modules.db import (
    ET_TZ,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
    write_candles_batch,
)


def _key() -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id="k1", secret="s-k1",
        credits_per_minute=8, credits_per_day=800,
    )


def _sample_values(count: int, interval: str) -> list[dict]:
    return [
        {
            "datetime": f"2025-01-{i + 1:02d}",
            "open": "100.0", "high": "101.0", "low": "99.0",
            "close": "100.5", "volume": "1000",
        }
        for i in range(count)
    ]


class _CountingHandler:
    """MockTransport handler que contabiliza cuántas veces se llamó."""

    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        interval = request.url.params.get("interval")
        outputsize = int(request.url.params.get("outputsize") or 3)
        return httpx.Response(
            200,
            json={
                "meta": {"symbol": "QQQ", "interval": interval},
                "values": _sample_values(outputsize, interval),
                "status": "ok",
            },
        )


@pytest_asyncio.fixture
async def db_factory():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


async def _warm_fresh_candles(
    db_factory,
    ticker: str,
    tf: str,
    count: int,
    last_dt: dt.datetime | None = None,
) -> None:
    """Pre-popula la DB con `count` velas frescas para (ticker, TF).

    La última vela tiene `dt = last_dt` (default: ahora ET).
    """
    last_dt = last_dt or dt.datetime.now(ET_TZ)
    candles = [
        {
            "dt": last_dt - dt.timedelta(hours=count - i - 1),
            "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000,
        }
        for i in range(count)
    ]
    async with db_factory() as session:
        await write_candles_batch(
            session, timeframe=tf, ticker=ticker, candles=candles,
        )


async def _make_engine_ctx(db_factory, handler):
    pool = KeyPool([_key()])
    sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
    client = TwelveDataClient(pool, transport=httpx.MockTransport(handler))
    engine = DataEngine(
        pool=pool, client=client,
        session_factory=db_factory, warmup_sizes=sizes,
    )
    return engine, client


# ═══════════════════════════════════════════════════════════════════════════
# Baseline — DB vacía
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmupEmptyDB:
    @pytest.mark.asyncio
    async def test_fetches_all_timeframes(self, db_factory) -> None:
        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            results = await engine.warmup(["QQQ"])
        finally:
            await client.close()
        # 3 TFs x 1 ticker = 3 fetches
        assert handler.call_count == 3
        for tf in (Timeframe.DAILY, Timeframe.H1, Timeframe.M15):
            fr = results["QQQ"][tf]
            assert fr.integrity_ok
            assert fr.used_key_id == "k1"  # fetch real


# ═══════════════════════════════════════════════════════════════════════════
# DB llena + fresco → skip fetch
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmupDBHitAllFresh:
    @pytest.mark.asyncio
    async def test_all_tfs_cached_no_fetch(self, db_factory) -> None:
        # Popular las 3 tablas con 3 velas frescas cada una
        for tf in ("daily", "1h", "15m"):
            await _warm_fresh_candles(db_factory, "QQQ", tf, 3)

        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            results = await engine.warmup(["QQQ"])
        finally:
            await client.close()
        # 0 calls al provider
        assert handler.call_count == 0
        # Pero results tienen contenido (de DB)
        for tf in (Timeframe.DAILY, Timeframe.H1, Timeframe.M15):
            fr = results["QQQ"][tf]
            assert fr.integrity_ok
            assert fr.used_key_id is None  # synthetic: DB hit
            assert len(fr.candles) == 3


# ═══════════════════════════════════════════════════════════════════════════
# DB stale → fetch completo
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmupDBStale:
    @pytest.mark.asyncio
    async def test_daily_stale_triggers_fetch(self, db_factory) -> None:
        # Popular daily con velas de hace 10 días (umbral daily = 7d)
        stale_dt = dt.datetime.now(ET_TZ) - dt.timedelta(days=10)
        await _warm_fresh_candles(db_factory, "QQQ", "daily", 3, last_dt=stale_dt)
        await _warm_fresh_candles(db_factory, "QQQ", "1h", 3)
        await _warm_fresh_candles(db_factory, "QQQ", "15m", 3)

        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            results = await engine.warmup(["QQQ"])
        finally:
            await client.close()
        # Solo daily refetch (1 call)
        assert handler.call_count == 1
        assert results["QQQ"][Timeframe.DAILY].used_key_id == "k1"
        assert results["QQQ"][Timeframe.H1].used_key_id is None
        assert results["QQQ"][Timeframe.M15].used_key_id is None

    @pytest.mark.asyncio
    async def test_15m_stale_threshold(self, db_factory) -> None:
        # 15m stale threshold = 1 día. Pongo velas de hace 2 días → refetch.
        stale = dt.datetime.now(ET_TZ) - dt.timedelta(days=2)
        await _warm_fresh_candles(db_factory, "QQQ", "daily", 3)
        await _warm_fresh_candles(db_factory, "QQQ", "1h", 3)
        await _warm_fresh_candles(db_factory, "QQQ", "15m", 3, last_dt=stale)

        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            await engine.warmup(["QQQ"])
        finally:
            await client.close()
        assert handler.call_count == 1  # solo 15m


# ═══════════════════════════════════════════════════════════════════════════
# DB incompleta (<N velas) → fetch
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmupDBIncomplete:
    @pytest.mark.asyncio
    async def test_less_than_n_candles_fetches(self, db_factory) -> None:
        # DB tiene 2 velas pero warmup_size=3 → fetch
        await _warm_fresh_candles(db_factory, "QQQ", "daily", 2)
        await _warm_fresh_candles(db_factory, "QQQ", "1h", 3)
        await _warm_fresh_candles(db_factory, "QQQ", "15m", 3)

        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            await engine.warmup(["QQQ"])
        finally:
            await client.close()
        # Solo daily refetch (tenía menos de N)
        assert handler.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# Mix: 2 tickers, uno cached otro vacío
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmupMultiTicker:
    @pytest.mark.asyncio
    async def test_cached_and_empty_coexist(self, db_factory) -> None:
        # QQQ: DB llena + fresca en los 3 TFs
        for tf in ("daily", "1h", "15m"):
            await _warm_fresh_candles(db_factory, "QQQ", tf, 3)
        # SPY: DB vacía → todas fetchean

        handler = _CountingHandler()
        engine, client = await _make_engine_ctx(db_factory, handler)
        try:
            results = await engine.warmup(["QQQ", "SPY"])
        finally:
            await client.close()
        # QQQ: 0 fetches. SPY: 3 fetches (daily, 1h, 15m).
        assert handler.call_count == 3
        for tf in (Timeframe.DAILY, Timeframe.H1, Timeframe.M15):
            assert results["QQQ"][tf].used_key_id is None
            assert results["SPY"][tf].used_key_id == "k1"
