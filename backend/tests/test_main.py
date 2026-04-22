"""Tests de `backend.main` y `settings.py` — entrypoint (D.1 + D.3)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


class TestSettings:
    def test_empty_api_keys_default(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.delenv("SCANNER_API_KEYS", raising=False)
        s = Settings()
        assert s.api_keys == ""
        assert s.api_keys_set == set()

    def test_api_keys_single(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-one")
        s = Settings()
        assert s.api_keys_set == {"sk-one"}

    def test_api_keys_csv(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-a, sk-b ,sk-c")
        s = Settings()
        assert s.api_keys_set == {"sk-a", "sk-b", "sk-c"}

    def test_api_keys_filters_empty_tokens(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-a,,  ,sk-b")
        s = Settings()
        assert s.api_keys_set == {"sk-a", "sk-b"}

    def test_defaults(self, monkeypatch) -> None:
        from settings import Settings

        for v in (
            "SCANNER_DB_PATH", "SCANNER_HOST", "SCANNER_PORT",
            "SCANNER_HEARTBEAT_INTERVAL_S", "SCANNER_AUTO_SCHEDULER_ENABLED",
            "SCANNER_AUTO_SCHEDULER_INTERVAL_S", "SCANNER_SHUTDOWN_TIMEOUT_S",
            "SCANNER_LOG_LEVEL",
        ):
            monkeypatch.delenv(v, raising=False)
        s = Settings()
        assert s.db_path == "data/scanner.db"
        assert s.host == "127.0.0.1"
        assert s.port == 8000
        assert s.heartbeat_interval_s == 120.0
        assert s.auto_scheduler_enabled is False
        assert s.auto_scheduler_interval_s == 60.0
        assert s.shutdown_timeout_s == 30.0
        assert s.log_level == "INFO"

    def test_log_level_normalized_to_upper(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_LOG_LEVEL", "debug")
        assert Settings().log_level == "DEBUG"

    def test_port_validation(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_PORT", "99999")
        with pytest.raises(ValidationError):
            Settings()

    def test_interval_must_be_positive(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_HEARTBEAT_INTERVAL_S", "0")
        with pytest.raises(ValidationError):
            Settings()


class TestMainExitCodes:
    def test_missing_keys_returns_1(self, monkeypatch) -> None:
        from main import main

        monkeypatch.delenv("SCANNER_API_KEYS", raising=False)
        assert main() == 1


class TestAppLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_with_heartbeat_only(self) -> None:
        from api import create_app

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            enable_heartbeat=True,
            heartbeat_interval_s=60.0,
        )
        async with app.router.lifespan_context(app):
            # 1 worker: heartbeat
            assert len(app.state.workers) == 1
            names = {t.get_name() for t in app.state.workers}
            assert "heartbeat_worker" in names
        assert all(w.done() for w in app.state.workers)

    @pytest.mark.asyncio
    async def test_lifespan_with_all_workers(self) -> None:
        from api import create_app

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            enable_heartbeat=True,
            enable_auto_scheduler=True,
            heartbeat_interval_s=60.0,
            auto_scheduler_interval_s=60.0,
        )
        async with app.router.lifespan_context(app):
            assert len(app.state.workers) == 2
            names = {t.get_name() for t in app.state.workers}
            assert names == {"heartbeat_worker", "auto_scheduler_worker"}
        assert all(w.done() for w in app.state.workers)

    @pytest.mark.asyncio
    async def test_lifespan_without_workers(self) -> None:
        from api import create_app

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            enable_heartbeat=False,
            enable_auto_scheduler=False,
        )
        async with app.router.lifespan_context(app):
            assert app.state.workers == []
