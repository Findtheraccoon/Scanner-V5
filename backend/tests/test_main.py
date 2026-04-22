"""Tests de `backend.main` — entrypoint (D.1)."""

from __future__ import annotations

import pytest


class TestLoadApiKeys:
    def test_empty_env_returns_empty_set(self, monkeypatch) -> None:
        from main import _load_api_keys

        monkeypatch.delenv("SCANNER_API_KEYS", raising=False)
        assert _load_api_keys() == set()

    def test_single_key(self, monkeypatch) -> None:
        from main import _load_api_keys

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-one")
        assert _load_api_keys() == {"sk-one"}

    def test_multiple_csv(self, monkeypatch) -> None:
        from main import _load_api_keys

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-a, sk-b ,sk-c")
        assert _load_api_keys() == {"sk-a", "sk-b", "sk-c"}

    def test_empty_tokens_filtered(self, monkeypatch) -> None:
        from main import _load_api_keys

        monkeypatch.setenv("SCANNER_API_KEYS", "sk-a,,  ,sk-b")
        assert _load_api_keys() == {"sk-a", "sk-b"}


class TestMainReturnsNonZeroOnMissingKeys:
    def test_missing_keys_returns_1(self, monkeypatch, capsys) -> None:
        from main import main

        monkeypatch.delenv("SCANNER_API_KEYS", raising=False)
        # Evita que intente bindear puerto: no llamará a uvicorn.run si
        # las keys faltan (return 1 antes).
        assert main() == 1


class TestAppWithHeartbeatEnabled:
    """El heartbeat worker solo se enciende cuando enable_heartbeat=True.

    Validamos que el lifespan maneja el caso sin romper.
    """

    @pytest.mark.asyncio
    async def test_lifespan_with_heartbeat_starts_and_stops(self) -> None:
        from api import create_app

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            enable_heartbeat=True,
            heartbeat_interval_s=0.01,
        )
        # El context manager ejecuta startup + shutdown
        async with app.router.lifespan_context(app):
            # Durante el lifespan, hay un task registrado
            assert len(app.state.workers) == 1
            assert not app.state.workers[0].done()
        # Después del shutdown, todos cancelados
        assert all(w.done() for w in app.state.workers)

    @pytest.mark.asyncio
    async def test_lifespan_without_heartbeat_has_no_workers(self) -> None:
        from api import create_app

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            enable_heartbeat=False,
        )
        async with app.router.lifespan_context(app):
            assert app.state.workers == []
