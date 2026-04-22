"""Tests del Check D — infraestructura."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from modules.db import make_engine, make_session_factory
from modules.validator.checks import d_infra


@pytest.mark.asyncio
async def test_pass_with_real_sqlite(tmp_path: Path) -> None:
    """DB real (SQLite in-memory) + LOG dir real → pass."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    try:
        result = await d_infra.run(
            session_factory=factory, log_dir=tmp_path / "LOG",
        )
        assert result.test_id == "D"
        assert result.status == "pass"
        assert result.severity is None
        assert result.details["checks"]["db_reachable"] is True
        assert result.details["checks"]["fs_writable"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pass_without_log_dir() -> None:
    """Sin log_dir, solo se valida DB. Sigue siendo pass si DB anda."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    try:
        result = await d_infra.run(session_factory=factory, log_dir=None)
        assert result.status == "pass"
        # El check FS no corrió (no se agregó a checks[])
        assert "fs_writable" not in result.details["checks"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fatal_when_db_unreachable() -> None:
    """Si el SELECT 1 falla, el test es fail/fatal."""
    # Mock de session_factory que siempre falla al ejecutar
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.execute = AsyncMock(side_effect=RuntimeError("connection lost"))

    def factory():
        return mock_session

    result = await d_infra.run(session_factory=factory, log_dir=None)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "connection lost" in (result.message or "")
    assert result.details["checks"]["db_reachable"] is False


@pytest.mark.asyncio
async def test_fatal_when_fs_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FS no escribible → fatal. Simulado interceptando write_text."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)

    original_write = Path.write_text

    def _fail_write(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        if self.name == ".validator_fs_probe":
            raise OSError("permission denied")
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_write)

    try:
        result = await d_infra.run(
            session_factory=factory, log_dir=tmp_path / "LOG",
        )
        assert result.status == "fail"
        assert result.severity == "fatal"
        assert "permission denied" in (result.message or "")
        assert result.details["checks"]["db_reachable"] is True
        assert result.details["checks"]["fs_writable"] is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_duration_ms_populated(tmp_path: Path) -> None:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    try:
        result = await d_infra.run(
            session_factory=factory, log_dir=tmp_path,
        )
        assert result.duration_ms > 0.0
    finally:
        await engine.dispose()
