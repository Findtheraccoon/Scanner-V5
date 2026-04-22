"""Tests de los endpoints REST del Validator (V.6)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import init_db
from modules.validator import Validator

AUTH = {"Authorization": "Bearer sk-test"}


@pytest_asyncio.fixture
async def app_with_validator(tmp_path: Path):
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    app.state.validator = Validator(
        session_factory=app.state.session_factory,
        broadcaster=app.state.broadcaster,
        log_dir=tmp_path,
        parity_enabled=False,
    )
    yield app
    await app.state.db_engine.dispose()


@pytest_asyncio.fixture
async def app_without_validator():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
        auto_init_db=False,
    )
    await init_db(app.state.db_engine)
    yield app
    await app.state.db_engine.dispose()


class TestAuth:
    @pytest.mark.asyncio
    async def test_run_unauthenticated(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run")
        assert r.status_code == 401


class TestRunFullBattery:
    @pytest.mark.asyncio
    async def test_returns_report(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 200
        report = r.json()
        assert "run_id" in report
        assert report["overall_status"] in ("pass", "fail", "partial")
        assert len(report["tests"]) == 7
        ids = [t["test_id"] for t in report["tests"]]
        assert ids == ["D", "A", "B", "C", "E", "F", "G"]

    @pytest.mark.asyncio
    async def test_503_without_validator(self, app_without_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_without_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 503

    @pytest.mark.asyncio
    async def test_persists_latest_report(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r1 = await client.post("/api/v1/validator/run", headers=AUTH)
            assert r1.status_code == 200
            run_id_1 = r1.json()["run_id"]

            # Latest debe reflejar la corrida recién terminada
            r2 = await client.get("/api/v1/validator/report/latest", headers=AUTH)
        assert r2.status_code == 200
        assert r2.json()["run_id"] == run_id_1


class TestRunConnectivity:
    @pytest.mark.asyncio
    async def test_runs_only_g(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post(
                "/api/v1/validator/connectivity", headers=AUTH,
            )
        assert r.status_code == 200
        result = r.json()
        assert result["test_id"] == "G"
        # Sin probes configurados → skip
        assert result["status"] == "skip"


class TestLatestReport:
    @pytest.mark.asyncio
    async def test_404_before_any_run(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/validator/report/latest", headers=AUTH)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_latest_matches_most_recent_run(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            await client.post("/api/v1/validator/run", headers=AUTH)
            r_second = await client.post("/api/v1/validator/run", headers=AUTH)
            run_id_2 = r_second.json()["run_id"]

            latest = await client.get(
                "/api/v1/validator/report/latest", headers=AUTH,
            )
        assert latest.json()["run_id"] == run_id_2


class TestLogPersistence:
    """La ruta `POST /run` escribe el TXT a `app.state.log_dir` si existe."""

    @pytest.mark.asyncio
    async def test_run_writes_txt_log(
        self, app_with_validator, tmp_path: Path,
    ) -> None:
        app_with_validator.state.log_dir = str(tmp_path / "LOG")
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        # Debe haber un archivo validator-*-<short_id>.txt en LOG/
        # (FS sync IO en test es aceptable — ASYNC240 irrelevante acá.)
        log_dir = tmp_path / "LOG"
        files = sorted(log_dir.iterdir())
        matching = [
            f for f in files if f.name.startswith("validator-") and run_id[:8] in f.name
        ]
        assert len(matching) == 1
        assert run_id in matching[0].read_text()

    @pytest.mark.asyncio
    async def test_run_without_log_dir_skips_file(
        self, app_with_validator,
    ) -> None:
        """Sin `app.state.log_dir`, el endpoint funciona sin intentar escribir."""
        # No seteamos log_dir
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.post("/api/v1/validator/run", headers=AUTH)
        assert r.status_code == 200


class TestReportsEndpoints:
    """Endpoints `/reports*` — histórico persistido en DB (AR.4)."""

    @pytest.mark.asyncio
    async def test_reports_latest_404_empty(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get(
                "/api/v1/validator/reports/latest", headers=AUTH,
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_run_persists_and_reports_latest_returns_it(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            # Corro la batería → persiste en DB
            run_r = await client.post(
                "/api/v1/validator/run", headers=AUTH,
            )
            assert run_r.status_code == 200
            run_id = run_r.json()["run_id"]

            # /reports/latest debe devolverlo
            latest = await client.get(
                "/api/v1/validator/reports/latest", headers=AUTH,
            )
        assert latest.status_code == 200
        body = latest.json()
        assert body["run_id"] == run_id
        assert body["trigger"] == "manual"

    @pytest.mark.asyncio
    async def test_reports_history_empty(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get("/api/v1/validator/reports", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"items": [], "next_cursor": None}

    @pytest.mark.asyncio
    async def test_reports_history_paginates(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            # Corro 3 batteries
            for _ in range(3):
                await client.post("/api/v1/validator/run", headers=AUTH)

            r = await client.get(
                "/api/v1/validator/reports?limit=2", headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_reports_history_filter_trigger(
        self, app_with_validator,
    ) -> None:
        from modules.db import ET_TZ, write_validator_report
        from modules.validator import TestResult, ValidatorReport

        # Persistir 3 reportes con triggers distintos via DB directa
        async with app_with_validator.state.session_factory() as op:
            for i, trig in enumerate(("startup", "manual", "hot_reload")):
                await write_validator_report(
                    op,
                    report=ValidatorReport(
                        run_id=f"r-{i}",
                        started_at=_dt.datetime(2026, 4, 22, tzinfo=ET_TZ),
                        finished_at=_dt.datetime(2026, 4, 22, tzinfo=ET_TZ),
                        tests=[TestResult(test_id="D", status="skip")],
                    ),
                    trigger=trig,  # type: ignore[arg-type]
                )

        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get(
                "/api/v1/validator/reports?trigger=hot_reload",
                headers=AUTH,
            )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["trigger"] == "hot_reload"

    @pytest.mark.asyncio
    async def test_report_by_id_404(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get(
                "/api/v1/validator/reports/9999", headers=AUTH,
            )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_report_by_id_returns_full(
        self, app_with_validator,
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            run_r = await client.post(
                "/api/v1/validator/run", headers=AUTH,
            )
            run_id = run_r.json()["run_id"]

            # Resolver el id vía /reports
            listing = await client.get(
                "/api/v1/validator/reports", headers=AUTH,
            )
            report_id = listing.json()["items"][0]["id"]

            r = await client.get(
                f"/api/v1/validator/reports/{report_id}", headers=AUTH,
            )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == report_id
        assert body["run_id"] == run_id
        assert len(body["tests"]) == 7


class TestOpenApi:
    @pytest.mark.asyncio
    async def test_endpoints_documented(self, app_with_validator) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app_with_validator),
            base_url="http://test",
        ) as client:
            r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/validator/run" in paths
        assert "/api/v1/validator/connectivity" in paths
        assert "/api/v1/validator/report/latest" in paths
