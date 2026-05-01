"""Tests de `POST /api/v1/scan/manual` (D.2)."""

from __future__ import annotations

import datetime as dt
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY
from modules.db import ET_TZ, init_db

AUTH = {"Authorization": "Bearer sk-test"}


def _monotonic_candles(n: int, start: float = 500.0) -> list[dict]:
    return [
        {
            "dt": f"2025-01-{(i % 28) + 1:02d} 10:00:00",
            "o": start + i * 0.1, "h": start + i * 0.1 + 1.0,
            "l": start + i * 0.1 - 1.0, "c": start + i * 0.1 + 0.5,
            "v": 1_000_000 + i,
        }
        for i in range(n)
    ]


def _valid_fixture_dict() -> dict:
    from modules.fixtures import CONFIRM_CATEGORIES

    return {
        "metadata": {
            "fixture_id": "qqq_test",
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "test fixture",
        },
        "ticker_info": {
            "ticker": "QQQ",
            "benchmark": "SPY",
            "requires_spy_daily": True,
            "requires_bench_daily": True,
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


def _valid_body(**overrides) -> dict:
    body = {
        "ticker": "QQQ",
        "slot_id": 1,
        "fixture": _valid_fixture_dict(),
        "candles_daily": _monotonic_candles(MIN_CANDLES_DAILY),
        "candles_1h": _monotonic_candles(MIN_CANDLES_1H),
        "candles_15m": _monotonic_candles(MIN_CANDLES_15M),
        "spy_daily": _monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        "bench_daily": _monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        "candle_timestamp": dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ).isoformat(),
    }
    body.update(overrides)
    return body


@pytest_asyncio.fixture
async def client():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await app.state.db_engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════


class TestScanManualAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client) -> None:
        r = await client.post("/api/v1/scan/manual", json=_valid_body())
        assert r.status_code == 401


class TestScanSlotBug015:
    """BUG-015: nuevo endpoint POST /scan/slot/{slot_id} que reemplaza
    al botón scan del Cockpit. El frontend antes pegaba /scan/manual con
    body vacío y siempre fallaba 422.
    """

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client) -> None:
        r = await client.post("/api/v1/scan/slot/1")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_no_registry_runtime_returns_503(self, client) -> None:
        # El client del fixture no inyecta registry_runtime → 503 limpio.
        r = await client.post("/api/v1/scan/slot/1", headers=AUTH)
        assert r.status_code == 503
        assert "registry runtime" in r.json()["detail"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestScanManualValidation:
    @pytest.mark.asyncio
    async def test_missing_ticker_422(self, client) -> None:
        body = _valid_body()
        del body["ticker"]
        r = await client.post("/api/v1/scan/manual", json=body, headers=AUTH)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_extra_field_rejected_422(self, client) -> None:
        """`extra="forbid"` en el Pydantic schema."""
        body = _valid_body()
        body["unknown_field"] = 42
        r = await client.post("/api/v1/scan/manual", json=body, headers=AUTH)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_slot_id_zero_rejected(self, client) -> None:
        r = await client.post(
            "/api/v1/scan/manual",
            json=_valid_body(slot_id=0),
            headers=AUTH,
        )
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# Happy path — NEUTRAL (sin triggers)
# ═══════════════════════════════════════════════════════════════════════════


class TestScanManualNeutralPath:
    @pytest.mark.asyncio
    async def test_returns_output_with_id(self, client) -> None:
        r = await client.post(
            "/api/v1/scan/manual", json=_valid_body(), headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert body["ticker"] == "QQQ"
        # Serie monotónica sin triggers → signal NEUTRAL
        assert body["signal"] == "NEUTRAL"
        assert body["error"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Happy path — SETUP con monkeypatch de trigger
# ═══════════════════════════════════════════════════════════════════════════


class TestScanManualSetupPath:
    @pytest.mark.asyncio
    async def test_setup_returns_and_persists(
        self, client, monkeypatch,
    ) -> None:
        # Monkeypatch del detector MA cross 1H para emitir trigger sintético
        analyze_mod = sys.modules["engines.scoring.analyze"]
        monkeypatch.setattr(
            analyze_mod, "detect_ma_cross_1h",
            lambda candles: [{
                "tf": "1H", "d": "MA20 cross up (synth)",
                "sg": "CALL", "w": 4.0, "cat": "TRIGGER", "age": 0,
            }],
        )
        r = await client.post(
            "/api/v1/scan/manual", json=_valid_body(), headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        # Trigger peso=4 sin confirms (serie monotónica no dispara nada más)
        # → score=4 → banda B → signal REVISAR.
        assert body["conf"] == "B"
        assert body["signal"] == "REVISAR"
        assert body["dir"] == "CALL"
        # trigger=4 + VolSeq confirm (w=1 del fixture test) = 5.0 → banda B
        assert body["score"] == 5.0
        assert "id" in body


# ═══════════════════════════════════════════════════════════════════════════
# OpenAPI
# ═══════════════════════════════════════════════════════════════════════════


class TestScanManualOpenApi:
    @pytest.mark.asyncio
    async def test_endpoint_documented(self, client) -> None:
        r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/scan/manual" in paths
        assert "post" in paths["/api/v1/scan/manual"]


# ═══════════════════════════════════════════════════════════════════════════
# Auto-scan pause / resume / status (deuda técnica del Cockpit AUTO toggle)
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def client_with_running():
    """App con `app.state.auto_scan_running` precargado (set = corriendo)."""
    import asyncio as _asyncio

    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    running = _asyncio.Event()
    running.set()
    app.state.auto_scan_running = running
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, running
    await app.state.db_engine.dispose()


class TestAutoScanPauseResume:
    @pytest.mark.asyncio
    async def test_status_initial_running(self, client_with_running) -> None:
        c, _running = client_with_running
        r = await c.get("/api/v1/scan/auto/status", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"paused": False}

    @pytest.mark.asyncio
    async def test_pause_then_status(self, client_with_running) -> None:
        c, running = client_with_running
        r = await c.post("/api/v1/scan/auto/pause", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"paused": True}
        assert not running.is_set()
        # status refleja el cambio
        r = await c.get("/api/v1/scan/auto/status", headers=AUTH)
        assert r.json() == {"paused": True}

    @pytest.mark.asyncio
    async def test_resume_clears_pause(self, client_with_running) -> None:
        c, running = client_with_running
        await c.post("/api/v1/scan/auto/pause", headers=AUTH)
        r = await c.post("/api/v1/scan/auto/resume", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"paused": False}
        assert running.is_set()

    @pytest.mark.asyncio
    async def test_pause_idempotent(self, client_with_running) -> None:
        c, running = client_with_running
        for _ in range(3):
            r = await c.post("/api/v1/scan/auto/pause", headers=AUTH)
            assert r.status_code == 200
            assert r.json() == {"paused": True}
        assert not running.is_set()

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client_with_running) -> None:
        c, _running = client_with_running
        r = await c.post("/api/v1/scan/auto/pause")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_503_when_no_running_event(self, client) -> None:
        """Sin `auto_scan_running` en app.state (e.g. arrancado sin keys)."""
        r = await client.post("/api/v1/scan/auto/pause", headers=AUTH)
        assert r.status_code == 503
        r = await client.post("/api/v1/scan/auto/resume", headers=AUTH)
        assert r.status_code == 503
        r = await client.get("/api/v1/scan/auto/status", headers=AUTH)
        assert r.status_code == 503
