"""Tests del `Validator.run_full_battery()` — orquestación + progress event."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from api.broadcaster import Broadcaster
from api.events import EVENT_VALIDATOR_PROGRESS
from modules.db import make_engine, make_session_factory
from modules.validator import TEST_ORDER, Validator


class _CapturingBroadcaster(Broadcaster):
    """Broadcaster que guarda todo lo emitido para asserts."""

    def __init__(self) -> None:
        super().__init__()
        self.emitted: list[dict[str, Any]] = []

    async def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        self.emitted.append({"event": event, "payload": payload})


@pytest.mark.asyncio
async def test_runs_7_tests_in_canonical_order(tmp_path: Path) -> None:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        report = await v.run_full_battery()

        assert len(report.tests) == 7
        assert [t.test_id for t in report.tests] == list(TEST_ORDER)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_d_passes_others_skip(tmp_path: Path) -> None:
    """V.1: solo D está implementado, el resto sigue stubbed."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        report = await v.run_full_battery()

        d = next(t for t in report.tests if t.test_id == "D")
        assert d.status == "pass"

        for t in report.tests:
            if t.test_id == "D":
                continue
            assert t.status == "skip"
            assert t.message == "not implemented yet"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_overall_status_pass_when_only_d_and_skips(
    tmp_path: Path,
) -> None:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        report = await v.run_full_battery()
        assert report.overall_status == "pass"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_emits_running_and_terminal_per_test(tmp_path: Path) -> None:
    """Cada test emite `running` primero y luego su status terminal."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        await v.run_full_battery()

        events = [
            e for e in broadcaster.emitted
            if e["event"] == EVENT_VALIDATOR_PROGRESS
        ]
        # 7 tests x 2 emisiones (running + terminal) = 14
        assert len(events) == 14

        # Primer par de emisiones corresponde a D
        assert events[0]["payload"]["test_id"] == "D"
        assert events[0]["payload"]["status"] == "running"
        assert events[1]["payload"]["test_id"] == "D"
        assert events[1]["payload"]["status"] == "pass"

        # Último par — test G (skipped en V.1)
        assert events[-2]["payload"]["test_id"] == "G"
        assert events[-2]["payload"]["status"] == "running"
        assert events[-1]["payload"]["test_id"] == "G"
        assert events[-1]["payload"]["status"] == "skip"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_all_emissions_share_run_id(tmp_path: Path) -> None:
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        report = await v.run_full_battery()

        events = [
            e for e in broadcaster.emitted
            if e["event"] == EVENT_VALIDATOR_PROGRESS
        ]
        run_ids = {e["payload"]["run_id"] for e in events}
        assert run_ids == {report.run_id}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_break_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si broadcaster.broadcast falla, la batería sigue corriendo."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)

    class _BrokenBroadcaster(Broadcaster):
        async def broadcast(self, event: str, payload: dict) -> None:
            raise RuntimeError("WS pipe broken")

    broadcaster = _BrokenBroadcaster()

    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
        )
        report = await v.run_full_battery()
        # La batería completó de todas formas
        assert len(report.tests) == 7
    finally:
        await engine.dispose()
