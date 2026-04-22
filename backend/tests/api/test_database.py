"""Tests de los endpoints REST `/api/v1/database` (AR.1)."""

from __future__ import annotations

import datetime as _dt

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import ET_TZ, Signal, init_db

AUTH = {"Authorization": "Bearer sk-test"}


@pytest_asyncio.fixture
async def app_with_archive():
    """App con archive configurado (in-memory)."""
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        archive_db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    await init_db(app.state.archive_engine)
    yield app
    await app.state.db_engine.dispose()
    await app.state.archive_engine.dispose()


@pytest_asyncio.fixture
async def app_without_archive():
    """App sin archive — endpoint /rotate usa modo legacy."""
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        archive_db_url=None,
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    yield app
    await app.state.db_engine.dispose()


def _old_signal(days_ago: int = 400) -> Signal:
    now = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
    ts = now - _dt.timedelta(days=days_ago)
    return Signal(
        ticker="QQQ",
        engine_version="5.2.0",
        fixture_id="qqq_test", fixture_version="5.2.0",
        compute_timestamp=ts, candle_timestamp=ts,
        score=5.0, conf="NEUTRAL", signal=False, blocked=False,
        layers_json={}, ind_json={}, patterns_json=[],
    )


class TestRotateAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_401(self, app_with_archive) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/database/rotate")
        assert r.status_code == 401


class TestRotateWithArchive:
    @pytest.mark.asyncio
    async def test_returns_archive_mode(self, app_with_archive) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/database/rotate", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "archive"
        # Sin filas viejas, no hubo trabajo
        assert body["result"]["signals"]["archived"] == 0
        assert body["result"]["signals"]["deleted"] == 0


class TestRotateDeleteOnly:
    @pytest.mark.asyncio
    async def test_without_archive_uses_legacy_mode(
        self, app_without_archive,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_without_archive),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/database/rotate", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["mode"] == "delete_only"
        # legacy retorna dict[str,int], no dict[str,dict]
        assert isinstance(body["result"]["signals"], int)


class TestStats:
    @pytest.mark.asyncio
    async def test_empty_stats_with_archive(self, app_with_archive) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/database/stats", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["archive_configured"] is True
        assert "signals" in body["tables"]
        assert body["tables"]["signals"]["rows_operative"] == 0
        assert body["tables"]["signals"]["rows_archive"] == 0
        # Heartbeat no archivable
        assert body["tables"]["heartbeat"]["archives_to_disk"] is False
        assert body["tables"]["heartbeat"]["rows_archive"] is None

    @pytest.mark.asyncio
    async def test_stats_without_archive(self, app_without_archive) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_without_archive),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/database/stats", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["archive_configured"] is False
        assert body["tables"]["signals"]["rows_archive"] is None

    @pytest.mark.asyncio
    async def test_stats_reflect_rotation_e2e(self, app_with_archive) -> None:
        """Flujo: inserto fila vieja → rotate → stats muestra rows_archive=1."""
        async with app_with_archive.state.session_factory() as op:
            op.add(_old_signal())
            await op.commit()

        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            # Pre-rotación
            pre = (await client.get(
                "/api/v1/database/stats", headers=AUTH,
            )).json()
            assert pre["tables"]["signals"]["rows_operative"] == 1
            assert pre["tables"]["signals"]["rows_archive"] == 0

            # Rotación
            await client.post("/api/v1/database/rotate", headers=AUTH)

            # Post-rotación
            post = (await client.get(
                "/api/v1/database/stats", headers=AUTH,
            )).json()
            assert post["tables"]["signals"]["rows_operative"] == 0
            assert post["tables"]["signals"]["rows_archive"] == 1


class TestOpenApi:
    @pytest.mark.asyncio
    async def test_endpoints_documented(self, app_with_archive) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/database/rotate" in paths
        assert "/api/v1/database/stats" in paths


class TestRotateOnShutdown:
    """Smoke test: `rotate_on_shutdown=True` dispara la rotación al
    cerrar el lifespan."""

    @pytest.mark.asyncio
    async def test_shutdown_runs_rotation(self) -> None:
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            archive_db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=True,
            rotate_on_shutdown=True,
        )
        async with (
            app.router.lifespan_context(app),
            app.state.session_factory() as op,
        ):
            op.add(_old_signal())
            await op.commit()
        # Al salir del lifespan se dispara la rotación — no crashea
        # aunque los engines quedan disposed inmediatamente después.
        # La verificación que realmente se corrió la cubren los tests
        # unitarios de rotate_with_archive.

    @pytest.mark.asyncio
    async def test_shutdown_without_archive_no_op(self) -> None:
        """rotate_on_shutdown + archive_db_url=None no dispara nada."""
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            archive_db_url=None,
            auto_init_db=True,
            rotate_on_shutdown=True,
        )
        async with app.router.lifespan_context(app):
            pass
