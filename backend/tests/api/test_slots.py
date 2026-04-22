"""Tests de endpoints REST de slots (SR.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

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
    async def test_enable_requires_ticker_and_fixture(
        self, app_with_registry,
    ) -> None:
        """enable=True sin ticker + fixture → 400 con mensaje claro."""
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
        assert "ticker" in r.text.lower()

    @pytest.mark.asyncio
    async def test_enable_requires_data_engine(
        self, app_with_registry,
    ) -> None:
        """Sin `app.state.data_engine`, enable devuelve 503."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_registry),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={
                    "enabled": True,
                    "ticker": "QQQ",
                    "fixture": "fixtures/qqq.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
        assert r.status_code == 503

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


class TestPatchSlotPersistence:
    """Verifica que el PATCH disable persiste al `slot_registry.json`."""

    @pytest.mark.asyncio
    async def test_disable_persists_to_disk(self, tmp_path: Path) -> None:
        from httpx import ASGITransport, AsyncClient

        registry_path = tmp_path / "slot_registry.json"
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        # Runtime con path → escritura real al disco
        base_rt = _make_registry()
        app.state.registry_runtime = RegistryRuntime(
            base_rt._registry,
            registry_path=registry_path,
        )

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                r = await client.patch(
                    "/api/v1/slots/1",
                    json={"enabled": False},
                    headers=AUTH,
                )
            assert r.status_code == 200

            # El archivo fue creado y refleja el cambio
            assert registry_path.is_file()
            data = json.loads(registry_path.read_text())
            slot1 = next(s for s in data["slots"] if s["slot"] == 1)
            slot2 = next(s for s in data["slots"] if s["slot"] == 2)
            assert slot1["enabled"] is False
            assert slot2["enabled"] is True  # no se tocó
        finally:
            await app.state.db_engine.dispose()


class TestPatchTriggersRevalidation:
    """Tras un PATCH exitoso, se spawnea `run_slot_revalidation` si hay
    un Validator en app.state."""

    @pytest_asyncio.fixture
    async def app_with_validator(self, tmp_path):
        """App con registry real en disco + Validator real."""
        from engines.scoring import ENGINE_VERSION
        from modules.slot_registry import load_registry
        from modules.validator import Validator
        from tests.modules.slot_registry.test_loader import _write_registry

        registry_path = _write_registry(tmp_path)
        registry = load_registry(registry_path, engine_version=ENGINE_VERSION)
        runtime = RegistryRuntime(registry, registry_path=registry_path)

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        app.state.registry_runtime = runtime
        app.state.validator = Validator(
            session_factory=app.state.session_factory,
            broadcaster=app.state.broadcaster,
            log_dir=tmp_path,
            registry=runtime,
            registry_path=registry_path,
            parity_enabled=False,
        )
        yield app
        await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_disable_spawns_revalidation(
        self, app_with_validator,
    ) -> None:
        """El PATCH disable dispara A→B→C en background y guarda reporte."""
        import asyncio

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={"enabled": False},
                headers=AUTH,
            )
            assert r.status_code == 200
            # Esperar el task de revalidation
            tasks = list(
                getattr(app_with_validator.state, "revalidation_tasks", []),
            )
            await asyncio.gather(*tasks)

        # El reporte se guardó
        report = app_with_validator.state.last_validator_report
        assert [t.test_id for t in report.tests] == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_patch_without_validator_does_not_crash(
        self, app_with_registry,
    ) -> None:
        """Sin validator en app.state, el PATCH sigue funcionando."""
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


