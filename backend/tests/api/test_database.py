"""Tests de los endpoints REST `/api/v1/database` (AR.1)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

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


class TestBackupEndpoints:
    """Endpoints POST /backup, /restore, /backups usando moto."""

    _BUCKET = "scanner-test-bucket"

    @staticmethod
    def _s3_body() -> dict:
        return {
            "s3": {
                "bucket": "scanner-test-bucket",
                "access_key_id": "testing",
                "secret_access_key": "testing",
                "region": "us-east-1",
                "key_prefix": "scanner-backups/",
            },
        }

    @pytest_asyncio.fixture
    async def app_with_file_db(self, tmp_path):
        """App con DB en archivo real (no :memory:) — backup/restore
        requieren path físico."""
        from api import create_app
        from modules.db import init_db

        db_path = tmp_path / "scanner.db"
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url=f"sqlite+aiosqlite:///{db_path}",
            archive_db_url=None,
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        # Forzar que el archivo se materialice en disco
        async with app.state.session_factory() as op:
            from sqlalchemy import text as sql_text
            await op.execute(sql_text("SELECT 1"))
        yield app, db_path
        await app.state.db_engine.dispose()

    @pytest.fixture
    def mock_s3(self):
        import boto3
        from moto import mock_aws

        with mock_aws():
            boto3.client("s3", region_name="us-east-1").create_bucket(
                Bucket=self._BUCKET,
            )
            yield

    @pytest.mark.asyncio
    async def test_backup_uploads_and_returns_metadata(
        self, app_with_file_db, mock_s3,
    ) -> None:
        app, _ = app_with_file_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/database/backup",
                json=self._s3_body(),
                headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["bucket"] == self._BUCKET
        assert body["key"].startswith("scanner-backups/scanner-")
        assert body["key"].endswith(".db.gz")
        assert body["size_bytes_gz"] > 0

    @pytest.mark.asyncio
    async def test_backup_rejects_memory_db(self, mock_s3) -> None:
        """`:memory:` no tiene path físico → 400."""
        from api import create_app
        from modules.db import init_db

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                r = await client.post(
                    "/api/v1/database/backup",
                    json=self._s3_body(),
                    headers=AUTH,
                )
            assert r.status_code == 400
            assert "in-memory" in r.text
        finally:
            await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_restore_creates_sibling_file(
        self, app_with_file_db, mock_s3,
    ) -> None:
        app, db_path = app_with_file_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            up = await client.post(
                "/api/v1/database/backup",
                json=self._s3_body(),
                headers=AUTH,
            )
            key = up.json()["key"]

            r = await client.post(
                "/api/v1/database/restore",
                json={**self._s3_body(), "key": key},
                headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["bucket"] == self._BUCKET
        assert "notice" in body
        restored = Path(body["restored_path"])
        import asyncio as _asyncio
        assert await _asyncio.to_thread(restored.is_file)
        assert restored.parent == db_path.parent
        assert restored.name.startswith("scanner.db.restored-")

    @pytest.mark.asyncio
    async def test_list_backups_empty_bucket(
        self, app_with_file_db, mock_s3,
    ) -> None:
        app, _ = app_with_file_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/database/backups",
                json=self._s3_body(),
                headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["bucket"] == self._BUCKET
        assert body["objects"] == []

    @pytest.mark.asyncio
    async def test_list_backups_sees_uploaded(
        self, app_with_file_db, mock_s3,
    ) -> None:
        app, _ = app_with_file_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            await client.post(
                "/api/v1/database/backup",
                json=self._s3_body(),
                headers=AUTH,
            )
            r = await client.post(
                "/api/v1/database/backups",
                json=self._s3_body(),
                headers=AUTH,
            )
        assert r.status_code == 200
        objs = r.json()["objects"]
        assert len(objs) == 1
        assert objs[0]["key"].startswith("scanner-backups/")


class TestAggressiveRotationEndpoint:
    """`POST /database/rotate/aggressive` (§9.4)."""

    @pytest_asyncio.fixture
    async def app_file_db(self, tmp_path):
        """App con DB en archivo real + archive + size_limit bajo."""
        from api import create_app
        from modules.db import init_db

        db_path = tmp_path / "scanner.db"
        archive_path = tmp_path / "archive.db"
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url=f"sqlite+aiosqlite:///{db_path}",
            archive_db_url=f"sqlite+aiosqlite:///{archive_path}",
            auto_init_db=False,
            db_size_limit_mb=0,  # forzar trigger con cualquier contenido
        )
        await init_db(app.state.db_engine)
        await init_db(app.state.archive_engine)
        yield app, db_path
        await app.state.db_engine.dispose()
        await app.state.archive_engine.dispose()

    @pytest.mark.asyncio
    async def test_503_without_archive(self) -> None:
        from api import create_app
        from modules.db import init_db

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            archive_db_url=None,
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                r = await client.post(
                    "/api/v1/database/rotate/aggressive", headers=AUTH,
                )
            assert r.status_code == 503
        finally:
            await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_400_with_memory_db(self) -> None:
        from api import create_app
        from modules.db import init_db

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            archive_db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        await init_db(app.state.archive_engine)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                r = await client.post(
                    "/api/v1/database/rotate/aggressive", headers=AUTH,
                )
            assert r.status_code == 400
        finally:
            await app.state.db_engine.dispose()
            await app.state.archive_engine.dispose()

    @pytest.mark.asyncio
    async def test_triggers_when_over_limit(self, app_file_db) -> None:
        app, _ = app_file_db
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/database/rotate/aggressive", headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["triggered"] is True
        assert body["size_mb_before"] > 0
        assert "rotation" in body
        assert body["vacuum_recommended"] is True


class TestStatsIncludesSize:
    """`/stats` devuelve `size_mb_operative` + `size_limit_mb` (AR.5)."""

    @pytest.mark.asyncio
    async def test_stats_exposes_size_fields(
        self, app_with_archive,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_archive),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/database/stats", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        # En :memory: size es None
        assert "size_mb_operative" in body
        assert "size_limit_mb" in body
        assert body["size_limit_mb"] == 5000  # default


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


class TestVacuum:
    """`POST /database/vacuum` — recupera espacio post rotación agresiva."""

    @pytest.mark.asyncio
    async def test_unauthenticated_401(self) -> None:
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/database/vacuum")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_in_memory_returns_400(self) -> None:
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    "/api/v1/database/vacuum", headers=AUTH,
                )
            assert r.status_code == 400
            assert "in-memory" in r.text or "memory" in r.text
        finally:
            await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_vacuum_on_file_db_returns_sizes(self, tmp_path: Path) -> None:
        db_file = tmp_path / "scanner.db"
        app = create_app(
            valid_api_keys={"sk-test"},
            db_url=f"sqlite+aiosqlite:///{db_file}",
            auto_init_db=False,
        )
        await init_db(app.state.db_engine)
        # Inserto y borro filas para que VACUUM tenga algo que reclamar.
        async with app.state.session_factory() as session:
            for i in range(50):
                session.add(_old_signal(days_ago=400 + i))
            await session.commit()
        # Cierro el engine antes del VACUUM (SQLite locking).
        await app.state.db_engine.dispose()

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                r = await client.post(
                    "/api/v1/database/vacuum", headers=AUTH,
                )
            assert r.status_code == 200, r.text
            body = r.json()
            assert "size_mb_before" in body
            assert "size_mb_after" in body
            assert "db_path" in body
            assert body["size_mb_after"] >= 0
        finally:
            # El handler del vacuum reabrió la conexión SQLite directa,
            # pero el engine SQLAlchemy ya estaba disposed.
            pass
