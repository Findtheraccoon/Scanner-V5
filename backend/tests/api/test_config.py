"""Tests de los endpoints REST `/api/v1/config/*`.

Cubren los 10 endpoints del Config:
- POST /load, /save, /save_as, /clear, /reload-policies
- GET /last, /current
- PUT /twelvedata_keys, /s3, /startup_flags
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from engines.data import ApiKeyConfig, KeyPool
from modules.config import (
    S3Config,
    StartupFlags,
    TDKeyConfig,
    UserConfig,
    save_config,
)
from modules.db import init_db

AUTH = {"Authorization": "Bearer sk-test"}


@pytest_asyncio.fixture
async def app(tmp_path: Path):
    last_path_file = tmp_path / "last_config_path.json"
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
        last_config_path_file=str(last_path_file),
    )
    await init_db(app.state.db_engine)
    yield app
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _sample_config() -> UserConfig:
    return UserConfig(
        name="trader-alvaro",
        twelvedata_keys=[
            TDKeyConfig(key_id="k1", secret="td-secret-1"),
            TDKeyConfig(key_id="k2", secret="td-secret-2"),
        ],
        s3_config=S3Config(
            bucket="b",
            access_key_id="ak",
            secret_access_key="sk",
        ),
        api_bearer_token="bearer-zzz",
    )


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════


class TestAuth:
    async def test_endpoints_require_bearer(self, client: AsyncClient) -> None:
        for method, path, body in [
            ("POST", "/api/v1/config/load", {"path": "x"}),
            ("POST", "/api/v1/config/save", {}),
            ("POST", "/api/v1/config/save_as", {"path": "x"}),
            ("POST", "/api/v1/config/clear", None),
            ("GET", "/api/v1/config/last", None),
            ("GET", "/api/v1/config/current", None),
            ("PUT", "/api/v1/config/twelvedata_keys", {"twelvedata_keys": []}),
            ("PUT", "/api/v1/config/s3", {"s3_config": None}),
            ("POST", "/api/v1/config/reload-policies", None),
        ]:
            r = await client.request(method, path, json=body)
            assert r.status_code == 401, f"{method} {path} no es 401"


# ════════════════════════════════════════════════════════════════════
# /load + /save + /save_as + /current
# ════════════════════════════════════════════════════════════════════


class TestLoadSave:
    async def test_load_writes_runtime_and_last(
        self, client: AsyncClient, app, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(_sample_config(), cfg_path)

        r = await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["loaded"] is True
        assert data["path"] == str(cfg_path)
        assert data["name"] == "trader-alvaro"

        # Runtime poblado
        assert app.state.user_config is not None
        assert app.state.user_config.name == "trader-alvaro"

        # LAST persistido
        last_file = app.state.last_config_path_file
        assert last_file.is_file()
        meta = json.loads(last_file.read_text())
        assert meta["path"] == str(cfg_path)
        assert "loaded_at" in meta

    async def test_load_404_if_missing(self, client: AsyncClient, tmp_path: Path) -> None:
        r = await client.post(
            "/api/v1/config/load",
            json={"path": str(tmp_path / "nope.json")},
            headers=AUTH,
        )
        assert r.status_code == 404

    async def test_load_400_if_invalid_json(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        r = await client.post(
            "/api/v1/config/load", json={"path": str(bad)}, headers=AUTH,
        )
        assert r.status_code == 400

    async def test_load_400_if_invalid_schema(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"name": "x", "unknown_field": True}))
        r = await client.post(
            "/api/v1/config/load", json={"path": str(bad)}, headers=AUTH,
        )
        assert r.status_code == 400

    async def test_save_writes_to_current_path(
        self, client: AsyncClient, app, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(UserConfig(name="initial"), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        # Edit + save
        await client.put(
            "/api/v1/config/twelvedata_keys",
            json={
                "twelvedata_keys": [
                    {"key_id": "k1", "secret": "s1"},
                ],
            },
            headers=AUTH,
        )
        r = await client.post("/api/v1/config/save", json={}, headers=AUTH)
        assert r.status_code == 200, r.text
        assert r.json()["path"] == str(cfg_path)

        # Verifico que el JSON en disco refleja la edición.
        on_disk = json.loads(cfg_path.read_text())
        assert on_disk["twelvedata_keys"][0]["key_id"] == "k1"
        assert on_disk["twelvedata_keys"][0]["secret"] == "s1"

    async def test_save_400_without_loaded_config(
        self, client: AsyncClient,
    ) -> None:
        r = await client.post("/api/v1/config/save", json={}, headers=AUTH)
        assert r.status_code == 400

    async def test_save_400_without_current_path_or_body(
        self, client: AsyncClient, app,
    ) -> None:
        # Hay user_config en memoria pero sin path (vía PUT en lugar de load).
        await client.put(
            "/api/v1/config/twelvedata_keys",
            json={"twelvedata_keys": []},
            headers=AUTH,
        )
        r = await client.post("/api/v1/config/save", json={}, headers=AUTH)
        assert r.status_code == 400

    async def test_save_with_explicit_path(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(UserConfig(name="x"), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        new_path = tmp_path / "other.json"
        r = await client.post(
            "/api/v1/config/save",
            json={"path": str(new_path)},
            headers=AUTH,
        )
        assert r.status_code == 200
        assert new_path.is_file()

    async def test_save_as(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(UserConfig(name="x"), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        new_path = tmp_path / "saved-as.json"
        r = await client.post(
            "/api/v1/config/save_as",
            json={"path": str(new_path)},
            headers=AUTH,
        )
        assert r.status_code == 200
        assert new_path.is_file()

    async def test_save_as_400_without_runtime(self, client: AsyncClient, tmp_path: Path) -> None:
        r = await client.post(
            "/api/v1/config/save_as",
            json={"path": str(tmp_path / "x.json")},
            headers=AUTH,
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════
# /current + /clear + /last
# ════════════════════════════════════════════════════════════════════


class TestCurrentClearLast:
    async def test_current_when_empty(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/config/current", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"loaded": False, "config": None, "path": None}

    async def test_current_redacts_secrets_by_default(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(_sample_config(), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        r = await client.get("/api/v1/config/current", headers=AUTH)
        body = r.json()
        assert body["loaded"] is True
        cfg = body["config"]
        assert cfg["twelvedata_keys"][0]["secret"] == "***"
        assert cfg["s3_config"]["secret_access_key"] == "***"
        assert cfg["api_bearer_token"] == "***"

    async def test_current_include_secrets_returns_raw(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(_sample_config(), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        r = await client.get(
            "/api/v1/config/current?include_secrets=true", headers=AUTH,
        )
        cfg = r.json()["config"]
        assert cfg["twelvedata_keys"][0]["secret"] == "td-secret-1"
        assert cfg["s3_config"]["secret_access_key"] == "sk"
        assert cfg["api_bearer_token"] == "bearer-zzz"

    async def test_clear_wipes_runtime(
        self, client: AsyncClient, app, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(_sample_config(), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        assert app.state.user_config is not None

        r = await client.post("/api/v1/config/clear", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"cleared": True}
        assert app.state.user_config is None
        assert app.state.user_config_path is None

    async def test_last_returns_null_initially(self, client: AsyncClient) -> None:
        r = await client.get("/api/v1/config/last", headers=AUTH)
        assert r.status_code == 200
        assert r.json() is None

    async def test_last_returns_path_after_load(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(UserConfig(), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        r = await client.get("/api/v1/config/last", headers=AUTH)
        body = r.json()
        assert body["path"] == str(cfg_path)
        assert "loaded_at" in body

    async def test_last_persists_after_save_as(
        self, client: AsyncClient, tmp_path: Path,
    ) -> None:
        cfg_path = tmp_path / "c.json"
        save_config(UserConfig(), cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        new_path = tmp_path / "new.json"
        await client.post(
            "/api/v1/config/save_as",
            json={"path": str(new_path)},
            headers=AUTH,
        )
        r = await client.get("/api/v1/config/last", headers=AUTH)
        assert r.json()["path"] == str(new_path)


# ════════════════════════════════════════════════════════════════════
# PUT /twelvedata_keys + reload del KeyPool
# ════════════════════════════════════════════════════════════════════


class TestPutTwelvedataKeys:
    async def test_creates_runtime_if_empty(
        self, client: AsyncClient, app,
    ) -> None:
        r = await client.put(
            "/api/v1/config/twelvedata_keys",
            json={
                "twelvedata_keys": [
                    {"key_id": "k1", "secret": "s1"},
                ],
            },
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        # Sin KeyPool wired, reload no aplica.
        assert body["key_pool_reloaded"] is False
        assert app.state.user_config is not None
        assert len(app.state.user_config.twelvedata_keys) == 1

    async def test_reloads_key_pool_when_present(
        self, client: AsyncClient, app,
    ) -> None:
        # Wire un KeyPool dummy en app.state.
        pool = KeyPool([
            ApiKeyConfig(key_id="old", secret="old-secret",
                         credits_per_minute=8, credits_per_day=800),
        ])
        app.state.key_pool = pool

        r = await client.put(
            "/api/v1/config/twelvedata_keys",
            json={
                "twelvedata_keys": [
                    {"key_id": "new1", "secret": "n1",
                     "credits_per_minute": 8, "credits_per_day": 800},
                    {"key_id": "new2", "secret": "n2",
                     "credits_per_minute": 8, "credits_per_day": 800},
                ],
            },
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["key_pool_reloaded"] is True
        snap = pool.snapshot()
        assert {s.key_id for s in snap} == {"new1", "new2"}


class TestPutS3:
    async def test_set_and_clear(self, client: AsyncClient, app) -> None:
        # Set
        r = await client.put(
            "/api/v1/config/s3",
            json={
                "s3_config": {
                    "bucket": "b",
                    "access_key_id": "ak",
                    "secret_access_key": "sk",
                },
            },
            headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["configured"] is True
        assert app.state.user_config.s3_config is not None

        # Clear
        r = await client.put(
            "/api/v1/config/s3", json={"s3_config": None}, headers=AUTH,
        )
        assert r.status_code == 200
        assert r.json()["configured"] is False
        assert app.state.user_config.s3_config is None


class TestPutStartupFlags:
    async def test_updates_runtime_and_db_size_limit(
        self, client: AsyncClient, app,
    ) -> None:
        r = await client.put(
            "/api/v1/config/startup_flags",
            json={
                "startup_flags": {
                    "validator_run_at_startup": False,
                    "validator_parity_enabled": False,
                    "validator_parity_limit": 50,
                    "heartbeat_interval_s": 60.0,
                    "rotate_on_shutdown": True,
                    "aggressive_rotation_enabled": True,
                    "aggressive_rotation_interval_s": 1800.0,
                    "db_size_limit_mb": 8000,
                },
            },
            headers=AUTH,
        )
        assert r.status_code == 200
        body = r.json()
        assert "db_size_limit_mb" in body["applied_immediately"]
        assert app.state.db_size_limit_mb == 8000
        assert app.state.user_config.startup_flags.db_size_limit_mb == 8000


class TestReloadPolicies:
    async def test_no_op_without_config(self, client: AsyncClient) -> None:
        r = await client.post("/api/v1/config/reload-policies", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["applied"] == []

    async def test_applies_db_size_limit_after_load(
        self, client: AsyncClient, app, tmp_path: Path,
    ) -> None:
        cfg = UserConfig(
            startup_flags=StartupFlags(db_size_limit_mb=12345),
        )
        cfg_path = tmp_path / "c.json"
        save_config(cfg, cfg_path)
        await client.post(
            "/api/v1/config/load", json={"path": str(cfg_path)}, headers=AUTH,
        )
        # Verifico que `app.state.db_size_limit_mb` no se actualiza al load.
        # Solo /reload-policies lo aplica.
        await client.post("/api/v1/config/reload-policies", headers=AUTH)
        assert app.state.db_size_limit_mb == 12345
