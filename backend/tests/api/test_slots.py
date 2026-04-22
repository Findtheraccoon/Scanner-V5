"""Tests de endpoints REST de slots (SR.3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from api import create_app
from api.events import EVENT_SLOT_STATUS
from engines.registry_runtime import RegistryRuntime
from modules.db import init_db
from modules.fixtures import Fixture
from modules.slot_registry import RegistryMetadata, SlotRecord, SlotRegistry

AUTH = {"Authorization": "Bearer sk-test"}


def _fixture_dict() -> dict:
    from modules.fixtures import CONFIRM_CATEGORIES

    return {
        "metadata": {
            "fixture_id": "qqq_test",
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "test",
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
            {"min": 2.0, "max": None, "label": "OK", "signal": "REVISAR"},
        ],
    }


def _make_registry() -> RegistryRuntime:
    metadata = RegistryMetadata(
        registry_version="1.0.0",
        engine_version_required=">=5.2.0,<6.0.0",
        generated_at=datetime(2026, 4, 22, tzinfo=UTC),
        description="test",
    )
    fixture = Fixture.model_validate(_fixture_dict())
    slots = [
        SlotRecord(
            slot=1, status="OPERATIVE", ticker="QQQ",
            fixture_path="fixtures/slot1.json",
            fixture=fixture, benchmark="SPY",
        ),
        SlotRecord(
            slot=2, status="OPERATIVE", ticker="SPY",
            fixture_path="fixtures/slot2.json",
            fixture=fixture, benchmark="SPY",
        ),
    ]
    # Fill 3-6 DISABLED
    for i in range(3, 7):
        slots.append(
            SlotRecord(
                slot=i, status="DISABLED", ticker=None,
                fixture_path=None, fixture=None, benchmark=None,
            ),
        )
    return RegistryRuntime(
        SlotRegistry(metadata=metadata, slots=slots, warnings=[]),
    )


@pytest_asyncio.fixture
async def app_with_registry():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    app.state.registry_runtime = _make_registry()
    yield app
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def app_without_registry():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    # NO se setea `app.state.registry_runtime` — simula backend sin
    # scan loop real (fallback a stub).
    yield app
    await app.state.db_engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════


class TestSlotsAuth:
    @pytest.mark.asyncio
    async def test_list_unauthenticated(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/slots")
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# GET /slots
# ═══════════════════════════════════════════════════════════════════════════


class TestListSlots:
    @pytest.mark.asyncio
    async def test_returns_6_slots(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/slots", headers=AUTH)
        assert r.status_code == 200
        slots = r.json()
        assert len(slots) == 6
        assert slots[0]["slot"] == 1
        assert slots[0]["status"] == "active"
        assert slots[0]["ticker"] == "QQQ"
        assert slots[2]["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_503_without_registry(self, app_without_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_without_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/slots", headers=AUTH)
        assert r.status_code == 503


# ═══════════════════════════════════════════════════════════════════════════
# GET /slots/{id}
# ═══════════════════════════════════════════════════════════════════════════


class TestGetSlot:
    @pytest.mark.asyncio
    async def test_existing_slot(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/slots/1", headers=AUTH)
        assert r.status_code == 200
        slot = r.json()
        assert slot["slot"] == 1
        assert slot["ticker"] == "QQQ"

    @pytest.mark.asyncio
    async def test_nonexistent_slot(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/slots/99", headers=AUTH)
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# PATCH /slots/{id}
# ═══════════════════════════════════════════════════════════════════════════


class TestPatchSlot:
    @pytest.mark.asyncio
    async def test_disable_slot(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={"enabled": False},
                headers=AUTH,
            )
        assert r.status_code == 200
        slot = r.json()
        assert slot["status"] == "disabled"
        assert slot["ticker"] is None

        # El registry runtime refleja el cambio
        tickers = await app_with_registry.state.registry_runtime.list_scannable_tickers()
        # Slot 1 ya NO está en scannable
        assert not any(t[0] == 1 for t in tickers)

    @pytest.mark.asyncio
    async def test_disable_nonexistent_404(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/99",
                json={"enabled": False},
                headers=AUTH,
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_enable_mvp_not_supported(self, app_with_registry) -> None:
        """MVP: `enabled=True` todavía no soportado."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={"enabled": True},
                headers=AUTH,
            )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_extra_field_rejected(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={"unknown_field": 1},
                headers=AUTH,
            )
        assert r.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# WebSocket broadcast de slot.status
# ═══════════════════════════════════════════════════════════════════════════


class TestSlotStatusBroadcast:
    def test_disable_broadcasts_slot_status(self) -> None:
        """El PATCH disable debe emitir `slot.status=disabled` al WS."""
        # Uso TestClient sync para tests WS + request HTTP juntos.
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
        )
        with TestClient(app) as client:
            # Inyectar runtime después del startup (que ya corrió init_db).
            client.app.state.registry_runtime = _make_registry()

            with client.websocket_connect("/ws?token=sk-test") as ws:
                # Ejecutar el PATCH
                r = client.patch(
                    "/api/v1/slots/1",
                    json={"enabled": False},
                    headers=AUTH,
                )
                assert r.status_code == 200

                # Leer del WebSocket
                envelope = ws.receive_json()
                assert envelope["event"] == EVENT_SLOT_STATUS
                assert envelope["payload"]["slot_id"] == 1
                assert envelope["payload"]["status"] == "disabled"


# ═══════════════════════════════════════════════════════════════════════════
# OpenAPI coverage
# ═══════════════════════════════════════════════════════════════════════════


class TestOpenApiCoverage:
    @pytest.mark.asyncio
    async def test_endpoints_documented(self, app_with_registry) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/slots" in paths
        assert "/api/v1/slots/{slot_id}" in paths
        assert "get" in paths["/api/v1/slots/{slot_id}"]
        assert "patch" in paths["/api/v1/slots/{slot_id}"]
