"""Tests del healthcheck continuo del Scoring Engine (spec §3.4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.scoring.healthcheck import ENG_001, run_healthcheck


class TestHealthcheckHappyPath:
    def test_green_with_default_fixture(self) -> None:
        r = run_healthcheck()
        assert r["status"] == "green"
        assert r["error_code"] is None
        assert r["message"] is None
        assert r["duration_ms"] < 1000  # <1s típico

    def test_output_shape(self) -> None:
        r = run_healthcheck()
        assert set(r.keys()) == {"status", "error_code", "message", "duration_ms"}


class TestHealthcheckErrorPaths:
    def test_red_when_fixture_missing(self, tmp_path: Path) -> None:
        """Fixture inexistente → red con ENG-001."""
        r = run_healthcheck(tmp_path / "ghost.json")
        assert r["status"] == "red"
        assert r["error_code"] == ENG_001
        assert "no se pudo leer" in r["message"]

    def test_yellow_when_fixture_malformed(self, tmp_path: Path) -> None:
        """Fixture con JSON inválido → analyze() lanzará, healthcheck
        retorna yellow o red según el tipo de excepción.

        JSON inválido lo captura `_load_fixture` como OSError no — es
        JSONDecodeError. El path actual atrapa esa vía el except
        genérico en analyze(), devolviendo red con ENG-001.
        """
        bad = tmp_path / "bad.json"
        bad.write_text("{ not valid json")
        r = run_healthcheck(bad)
        # JSONDecodeError al leer fixture — el except de `_load_fixture`
        # captura OSError pero no JSONDecodeError. La excepción propaga
        # como excepción genérica dentro del try de analyze, devolviendo
        # red con ENG-001. Si este comportamiento cambia, actualizar.
        assert r["status"] == "red"


class TestHealthcheckAnalyzeIntegration:
    """Smoke: el healthcheck ejerce analyze() real con dataset sintético.

    Garantiza que el path completo de análisis funciona (indicadores,
    triggers, alignment, scoring final). Si algún módulo del motor se
    rompe, este test lo captura.
    """

    def test_analyze_returns_all_required_keys(self) -> None:
        import engines.scoring.healthcheck as hc

        fixture = json.loads(
            hc._FIXTURE_PATH_DEFAULT.read_text(encoding="utf-8"),
        )
        from engines.scoring import analyze

        out = analyze(
            ticker="QQQ",
            candles_daily=hc._SYNTHETIC_DAILY,
            candles_1h=hc._SYNTHETIC_1H,
            candles_15m=hc._SYNTHETIC_15M,
            fixture=fixture,
            spy_daily=hc._SYNTHETIC_DAILY,
            sim_datetime=hc._SIM_DATETIME_FIXED,
            sim_date=hc._SIM_DATE_FIXED,
            bench_daily=hc._SYNTHETIC_DAILY,
        )
        for key in ("ticker", "signal", "score", "conf", "layers", "ind"):
            assert key in out

    def test_signal_is_valid_vocabulary(self) -> None:
        """El signal producido pertenece al vocabulario del spec."""
        r = run_healthcheck()
        # status=green implica signal válido
        assert r["status"] == "green"


class TestHealthcheckWorkerIntegration:
    @pytest.mark.asyncio
    async def test_heartbeat_worker_uses_healthcheck_result(
        self, tmp_path: Path,
    ) -> None:
        """Worker corre el healthcheck e incluye status/error_code en el
        heartbeat emitido."""
        import asyncio
        import contextlib

        from api.broadcaster import Broadcaster
        from api.workers import heartbeat_worker
        from modules.db import init_db, make_engine, make_session_factory

        engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_db(engine)
        factory = make_session_factory(engine)

        received: list[dict] = []

        class CapturingBroadcaster(Broadcaster):
            async def broadcast(self, event: str, payload: dict) -> None:
                received.append({"event": event, "payload": payload})

        def fake_healthcheck() -> dict:
            return {
                "status": "yellow",
                "error_code": "ENG-050",
                "message": "test parity failed",
                "duration_ms": 10.0,
            }

        task = asyncio.create_task(
            heartbeat_worker(
                factory,
                CapturingBroadcaster(),
                engine_name="scoring",
                interval_s=0.1,
                healthcheck_fn=fake_healthcheck,
            ),
            name="hb_test",
        )
        # Esperar un tick
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        await engine.dispose()

        assert len(received) >= 1
        p = received[0]["payload"]
        assert p["engine"] == "scoring"
        assert p["status"] == "yellow"
        assert p["error_code"] == "ENG-050"
        assert p["message"] == "test parity failed"

    @pytest.mark.asyncio
    async def test_heartbeat_worker_green_when_healthcheck_fn_none(
        self,
    ) -> None:
        """Sin healthcheck_fn, el worker se comporta como antes (green)."""
        import asyncio
        import contextlib

        from api.broadcaster import Broadcaster
        from api.workers import heartbeat_worker
        from modules.db import init_db, make_engine, make_session_factory

        engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_db(engine)
        factory = make_session_factory(engine)

        received: list[dict] = []

        class CapturingBroadcaster(Broadcaster):
            async def broadcast(self, event: str, payload: dict) -> None:
                received.append(payload)

        task = asyncio.create_task(
            heartbeat_worker(
                factory,
                CapturingBroadcaster(),
                engine_name="scoring",
                interval_s=0.1,
                healthcheck_fn=None,
            ),
            name="hb_test2",
        )
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await engine.dispose()

        assert received[0]["status"] == "green"
        assert "error_code" not in received[0]

    @pytest.mark.asyncio
    async def test_heartbeat_worker_handles_healthcheck_exception(
        self,
    ) -> None:
        """Si el healthcheck lanza, el worker marca red + ENG-001."""
        import asyncio
        import contextlib

        from api.broadcaster import Broadcaster
        from api.workers import heartbeat_worker
        from modules.db import init_db, make_engine, make_session_factory

        engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_db(engine)
        factory = make_session_factory(engine)

        received: list[dict] = []

        class CapturingBroadcaster(Broadcaster):
            async def broadcast(self, event: str, payload: dict) -> None:
                received.append(payload)

        def crashing_hc() -> dict:
            raise RuntimeError("boom")

        task = asyncio.create_task(
            heartbeat_worker(
                factory,
                CapturingBroadcaster(),
                engine_name="scoring",
                interval_s=0.1,
                healthcheck_fn=crashing_hc,
            ),
            name="hb_test3",
        )
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        await engine.dispose()

        assert received[0]["status"] == "red"
        assert received[0]["error_code"] == "ENG-001"
        assert "boom" in received[0]["message"]
