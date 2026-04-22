"""Tests del `SlotFailureTracker` + retry + DEGRADED escalado (C.2).

Cubre ADR-0004:
- Nivel 1: retry corto 1s en `fetch_for_scan`.
- Nivel 2: skip del ciclo + incrementa contador.
- Nivel 3: umbral 3 → DEGRADED + ENG-060.
- Recovery: success resetea contador; si venía degraded, active.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import httpx
import pytest
import pytest_asyncio

from api.broadcaster import Broadcaster
from api.events import EVENT_SLOT_STATUS
from engines.data import DataEngine, KeyPool, TwelveDataClient
from engines.data.constants import ENG_060, ENG_060_CYCLES_THRESHOLD
from engines.data.models import ApiKeyConfig, Timeframe
from engines.data.scan_loop import SlotFailureTracker, auto_scan_loop
from modules.db import (
    default_url,
    init_db,
    make_engine,
    make_session_factory,
)

# ═══════════════════════════════════════════════════════════════════════════
# SlotFailureTracker — unit tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTracker:
    def test_first_failure_not_degraded(self) -> None:
        t = SlotFailureTracker()
        count, went = t.register_failure(1)
        assert count == 1
        assert went is False
        assert t.is_degraded(1) is False

    def test_crosses_threshold_goes_degraded(self) -> None:
        t = SlotFailureTracker()
        for _ in range(ENG_060_CYCLES_THRESHOLD - 1):
            _, went = t.register_failure(1)
            assert went is False
        count, went = t.register_failure(1)
        assert count == ENG_060_CYCLES_THRESHOLD
        assert went is True
        assert t.is_degraded(1)

    def test_degraded_only_fires_once(self) -> None:
        t = SlotFailureTracker()
        for _ in range(ENG_060_CYCLES_THRESHOLD + 2):
            t.register_failure(1)
        # `went_degraded` solo fue True la vez que cruzó el umbral.
        assert t.is_degraded(1)

    def test_success_resets_and_returns_was_degraded(self) -> None:
        t = SlotFailureTracker()
        for _ in range(ENG_060_CYCLES_THRESHOLD):
            t.register_failure(1)
        assert t.is_degraded(1)
        was_degraded = t.register_success(1)
        assert was_degraded is True
        assert not t.is_degraded(1)
        assert t.failure_count(1) == 0

    def test_success_on_non_degraded_returns_false(self) -> None:
        t = SlotFailureTracker()
        t.register_failure(1)
        was_degraded = t.register_success(1)
        assert was_degraded is False

    def test_slots_tracked_independently(self) -> None:
        t = SlotFailureTracker()
        t.register_failure(1)
        t.register_failure(1)
        t.register_failure(2)
        assert t.failure_count(1) == 2
        assert t.failure_count(2) == 1


# ═══════════════════════════════════════════════════════════════════════════
# Retry nivel 1 en DataEngine.fetch_for_scan
# ═══════════════════════════════════════════════════════════════════════════


def _sample_values(n: int) -> list[dict]:
    return [
        {
            "datetime": f"2025-01-{i + 1:02d}",
            "open": "100.0", "high": "101.0", "low": "99.0",
            "close": "100.5", "volume": "1000",
        }
        for i in range(n)
    ]


class _FlakyHandler:
    """Handler que falla las primeras N llamadas y luego devuelve OK."""

    def __init__(self, fail_first_n: int) -> None:
        self.remaining = fail_first_n
        self.call_count = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if self.remaining > 0:
            self.remaining -= 1
            # Devolver values vacío → integrity falla
            return httpx.Response(
                200,
                json={
                    "meta": {"symbol": "QQQ", "interval": "1day"},
                    "values": [], "status": "ok",
                },
            )
        interval = request.url.params.get("interval")
        outputsize = int(request.url.params.get("outputsize") or 3)
        return httpx.Response(
            200,
            json={
                "meta": {"symbol": "QQQ", "interval": interval},
                "values": _sample_values(outputsize),
                "status": "ok",
            },
        )


def _key() -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id="k1", secret="s-k1",
        credits_per_minute=8, credits_per_day=800,
    )


@pytest_asyncio.fixture
async def db_factory():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    yield factory
    await engine.dispose()


class TestRetry:
    @pytest.mark.asyncio
    async def test_retry_recovers_transient_failure(
        self, db_factory, monkeypatch,
    ) -> None:
        """1er intento falla → retry 1s → 2do OK → retorna data."""
        # Patchear RETRY_SHORT_DELAY_S para no esperar 1s real
        monkeypatch.setattr(
            "engines.data.engine.RETRY_SHORT_DELAY_S", 0.01,
        )

        handler = _FlakyHandler(fail_first_n=4)  # 4 calls del 1er intento
        pool = KeyPool([_key()])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        async with TwelveDataClient(
            pool, transport=httpx.MockTransport(handler),
        ) as client:
            de = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            result = await de.fetch_for_scan("QQQ")
        assert result is not None
        # 4 calls del 1er intento fallido + 4 del retry exitoso = 8
        assert handler.call_count == 8

    @pytest.mark.asyncio
    async def test_retry_failing_still_returns_none(
        self, db_factory, monkeypatch,
    ) -> None:
        """Ambos intentos fallan → retorna None."""
        monkeypatch.setattr(
            "engines.data.engine.RETRY_SHORT_DELAY_S", 0.01,
        )

        handler = _FlakyHandler(fail_first_n=100)
        pool = KeyPool([_key()])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        async with TwelveDataClient(
            pool, transport=httpx.MockTransport(handler),
        ) as client:
            de = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            result = await de.fetch_for_scan("QQQ")
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# DEGRADED + slot.status broadcast
# ═══════════════════════════════════════════════════════════════════════════


class RecordingWS:
    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, data: Any) -> None:
        self.received.append(data)


class TestScanLoopDegraded:
    @pytest.mark.asyncio
    async def test_degraded_broadcast_after_threshold(
        self, db_factory, monkeypatch,
    ) -> None:
        """3 ciclos fallidos → 1 envelope slot.status DEGRADED con ENG-060."""
        monkeypatch.setattr(
            "engines.data.engine.RETRY_SHORT_DELAY_S", 0.001,
        )
        # Handler que falla SIEMPRE (ambos intentos)
        handler = _FlakyHandler(fail_first_n=1_000_000)
        pool = KeyPool([_key()])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        broadcaster = Broadcaster()
        ws = RecordingWS()
        await broadcaster.register(ws)
        # Pre-carga 2 fallos → el primer ciclo del loop cruza el umbral
        tracker = SlotFailureTracker()
        tracker.register_failure(1)
        tracker.register_failure(1)

        async with TwelveDataClient(
            pool, transport=httpx.MockTransport(handler),
        ) as client:
            de = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            task = asyncio.create_task(
                auto_scan_loop(
                    data_engine=de,
                    session_factory=db_factory,
                    broadcaster=broadcaster,
                    slot_tickers=["QQQ"],
                    fixture={},  # no se usa — scan nunca llega
                    test_interval_s=0.01,
                    tracker=tracker,
                ),
            )
            # Un ciclo más el retry ≈ 20-50ms, con margen
            await asyncio.sleep(0.3)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Al menos 1 envelope slot.status con degraded + ENG-060
        degraded = [
            e for e in ws.received
            if e["event"] == EVENT_SLOT_STATUS
            and e["payload"].get("status") == "degraded"
            and e["payload"].get("error_code") == ENG_060
        ]
        assert len(degraded) >= 1
        assert degraded[0]["payload"]["slot_id"] == 1
        assert tracker.is_degraded(1)

    @pytest.mark.asyncio
    async def test_recovery_broadcasts_active(
        self, db_factory,
    ) -> None:
        """Un slot degraded que recupera emite slot.status active."""
        # Setup: tracker pre-degraded, handler OK
        tracker = SlotFailureTracker()
        for _ in range(ENG_060_CYCLES_THRESHOLD):
            tracker.register_failure(1)
        assert tracker.is_degraded(1)

        handler = _FlakyHandler(fail_first_n=0)  # siempre OK
        pool = KeyPool([_key()])
        sizes = {Timeframe.DAILY: 3, Timeframe.H1: 3, Timeframe.M15: 3}
        broadcaster = Broadcaster()
        ws = RecordingWS()
        await broadcaster.register(ws)

        async with TwelveDataClient(
            pool, transport=httpx.MockTransport(handler),
        ) as client:
            de = DataEngine(
                pool=pool, client=client,
                session_factory=db_factory, warmup_sizes=sizes,
            )
            task = asyncio.create_task(
                auto_scan_loop(
                    data_engine=de,
                    session_factory=db_factory,
                    broadcaster=broadcaster,
                    slot_tickers=["QQQ"],
                    fixture=_valid_fixture(),
                    test_interval_s=0.02,
                    tracker=tracker,
                ),
            )
            await asyncio.sleep(0.2)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        active_events = [
            e for e in ws.received
            if e["event"] == EVENT_SLOT_STATUS
            and e["payload"].get("status") == "active"
        ]
        assert len(active_events) >= 1
        assert active_events[0]["payload"]["slot_id"] == 1
        assert "recovered" in active_events[0]["payload"]["message"]
        assert not tracker.is_degraded(1)


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
