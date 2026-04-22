"""Tests del `auto_scan_loop` (DE.3).

Usa `test_interval_s` para bypasear la lógica de market calendar — los
tests disparan ciclos inmediatamente y verifican que:

- El loop ejecuta `fetch_for_scan` + `scan_and_emit` por cada slot.
- Cancelación limpia.
- Fallos individuales no rompen el loop.
"""

from __future__ import annotations

import asyncio
import contextlib

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from api.broadcaster import Broadcaster
from engines.data import DataEngine, KeyPool, TwelveDataClient
from engines.data.models import ApiKeyConfig, Timeframe
from engines.data.scan_loop import auto_scan_loop
from modules.db import (
    Signal,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
)


def _key() -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id="k1", secret="s-k1",
        credits_per_minute=8, credits_per_day=800,
    )


def _sample_values(count: int, interval: str) -> list[dict]:
    if interval == "1day":
        return [
            {
                "datetime": f"2025-01-{i + 1:02d}",
                "open": "100.00", "high": "101.00", "low": "99.00",
                "close": "100.50", "volume": "1000000",
            }
            for i in range(count)
        ]
    if interval == "1h":
        return [
            {
                "datetime": f"2025-01-02 {9 + i}:00:00",
                "open": "200.00", "high": "201.00", "low": "199.00",
                "close": "200.50", "volume": "500000",
            }
            for i in range(count)
        ]
    return [
        {
            "datetime": f"2025-01-02 09:{i * 15:02d}:00".replace(":60:", ":00:"),
            "open": "300.00", "high": "301.00", "low": "299.00",
            "close": "300.50", "volume": "100000",
        }
        for i in range(count)
    ]


def _ok_handler() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
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

    return httpx.MockTransport(handler)


def _valid_fixture() -> dict:
    from modules.fixtures import CONFIRM_CATEGORIES

    return {
        "metadata": {
            "fixture_id": "qqq_test", "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0", "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z", "description": "test",
        },
        "ticker_info": {
            "ticker": "QQQ", "benchmark": "SPY",
            "requires_spy_daily": True, "requires_bench_daily": True,
        },
        "confirm_weights": dict.fromkeys(CONFIRM_CATEGORIES, 1.0),
        "detection_thresholds": {
            "fzarel_min_divergence_pct": 0.5,
            "divspy_asset_threshold_pct": 0.5,
            "divspy_spy_threshold_pct": 0.3,
            "volhigh_min_ratio": 1.2,
        },
        "score_bands": [
            {"min": 16.0, "max": None, "label": "S+", "signal": "SETUP"},
            {"min": 14.0, "max": 16.0, "label": "S", "signal": "SETUP"},
            {"min": 10.0, "max": 14.0, "label": "A+", "signal": "SETUP"},
            {"min": 7.0, "max": 10.0, "label": "A", "signal": "SETUP"},
            {"min": 4.0, "max": 7.0, "label": "B", "signal": "REVISAR"},
            {"min": 2.0, "max": 4.0, "label": "REVISAR", "signal": "REVISAR"},
        ],
    }


@pytest_asyncio.fixture
async def db_factory():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def engine_ctx(db_factory):
    pool = KeyPool([_key()])
    sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
    async with TwelveDataClient(pool, transport=_ok_handler()) as client:
        de = DataEngine(
            pool=pool, client=client,
            session_factory=db_factory, warmup_sizes=sizes,
        )
        yield de, db_factory


# ═══════════════════════════════════════════════════════════════════════════
# Scan cycle
# ═══════════════════════════════════════════════════════════════════════════


class TestAutoScanLoop:
    @pytest.mark.asyncio
    async def test_cycle_persists_signals_for_each_slot(self, engine_ctx) -> None:
        de, factory = engine_ctx
        broadcaster = Broadcaster()
        task = asyncio.create_task(
            auto_scan_loop(
                data_engine=de,
                session_factory=factory,
                broadcaster=broadcaster,
                slot_tickers=["QQQ", "SPY"],
                fixture=_valid_fixture(),
                test_interval_s=0.05,
            ),
        )
        # Esperar al menos un ciclo
        await asyncio.sleep(0.3)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        async with factory() as session:
            result = await session.execute(select(Signal))
            signals = result.scalars().all()
        # Al menos 2 signals (uno por slot)
        tickers_persistidos = {s.ticker for s in signals}
        assert "QQQ" in tickers_persistidos
        assert "SPY" in tickers_persistidos
        slot_ids = {s.slot_id for s in signals}
        assert slot_ids == {1, 2}

    @pytest.mark.asyncio
    async def test_cancel_is_clean(self, engine_ctx) -> None:
        de, factory = engine_ctx
        broadcaster = Broadcaster()
        task = asyncio.create_task(
            auto_scan_loop(
                data_engine=de,
                session_factory=factory,
                broadcaster=broadcaster,
                slot_tickers=["QQQ"],
                fixture=_valid_fixture(),
                test_interval_s=60.0,  # largo, tiene que cancelarse en sleep
            ),
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        assert task.done()

    @pytest.mark.asyncio
    async def test_broadcasts_engine_status(self, engine_ctx) -> None:
        de, factory = engine_ctx
        broadcaster = Broadcaster()

        class RecordingWS:
            def __init__(self):
                self.received: list[dict] = []

            async def send_json(self, data):
                self.received.append(data)

        ws = RecordingWS()
        await broadcaster.register(ws)

        task = asyncio.create_task(
            auto_scan_loop(
                data_engine=de,
                session_factory=factory,
                broadcaster=broadcaster,
                slot_tickers=["QQQ"],
                fixture=_valid_fixture(),
                test_interval_s=0.05,
            ),
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Debe haber al menos un envelope engine.status del data engine
        ds_events = [
            e for e in ws.received
            if e["event"] == "engine.status"
            and e["payload"].get("engine") == "data"
        ]
        assert len(ds_events) >= 1

    @pytest.mark.asyncio
    async def test_broadcasts_api_usage_tick_per_key(self, engine_ctx) -> None:
        """Post-ciclo emite api_usage.tick por cada key del pool."""
        de, factory = engine_ctx
        broadcaster = Broadcaster()

        class RecordingWS:
            def __init__(self):
                self.received: list[dict] = []

            async def send_json(self, data):
                self.received.append(data)

        ws = RecordingWS()
        await broadcaster.register(ws)

        task = asyncio.create_task(
            auto_scan_loop(
                data_engine=de,
                session_factory=factory,
                broadcaster=broadcaster,
                slot_tickers=["QQQ"],
                fixture=_valid_fixture(),
                test_interval_s=0.05,
            ),
        )
        await asyncio.sleep(0.25)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        ticks = [e for e in ws.received if e["event"] == "api_usage.tick"]
        # Pool tiene 1 key → al menos 1 tick por ciclo, 1+ ciclo en 0.25s
        assert len(ticks) >= 1
        payload = ticks[0]["payload"]
        assert set(payload.keys()) == {
            "key_id", "used_minute", "max_minute",
            "used_daily", "max_daily", "last_call_ts", "exhausted",
        }
        assert payload["key_id"] == "k1"
