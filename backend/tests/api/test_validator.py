"""Tests de los endpoints REST del Validator (V.6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import init_db
from modules.validator import Validator

AUTH = {"Authorization": "Bearer sk-test"}


@pytest_asyncio.fixture
async def app_with_validator(tmp_path: Path):
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    app.state.validator = Validator(
        session_factory=app.state.session_factory,
        broadcaster=app.state.broadcaster,
        log_dir=tmp_path,
        parity_enabled=False,
    )
    yield app
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def app_without_validator():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    yield app
    await app.state.db_engine.dispose()


class TestAuth:
    @pytest.mark.asyncio
    async def test_run_unauthenticated(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run")
        assert r.status_code == 401


class TestRunFullBattery:
    @pytest.mark.asyncio
    async def test_returns_report(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 200
        report = r.json()
        assert "run_id" in report
        assert report["overall_status"] in ("pass", "fail", "partial")
        assert len(report["tests"]) == 7
        ids = [t["test_id"] for t in report["tests"]]
        assert ids == ["D", "A", "B", "C", "E", "F", "G"]

    @pytest.mark.asyncio
    async def test_503_without_validator(self, app_without_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_without_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_persists_latest_report(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r1 = await client.post("/api/v1/validator/run", headers=AUTH)
            assert r1.status_code == 200
            run_id_1 = r1.json()["run_id"]

            # Latest debe reflejar la corrida recién terminada
            r2 = await client.get("/api/v1/validator/report/latest", headers=AUTH)
        assert r2.status_code == 200
        assert r2.json()["run_id"] == run_id_1


class TestRunConnectivity:
    @pytest.mark.asyncio
    async def test_runs_only_g(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/validator/connectivity", headers=AUTH,
            )
        assert r.status_code == 200
        result = r.json()
        assert result["test_id"] == "G"
        # Sin probes configurados → skip
        assert result["status"] == "skip"


class TestLatestReport:
    @pytest.mark.asyncio
    async def test_404_before_any_run(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/validator/report/latest", headers=AUTH)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_latest_matches_most_recent_run(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            await client.post("/api/v1/validator/run", headers=AUTH)
            r_second = await client.post("/api/v1/validator/run", headers=AUTH)
            run_id_2 = r_second.json()["run_id"]

            latest = await client.get(
                "/api/v1/validator/report/latest", headers=AUTH,
            )
        assert latest.json()["run_id"] == run_id_2


class TestOpenApi:
    @pytest.mark.asyncio
    async def test_endpoints_documented(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/validator/run" in paths
        assert "/api/v1/validator/connectivity" in paths
        assert "/api/v1/validator/report/latest" in paths
