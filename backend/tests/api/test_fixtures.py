"""Tests de los endpoints REST `/api/v1/fixtures/*`."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import init_db

AUTH = {"Authorization": "Bearer sk-test"}

REPO_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _copy_canonical(target_dir: Path) -> Path:
    """Copia el fixture QQQ canonical al `target_dir`. Devuelve el path."""
    target_dir.mkdir(parents=True, exist_ok=True)
    src = REPO_FIXTURES / "qqq_canonical_v1.json"
    dst = target_dir / "qqq_canonical_v1.json"
    shutil.copy(src, dst)
    sha_src = REPO_FIXTURES / "qqq_canonical_v1.sha256"
    if sha_src.is_file():
        shutil.copy(sha_src, target_dir / "qqq_canonical_v1.sha256")
    metrics_src = REPO_FIXTURES / "qqq_canonical_v1.metrics.json"
    if metrics_src.is_file():
        shutil.copy(metrics_src, target_dir / "qqq_canonical_v1.metrics.json")
    return dst


@pytest_asyncio.fixture
async def app(tmp_path: Path):
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
        fixtures_dir=str(fixtures_dir),
    )
    await init_db(app.state.db_engine)
    yield app
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════


class TestAuth:
    async def test_endpoints_require_bearer(self, client: AsyncClient) -> None:
        for method, path in [
            ("GET", "/api/v1/fixtures"),
            ("DELETE", "/api/v1/fixtures/qqq_canonical_v1"),
        ]:
            r = await client.request(method, path)
            assert r.status_code == 401

    async def test_upload_requires_bearer(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/fixtures/upload",
            files={"file": ("x.json", b"{}", "application/json")},
        )
        assert r.status_code == 401


# ════════════════════════════════════════════════════════════════════
# GET /fixtures
# ════════════════════════════════════════════════════════════════════


class TestList:
    async def test_empty_dir(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/fixtures", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert "engine_version" in body

    async def test_lists_canonical_with_metadata(
        self, client: AsyncClient, app,
    ) -> None:
        _copy_canonical(app.state.fixtures_dir)
        r = await client.get("/api/v1/fixtures", headers=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        item = items[0]
        assert item["fixture_id"] == "qqq_canonical_v1"
        assert item["fixture_version"] == "5.2.0"
        assert item["ticker_default"] == "QQQ"
        assert item["sha256_status"] in ("ok", "no canonical")
        assert "engine_compatible" in item
        assert item["used_by_slots"] == []  # sin registry runtime wired

    async def test_excludes_metrics_sibling(
        self, client: AsyncClient, app,
    ) -> None:
        _copy_canonical(app.state.fixtures_dir)
        # El listado no debe incluir el .metrics.json como item separado.
        r = await client.get("/api/v1/fixtures", headers=AUTH)
        items = r.json()["items"]
        names = [it.get("filename") for it in items]
        assert "qqq_canonical_v1.metrics.json" not in names

    async def test_reports_invalid_json_with_error(
        self, client: AsyncClient, app,
    ) -> None:
        bad = app.state.fixtures_dir / "bad.json"
        bad.write_text("not json")
        r = await client.get("/api/v1/fixtures", headers=AUTH)
        items = r.json()["items"]
        assert len(items) == 1
        assert "error" in items[0]


# ════════════════════════════════════════════════════════════════════
# POST /fixtures/upload
# ════════════════════════════════════════════════════════════════════


class TestUpload:
    async def test_uploads_canonical(
        self, client: AsyncClient, app,
    ) -> None:
        src = REPO_FIXTURES / "qqq_canonical_v1.json"
        body = src.read_bytes()
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={
                "file": (
                    "qqq_canonical_v1.json",
                    body,
                    "application/json",
                ),
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["uploaded"] is True
        assert data["fixture_id"] == "qqq_canonical_v1"
        assert data["sha256"] == hashlib.sha256(body).hexdigest()

        # Files persisted on disk.
        target = app.state.fixtures_dir / "qqq_canonical_v1.json"
        assert target.is_file()
        sha_target = app.state.fixtures_dir / "qqq_canonical_v1.sha256"
        assert sha_target.is_file()

    async def test_409_on_duplicate(
        self, client: AsyncClient, app,
    ) -> None:
        _copy_canonical(app.state.fixtures_dir)
        src = REPO_FIXTURES / "qqq_canonical_v1.json"
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={
                "file": (
                    "qqq_canonical_v1.json",
                    src.read_bytes(),
                    "application/json",
                ),
            },
        )
        assert r.status_code == 409

    async def test_400_non_json_filename(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={"file": ("x.txt", b"{}", "text/plain")},
        )
        assert r.status_code == 400

    async def test_400_invalid_json(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={"file": ("x.json", b"not json", "application/json")},
        )
        assert r.status_code == 400

    async def test_400_invalid_schema(self, client: AsyncClient) -> None:
        bogus = json.dumps({"foo": "bar"}).encode()
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={"file": ("x.json", bogus, "application/json")},
        )
        assert r.status_code == 400

    async def test_422_engine_compat_mismatch(
        self, client: AsyncClient,
    ) -> None:
        # Fixture válida pero con engine_compat_range incompatible.
        src = REPO_FIXTURES / "qqq_canonical_v1.json"
        data = json.loads(src.read_text())
        data["metadata"]["engine_compat_range"] = ">=99.0.0"
        data["metadata"]["fixture_id"] = "future_fixture"
        body = json.dumps(data).encode()
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={"file": ("future.json", body, "application/json")},
        )
        assert r.status_code == 422

    async def test_400_empty_file(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/v1/fixtures/upload",
            headers=AUTH,
            files={"file": ("x.json", b"", "application/json")},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════
# DELETE /fixtures/{id}
# ════════════════════════════════════════════════════════════════════


class TestDelete:
    async def test_404_when_missing(self, client: AsyncClient) -> None:
        r = await client.delete(
            "/api/v1/fixtures/nonexistent_fixture", headers=AUTH,
        )
        assert r.status_code == 404

    async def test_deletes_files(
        self, client: AsyncClient, app,
    ) -> None:
        _copy_canonical(app.state.fixtures_dir)
        json_path = app.state.fixtures_dir / "qqq_canonical_v1.json"
        sha_path = app.state.fixtures_dir / "qqq_canonical_v1.sha256"
        metrics_path = app.state.fixtures_dir / "qqq_canonical_v1.metrics.json"
        assert json_path.is_file()

        r = await client.delete(
            "/api/v1/fixtures/qqq_canonical_v1", headers=AUTH,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["deleted"] is True
        assert not json_path.is_file()
        assert not sha_path.is_file()
        assert not metrics_path.is_file()

    async def test_409_when_used_by_slot(
        self, client: AsyncClient, app, monkeypatch,
    ) -> None:
        _copy_canonical(app.state.fixtures_dir)

        # Fake registry runtime con un slot que usa el fixture.
        class _FakeRecord:
            def __init__(self) -> None:
                self.slot = 1
                self.fixture = type(
                    "F", (), {
                        "metadata": type(
                            "M", (), {"fixture_id": "qqq_canonical_v1"},
                        )(),
                    },
                )()

        # BUG-005: el código previo del endpoint llamaba
        # `runtime._registry.snapshot()` que no existe en `SlotRegistry`.
        # Ahora itera directamente `runtime._registry.slots`. El fake
        # se actualizó para reflejar el shape real.
        class _FakeRegistry:
            slots = [_FakeRecord()]

        class _FakeRuntime:
            _registry = _FakeRegistry()

        app.state.registry_runtime = _FakeRuntime()

        r = await client.delete(
            "/api/v1/fixtures/qqq_canonical_v1", headers=AUTH,
        )
        assert r.status_code == 409
        body = r.json()["detail"]
        assert body["used_by_slots"] == [1]
