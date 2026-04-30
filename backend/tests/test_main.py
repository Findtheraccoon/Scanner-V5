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


class TestSettingsScanLoop:
    def test_registry_path_default(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.delenv("SCANNER_REGISTRY_PATH", raising=False)
        assert Settings().registry_path == "slot_registry.json"

    def test_registry_path_override(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_REGISTRY_PATH", "config/reg.json")
        assert Settings().registry_path == "config/reg.json"

    def test_parse_twelvedata_keys_empty(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_TWELVEDATA_KEYS", "")
        assert Settings().parse_twelvedata_keys() == []

    def test_parse_twelvedata_keys_ok(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv(
            "SCANNER_TWELVEDATA_KEYS",
            "k1:sk-abc:8:800,k2:sk-def:5:500",
        )
        keys = Settings().parse_twelvedata_keys()
        assert len(keys) == 2
        assert keys[0] == {
            "key_id": "k1", "secret": "sk-abc",
            "credits_per_minute": 8, "credits_per_day": 800,
        }

    def test_parse_twelvedata_keys_malformed_raises(self, monkeypatch) -> None:
        from settings import Settings

        monkeypatch.setenv("SCANNER_TWELVEDATA_KEYS", "k1:onlytwo")
        with pytest.raises(ValueError, match="malformed"):
            Settings().parse_twelvedata_keys()


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
            # 3 workers de heartbeat: scoring (con healthcheck) + data + database.
            # `enable_heartbeat=True` arranca los 3 — los otros motores
            # necesitan emitir heartbeats para que /engine/health los
            # reporte como green en lugar de offline.
            assert len(app.state.workers) == 3
            names = {t.get_name() for t in app.state.workers}
            assert "heartbeat_worker_scoring" in names
            assert "heartbeat_worker_data" in names
            assert "heartbeat_worker_database" in names
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
            # 3 heartbeats (scoring + data + database) + auto_scheduler = 4
            assert len(app.state.workers) == 4
            names = {t.get_name() for t in app.state.workers}
            assert names == {
                "heartbeat_worker_scoring",
                "heartbeat_worker_data",
                "heartbeat_worker_database",
                "auto_scheduler_worker",
            }
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


class TestValidatorWiring:
    """V.7 — Validator adjunto al app.state y corrida al arrancar."""

    @pytest.mark.asyncio
    async def test_build_validator_standalone(self, tmp_path) -> None:
        """Sin scan_context, el validator se construye standalone
        (A/B/C/E/G harán skip)."""
        from api import create_app
        from main import _build_validator
        from settings import Settings

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        settings = Settings(
            log_dir=str(tmp_path),
            validator_parity_enabled=False,
        )
        v = _build_validator(settings, app, scan_context=None)
        assert v is not None
        # Run a smoke battery — D pasa (infra), resto skip
        report = await v.run_full_battery()
        assert report.overall_status == "pass"
        d_test = next(t for t in report.tests if t.test_id == "D")
        assert d_test.status == "pass"
        await app.state.db_engine.dispose()

    @pytest.mark.asyncio
    async def test_startup_factory_stores_report(self, tmp_path) -> None:
        """El factory de arranque persiste el reporte en app.state."""
        from api import create_app
        from main import _build_validator, _build_validator_startup_factory
        from settings import Settings

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            auto_init_db=False,
        )
        settings = Settings(
            log_dir=str(tmp_path),
            validator_parity_enabled=False,
        )
        app.state.validator = _build_validator(settings, app, scan_context=None)

        factory = _build_validator_startup_factory(app)
        await factory()

        assert hasattr(app.state, "last_validator_report")
        assert app.state.last_validator_report.overall_status == "pass"
        await app.state.db_engine.dispose()
