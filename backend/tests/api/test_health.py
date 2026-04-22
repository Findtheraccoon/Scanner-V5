"""Tests de FastAPI app + auth Bearer + health endpoint (C5.3)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import init_db


@pytest_asyncio.fixture
async def client_with_auth():
    # auto_init_db=False + init_db manual — AsyncClient no corre lifespan.
    app = create_app(
        valid_api_keys={"sk-test-1", "sk-test-2"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def client_no_auth():
    """App sin keys válidas configuradas — todos los requests dan 401."""
    app = create_app(
        valid_api_keys=None,
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await app.state.db_engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    @pytest.mark.asyncio
    async def test_missing_header_returns_401(self, client_with_auth) -> None:
        r = await client_with_auth.get("/api/v1/engine/health")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-wrong"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_scheme_returns_401(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Basic sk-test-1"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_allows_request(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_any_valid_token_works(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-2"},
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_empty_key_set_all_requests_fail(self, client_no_auth) -> None:
        r = await client_no_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-anything"},
        )
        assert r.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# Health endpoint
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_returns_expected_shape(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        assert r.status_code == 200
        body = r.json()
        required_keys = {
            "status", "engine", "engine_version",
            "memory_pct", "error_code", "ts",
        }
        assert set(body.keys()) == required_keys

    @pytest.mark.asyncio
    async def test_engine_is_scoring(self, client_with_auth) -> None:
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        body = r.json()
        assert body["engine"] == "scoring"

    @pytest.mark.asyncio
    async def test_ts_is_iso_tz_aware(self, client_with_auth) -> None:
        import datetime as dt

        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        ts = dt.datetime.fromisoformat(r.json()["ts"])
        assert ts.tzinfo is not None

    @pytest.mark.asyncio
    async def test_no_heartbeat_returns_offline(self, client_with_auth) -> None:
        """Sin heartbeats, el health endpoint retorna `offline`."""
        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        body = r.json()
        assert body["status"] == "offline"

    @pytest.mark.asyncio
    async def test_reads_latest_heartbeat_status(self, client_with_auth) -> None:
        """Si hay heartbeats, retorna el status del más reciente."""
        from engines.database import emit_engine_heartbeat

        factory = client_with_auth._transport.app.state.session_factory
        await emit_engine_heartbeat(
            factory, engine="scoring", status="yellow", memory_pct=82.3,
        )

        r = await client_with_auth.get(
            "/api/v1/engine/health",
            headers={"Authorization": "Bearer sk-test-1"},
        )
        body = r.json()
        assert body["status"] == "yellow"
        assert body["memory_pct"] == 82.3


# ═══════════════════════════════════════════════════════════════════════════
# OpenAPI / FastAPI hygiene
# ═══════════════════════════════════════════════════════════════════════════


class TestOpenApi:
    @pytest.mark.asyncio
    async def test_openapi_schema_public(self, client_with_auth) -> None:
        """OpenAPI doc no requiere auth (default FastAPI)."""
        r = await client_with_auth.get("/openapi.json")
        assert r.status_code == 200
        schema = r.json()
        assert schema["info"]["title"] == "Scanner V5 Backend"

    @pytest.mark.asyncio
    async def test_docs_accessible(self, client_with_auth) -> None:
        r = await client_with_auth.get("/docs")
        assert r.status_code == 200
