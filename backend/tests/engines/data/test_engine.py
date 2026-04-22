"""Tests del `DataEngine` orquestrador (DE.2).

Usa `httpx.MockTransport` para simular el provider sin HTTP real.
Verifica:

- `warmup(tickers)` fetch paralelo + persistencia en DB.
- `fetch_for_scan(ticker)` con los 3 TFs + SPY, integrity gate.
- Integrity failure → `fetch_for_scan` retorna `None`.
- Persistencia en `candles_{daily,1h,15m}` queda correcta.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from engines.data import DataEngine, KeyPool, TwelveDataClient
from engines.data.models import ApiKeyConfig, Timeframe
from modules.db import (
    CandleDaily,
    CandleH1,
    CandleM15,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
)


def _key(key_id: str = "k1") -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id=key_id,
        secret=f"s-{key_id}",
        credits_per_minute=8,
        credits_per_day=800,
    )


def _sample_values(count: int, tf: str) -> list[dict]:
    """Valores simulados del formato TwelveData."""
    if tf == "1day":
        return [
            {
                "datetime": f"2025-01-{i + 1:02d}",
                "open": f"{100 + i}.00",
                "high": f"{101 + i}.00",
                "low": f"{99 + i}.00",
                "close": f"{100 + i}.50",
                "volume": f"{1_000_000 + i * 100}",
            }
            for i in range(count)
        ]
    if tf == "1h":
        return [
            {
                "datetime": f"2025-01-02 {9 + i}:00:00",
                "open": f"{200 + i}.00",
                "high": f"{201 + i}.00",
                "low": f"{199 + i}.00",
                "close": f"{200 + i}.50",
                "volume": f"{500_000 + i * 50}",
            }
            for i in range(count)
        ]
    # 15min
    return [
        {
            "datetime": f"2025-01-02 09:{i * 15:02d}:00".replace(":60:", ":00:"),
            "open": f"{300 + i}.00",
            "high": f"{301 + i}.00",
            "low": f"{299 + i}.00",
            "close": f"{300 + i}.50",
            "volume": f"{100_000 + i * 10}",
        }
        for i in range(count)
    ]


def _ok_handler(integrity_fails_for: str | None = None) -> httpx.MockTransport:
    """Handler MockTransport que devuelve candles válidos para cualquier request.

    Si `integrity_fails_for` es un interval ("1day"/"1h"/"15min"),
    responde con `values` vacío para simular integrity failure.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        interval = request.url.params.get("interval")
        outputsize = int(request.url.params.get("outputsize") or 3)
        if integrity_fails_for == interval:
            # integrity gate espera al menos algunas velas
            return httpx.Response(
                200,
                json={
                    "meta": {"symbol": "QQQ", "interval": interval},
                    "values": [],
                    "status": "ok",
                },
            )
        return httpx.Response(
            200,
            json={
                "meta": {"symbol": "QQQ", "interval": interval},
                "values": _sample_values(outputsize, interval),
                "status": "ok",
            },
        )

    return httpx.MockTransport(handler)


@pytest_asyncio.fixture
async def db_factory():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def data_engine(db_factory):
    pool = KeyPool([_key("k1"), _key("k2")])
    # Small warmup sizes for speed
    sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
    async with TwelveDataClient(pool, transport=_ok_handler()) as client:
        engine = DataEngine(
            pool=pool,
            client=client,
            session_factory=db_factory,
            warmup_sizes=sizes,
        )
        yield engine, db_factory


# ═══════════════════════════════════════════════════════════════════════════
# warmup
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmup:
    @pytest.mark.asyncio
    async def test_returns_results_per_ticker_and_tf(self, data_engine) -> None:
        engine, _ = data_engine
        results = await engine.warmup(["QQQ", "SPY"])
        assert set(results.keys()) == {"QQQ", "SPY"}
        for ticker in ("QQQ", "SPY"):
            assert set(results[ticker].keys()) == {
                Timeframe.DAILY, Timeframe.H1, Timeframe.M15,
            }
            assert all(r.integrity_ok for r in results[ticker].values())

    @pytest.mark.asyncio
    async def test_persists_candles_in_db(self, data_engine) -> None:
        engine, factory = data_engine
        await engine.warmup(["QQQ"])
        # Verificar que las 3 tablas tienen filas para QQQ
        async with factory() as session:
            for model in (CandleDaily, CandleH1, CandleM15):
                result = await session.execute(
                    select(model).where(model.ticker == "QQQ"),
                )
                rows = result.scalars().all()
                assert len(rows) >= 1

    @pytest.mark.asyncio
    async def test_single_ticker(self, data_engine) -> None:
        engine, _ = data_engine
        results = await engine.warmup(["QQQ"])
        assert list(results.keys()) == ["QQQ"]


# ═══════════════════════════════════════════════════════════════════════════
# fetch_for_scan — happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchForScan:
    @pytest.mark.asyncio
    async def test_returns_dict_with_all_timeframes(self, data_engine) -> None:
        engine, _ = data_engine
        result = await engine.fetch_for_scan("QQQ")
        assert result is not None
        assert set(result.keys()) == {
            "candles_daily", "candles_1h", "candles_15m",
            "spy_daily", "fetched_at",
        }
        for tf in ("candles_daily", "candles_1h", "candles_15m"):
            assert len(result[tf]) >= 1
            first = result[tf][0]
            assert set(first.keys()) == {"dt", "o", "h", "l", "c", "v"}
            # dt es string sin tz (formato del scoring engine)
            assert isinstance(first["dt"], str)
            assert "T" not in first["dt"]  # "YYYY-MM-DD HH:MM:SS" sin T

    @pytest.mark.asyncio
    async def test_includes_spy_by_default(self, data_engine) -> None:
        engine, _ = data_engine
        result = await engine.fetch_for_scan("QQQ")
        assert result["spy_daily"] is not None
        assert len(result["spy_daily"]) >= 1

    @pytest.mark.asyncio
    async def test_skip_spy_when_disabled(self, data_engine) -> None:
        engine, _ = data_engine
        result = await engine.fetch_for_scan("QQQ", include_spy=False)
        assert result["spy_daily"] is None

    @pytest.mark.asyncio
    async def test_persists_to_db(self, data_engine) -> None:
        engine, factory = data_engine
        await engine.fetch_for_scan("QQQ")
        async with factory() as session:
            result = await session.execute(
                select(CandleDaily).where(CandleDaily.ticker == "QQQ"),
            )
            assert len(result.scalars().all()) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# fetch_for_scan — integrity gate
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchForScanIntegrityGate:
    @pytest.mark.asyncio
    async def test_daily_failure_returns_none(self, db_factory) -> None:
        """Si daily falla integrity, retorna None sin persistir nada."""
        pool = KeyPool([_key("k1")])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        async with TwelveDataClient(
            pool, transport=_ok_handler(integrity_fails_for="1day"),
        ) as client:
            engine = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            result = await engine.fetch_for_scan("QQQ")
        assert result is None

        # Nada persistido (ni el 1H/15m que SI estaban OK — gate temprano)
        async with db_factory() as session:
            daily = await session.execute(select(CandleDaily))
            assert len(daily.scalars().all()) == 0

    @pytest.mark.asyncio
    async def test_15m_failure_returns_none(self, db_factory) -> None:
        pool = KeyPool([_key("k1")])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        async with TwelveDataClient(
            pool, transport=_ok_handler(integrity_fails_for="15min"),
        ) as client:
            engine = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            result = await engine.fetch_for_scan("QQQ")
        assert result is None