class TestPatchSlotEnable:
    """Tests del flujo enable=true (hot-reload con warmup)."""

    @staticmethod
    def _write_fixture_tree(root: Path) -> Path:
        """Crea fixtures/qqq.json + slot_registry.json bajo `root`.

        Slot 1 disabled (para re-habilitarlo), resto disabled.
        """
        import json

        from tests.modules.slot_registry.test_loader import _fixture_dict

        fixtures_dir = root / "fixtures"
        fixtures_dir.mkdir()
        (fixtures_dir / "qqq.json").write_text(
            json.dumps(_fixture_dict(canonical_ref=None)),
        )

        registry_data = {
            "registry_metadata": {
                "registry_version": "1.0.0",
                "engine_version_required": ">=5.2.0,<6.0.0",
                "generated_at": "2025-03-10T00:00:00Z",
            },
            "slots": [
                {"slot": i, "ticker": None, "fixture": None,
                 "benchmark": None, "enabled": False}
                for i in range(1, 7)
            ],
        }
        path = root / "slot_registry.json"
        path.write_text(json.dumps(registry_data))
        return path

    @pytest_asyncio.fixture
    async def app_enable_ready(self, tmp_path):
        """App con registry real en disco + DataEngine mock."""
        from unittest.mock import AsyncMock

        from engines.scoring import ENGINE_VERSION
        from modules.slot_registry import load_registry

        registry_path = self._write_fixture_tree(tmp_path)
        registry = load_registry(registry_path, engine_version=ENGINE_VERSION)

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        app.state.registry_runtime = RegistryRuntime(
            registry, registry_path=registry_path,
        )
        # Mock del DataEngine — solo necesita un `warmup` async.
        app.state.data_engine = AsyncMock()
        app.state.data_engine.warmup = AsyncMock(return_value={})
        yield app
        await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_enable_returns_warming_up(self, app_enable_ready) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_enable_ready),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={
                    "enabled": True,
                    "ticker": "QQQ",
                    "fixture": "fixtures/qqq.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
        assert r.status_code == 200
        slot = r.json()
        assert slot["status"] == "warming_up"
        assert slot["ticker"] == "QQQ"
        assert slot["base_state"] == "OPERATIVE"

    @pytest.mark.asyncio
    async def test_enable_persists_to_registry_file(
        self, app_enable_ready,
    ) -> None:
        import json

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_enable_ready),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/2",
                json={
                    "enabled": True,
                    "ticker": "QQQ",
                    "fixture": "fixtures/qqq.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
        assert r.status_code == 200

        registry_path = (
            app_enable_ready.state.registry_runtime._registry_path
        )
        data = json.loads(registry_path.read_text())
        slot2 = next(s for s in data["slots"] if s["slot"] == 2)
        assert slot2["enabled"] is True
        assert slot2["ticker"] == "QQQ"

    @pytest.mark.asyncio
    async def test_enable_rejects_ticker_mismatch(
        self, app_enable_ready,
    ) -> None:
        """fixture declara QQQ; si el body pide SPY → 400 REG-012."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_enable_ready),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={
                    "enabled": True,
                    "ticker": "SPY",
                    "fixture": "fixtures/qqq.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
        assert r.status_code == 400
        body = r.json()
        assert body["detail"]["error_code"] == "REG-012"

    @pytest.mark.asyncio
    async def test_enable_rejects_missing_fixture(
        self, app_enable_ready,
    ) -> None:
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_enable_ready),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={
                    "enabled": True,
                    "ticker": "QQQ",
                    "fixture": "fixtures/ghost.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
        assert r.status_code == 400
        body = r.json()
        assert body["detail"]["error_code"] == "FIX-000"

    @pytest.mark.asyncio
    async def test_enable_calls_warmup_in_background(
        self, app_enable_ready,
    ) -> None:
        """Tras el enable, el DataEngine.warmup fue invocado con el ticker."""
        import asyncio

        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=app_enable_ready),
            base_url="http://test",
        ) as client:
            r = await client.patch(
                "/api/v1/slots/1",
                json={
                    "enabled": True,
                    "ticker": "QQQ",
                    "fixture": "fixtures/qqq.json",
                    "benchmark": "SPY",
                },
                headers=AUTH,
            )
            assert r.status_code == 200
            # Esperar a que termine el background task
            tasks = list(app_enable_ready.state.warmup_tasks)
            await asyncio.gather(*tasks)

        app_enable_ready.state.data_engine.warmup.assert_awaited_once_with(
            ["QQQ"],
        )
        # Post-warmup: slot es active
        slot = await app_enable_ready.state.registry_runtime.get_slot(1)
        assert slot["status"] == "active"


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
