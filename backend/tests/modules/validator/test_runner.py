"""Tests del `Validator.run_full_battery()` — orquestación + progress event."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from api.broadcaster import Broadcaster
from api.events import EVENT_VALIDATOR_PROGRESS
from engines.registry_runtime import RegistryRuntime
from engines.scoring import ENGINE_VERSION
from modules.db import make_engine, make_session_factory
from modules.slot_registry import load_registry
from modules.validator import TEST_ORDER, Validator
from tests.modules.slot_registry.test_loader import _write_registry


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
            parity_enabled=False,
        )
        report = await v.run_full_battery()

        assert len(report.tests) == 7
        assert [t.test_id for t in report.tests] == list(TEST_ORDER)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_without_inputs_abce_skip_with_reason(tmp_path: Path) -> None:
    """Sin registry / registry_path / scan_executor, A/B/C/E emiten skip
    con mensaje explicativo (no con 'not implemented yet')."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            parity_enabled=False,
        )
        report = await v.run_full_battery()

        d = next(t for t in report.tests if t.test_id == "D")
        assert d.status == "pass"

        # A, B, C, E: skip por falta de inputs (mensaje específico)
        for tid in ("A", "B", "C", "E"):
            t = next(t for t in report.tests if t.test_id == tid)
            assert t.status == "skip"
            assert "no provisto" in (t.message or "")

        # F skip por parity_enabled=False
        f_test = next(t for t in report.tests if t.test_id == "F")
        assert f_test.status == "skip"
        assert "parity disabled" in (f_test.message or "")

        # G skip por falta de probes
        g_test = next(t for t in report.tests if t.test_id == "G")
        assert g_test.status == "skip"
        assert "sin probes" in (g_test.message or "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_with_registry_abc_run(tmp_path: Path) -> None:
    """Con registry + path pasados, los checks A/B/C corren y pasan."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()

    registry_path = _write_registry(tmp_path)
    registry = load_registry(registry_path, engine_version=ENGINE_VERSION)
    runtime = RegistryRuntime(registry)

    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            registry=runtime,
            registry_path=registry_path,
            parity_enabled=False,
        )
        report = await v.run_full_battery()

        # D pasa (infra)
        assert next(t for t in report.tests if t.test_id == "D").status == "pass"
        # A pasa (fixture QQQ válida)
        assert next(t for t in report.tests if t.test_id == "A").status == "pass"
        # B pasa (hash canonical coincide)
        assert next(t for t in report.tests if t.test_id == "B").status == "pass"
        # C pasa (registry healthy)
        assert next(t for t in report.tests if t.test_id == "C").status == "pass"
        # E skip por falta de scan_executor
        e_test = next(t for t in report.tests if t.test_id == "E")
        assert e_test.status == "skip"
        assert "no provisto" in (e_test.message or "")
        # F skip (parity_enabled=False en este test — evita lentitud)
        f_test = next(t for t in report.tests if t.test_id == "F")
        assert f_test.status == "skip"
        # G skip por falta de probes
        g_test = next(t for t in report.tests if t.test_id == "G")
        assert g_test.status == "skip"
        assert "sin probes" in (g_test.message or "")

        assert report.overall_status == "pass"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_parity_disabled_skips_f(tmp_path: Path) -> None:
    """Con parity_enabled=False, Check F emite skip con mensaje específico."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            parity_enabled=False,
        )
        report = await v.run_full_battery()
        f_test = next(t for t in report.tests if t.test_id == "F")
        assert f_test.status == "skip"
        assert "parity disabled" in (f_test.message or "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_parity_enabled_runs_f_with_default_db(tmp_path: Path) -> None:
    """Con parity_enabled (default) + DB del repo, F corre con la DB real.

    Uso limit=5 para mantenerlo rápido.
    """
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()
    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            parity_limit=5,
        )
        report = await v.run_full_battery()
        f_test = next(t for t in report.tests if t.test_id == "F")
        # La DB está en el repo → no skip. Pass o warning según match rate.
        assert f_test.status in ("pass", "fail")
        assert f_test.details["total"] == 5
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_with_probes_g_runs(tmp_path: Path) -> None:
    """Con td_probe + s3_probe, Check G corre y reporta."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()

    async def _td() -> list[dict]:
        return [{"key_id": "k1", "ok": True}]

    async def _s3() -> dict:
        return {"ok": True}

    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            parity_enabled=False,
            td_probe=_td,
            s3_probe=_s3,
        )
        report = await v.run_full_battery()
        g_test = next(t for t in report.tests if t.test_id == "G")
        assert g_test.status == "pass"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_with_scan_executor_e_runs(tmp_path: Path) -> None:
    """Con scan_executor pasado, Check E corre y pasa."""
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    factory = make_session_factory(engine)
    broadcaster = _CapturingBroadcaster()

    async def _fake_executor() -> dict:
        return {
            "ticker": "QQQ",
            "signal": "NEUTRAL",
            "score": 0.0,
            "persisted": False,
            "id": None,
        }

    try:
        v = Validator(
            session_factory=factory,
            broadcaster=broadcaster,
            log_dir=tmp_path,
            scan_executor=_fake_executor,
            parity_enabled=False,
        )
        report = await v.run_full_battery()
        e_test = next(t for t in report.tests if t.test_id == "E")
        assert e_test.status == "pass"
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
            parity_enabled=False,
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
            parity_enabled=False,
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
            parity_enabled=False,
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
            parity_enabled=False,
        )
        report = await v.run_full_battery()
        # La batería completó de todas formas
        assert len(report.tests) == 7
    finally:
        await engine.dispose()
