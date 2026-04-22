"""Tests de endpoints REST de signals (C5.4).

Se inicializa una app con DB `:memory:`, se inyectan señales via los
helpers del módulo DB, y se verifica la respuesta HTTP.
"""

from __future__ import annotations

import base64
import datetime as dt

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api import create_app
from modules.db import ET_TZ, write_signal

AUTH = {"Authorization": "Bearer sk-test"}


def _make_output(
    *,
    ticker: str = "QQQ",
    score: float = 8.0,
    conf: str = "A",
    signal: str = "SETUP",
    dir_: str = "CALL",
) -> dict:
    return {
        "ticker": ticker,
        "engine_version": "5.2.0",
        "fixture_id": "qqq_canonical_v1",
        "fixture_version": "5.2.0",
        "score": score,
        "conf": conf,
        "signal": signal,
        "dir": dir_,
        "blocked": None,
        "error": False,
        "error_code": None,
        "layers": {"structure": {"pass": True, "override": False}},
        "ind": {"price": 500.0},
        "patterns": [{"cat": "TRIGGER", "w": 3.0, "sg": "CALL", "d": "P1"}],
        "sec_rel": None,
        "div_spy": None,
    }


@pytest_asyncio.fixture
async def app():
    app = create_app(
        valid_api_keys={"sk-test"},
        db_url="sqlite+aiosqlite:///:memory:",
    )
    # Triggerar startup (crea tablas)
    async with app.router.lifespan_context(app):
        yield app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _insert_signal(app, **kwargs) -> int:
    """Helper: usa la session_factory de la app para escribir."""
    factory = app.state.session_factory
    async with factory() as session:
        return await write_signal(session, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# GET /signals/latest
# ═══════════════════════════════════════════════════════════════════════════


class TestSignalsLatest:
    @pytest.mark.asyncio
    async def test_unauthenticated(self, client) -> None:
        r = await client.get("/api/v1/signals/latest")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_db_returns_empty_list(self, client) -> None:
        r = await client.get("/api/v1/signals/latest", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == []

    @pytest.mark.asyncio
    async def test_latest_per_slot(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        await _insert_signal(app, analyze_output=_make_output(ticker="QQQ"),
                             candle_timestamp=ts, slot_id=1)
        await _insert_signal(app, analyze_output=_make_output(ticker="SPY"),
                             candle_timestamp=ts, slot_id=2)

        r = await client.get("/api/v1/signals/latest", headers=AUTH)
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 2
        slots = {s["slot_id"] for s in items}
        assert slots == {1, 2}

    @pytest.mark.asyncio
    async def test_filter_by_slot_id(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        await _insert_signal(app, analyze_output=_make_output(),
                             candle_timestamp=ts, slot_id=1)
        await _insert_signal(app, analyze_output=_make_output(),
                             candle_timestamp=ts, slot_id=2)

        r = await client.get("/api/v1/signals/latest?slot_id=1", headers=AUTH)
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["slot_id"] == 1

    @pytest.mark.asyncio
    async def test_invalid_slot_id_returns_422(self, client) -> None:
        r = await client.get("/api/v1/signals/latest?slot_id=0", headers=AUTH)
        assert r.status_code == 422  # validation: ge=1


# ═══════════════════════════════════════════════════════════════════════════
# GET /signals/history
# ═══════════════════════════════════════════════════════════════════════════


class TestSignalsHistory:
    @pytest.mark.asyncio
    async def test_unauthenticated(self, client) -> None:
        r = await client.get("/api/v1/signals/history")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_empty_db(self, client) -> None:
        r = await client.get("/api/v1/signals/history", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"items": [], "next_cursor": None}

    @pytest.mark.asyncio
    async def test_pagination_cursor(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        for _ in range(10):
            await _insert_signal(app, analyze_output=_make_output(),
                                 candle_timestamp=ts, slot_id=1)

        # Página 1
        r = await client.get("/api/v1/signals/history?limit=3", headers=AUTH)
        body = r.json()
        assert len(body["items"]) == 3
        assert body["next_cursor"] is not None

        # Página 2 usando cursor
        cursor = body["next_cursor"]
        r = await client.get(
            f"/api/v1/signals/history?limit=3&cursor={cursor}", headers=AUTH,
        )
        body2 = r.json()
        assert len(body2["items"]) == 3
        # Los ids de página 2 son estrictamente menores al cursor
        assert all(s["id"] < cursor for s in body2["items"])

    @pytest.mark.asyncio
    async def test_limit_validation(self, client) -> None:
        r = await client.get("/api/v1/signals/history?limit=9999", headers=AUTH)
        # Validation: le=500
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_filter_by_slot(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        await _insert_signal(app, analyze_output=_make_output(),
                             candle_timestamp=ts, slot_id=1)
        await _insert_signal(app, analyze_output=_make_output(),
                             candle_timestamp=ts, slot_id=2)

        r = await client.get("/api/v1/signals/history?slot_id=1", headers=AUTH)
        body = r.json()
        assert all(s["slot_id"] == 1 for s in body["items"])


# ═══════════════════════════════════════════════════════════════════════════
# GET /signals/{id}
# ═══════════════════════════════════════════════════════════════════════════


class TestSignalById:
    @pytest.mark.asyncio
    async def test_unauthenticated(self, client) -> None:
        r = await client.get("/api/v1/signals/1")
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_nonexistent_returns_404(self, client) -> None:
        r = await client.get("/api/v1/signals/99999", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["detail"] == "Signal not found"

    @pytest.mark.asyncio
    async def test_returns_full_signal(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        sig_id = await _insert_signal(
            app, analyze_output=_make_output(), candle_timestamp=ts, slot_id=1,
        )
        r = await client.get(f"/api/v1/signals/{sig_id}", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == sig_id
        assert body["ticker"] == "QQQ"
        assert body["score"] == 8.0
        assert body["candles_snapshot_gzip_b64"] is None

    @pytest.mark.asyncio
    async def test_snapshot_returned_as_base64(self, app, client) -> None:
        ts = dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ)
        snapshot = b"\x1f\x8b\x08\x00fake_gzip_data"
        sig_id = await _insert_signal(
            app,
            analyze_output=_make_output(),
            candle_timestamp=ts,
            slot_id=1,
            candles_snapshot_gzip=snapshot,
        )
        r = await client.get(f"/api/v1/signals/{sig_id}", headers=AUTH)
        body = r.json()
        assert body["candles_snapshot_gzip_b64"] is not None
        decoded = base64.b64decode(body["candles_snapshot_gzip_b64"])
        assert decoded == snapshot


# ═══════════════════════════════════════════════════════════════════════════
# OpenAPI schema incluye los endpoints
# ═══════════════════════════════════════════════════════════════════════════


class TestOpenApiCoverage:
    @pytest.mark.asyncio
    async def test_all_signals_endpoints_documented(self, client) -> None:
        r = await client.get("/openapi.json")
        paths = r.json()["paths"]
        assert "/api/v1/signals/latest" in paths
        assert "/api/v1/signals/history" in paths
        assert "/api/v1/signals/{signal_id}" in paths


# ═══════════════════════════════════════════════════════════════════════════
# AR.3 — Transparent reads op + archive
# ═══════════════════════════════════════════════════════════════════════════


class TestTransparentReads:
    """/history y /{id} deben ver filas del archive cuando hay uno
    configurado en app.state."""

    @pytest_asyncio.fixture
    async def app_with_archive(self):
        from modules.db import Signal

        app = create_app(
            valid_api_keys={"sk-test"},
            db_url="sqlite+aiosqlite:///:memory:",
            archive_db_url="sqlite+aiosqlite:///:memory:",
        )
        async with app.router.lifespan_context(app):
            # 1 fila en archive (id=1, vieja) + 1 en op (id=10, fresca)
            now = dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
            archive_factory = app.state.archive_session_factory
            async with archive_factory() as ar:
                ar.add(Signal(
                    id=1, ticker="OLD",
                    engine_version="5.2.0",
                    fixture_id="qqq_canonical_v1", fixture_version="5.2.0",
                    compute_timestamp=now - dt.timedelta(days=400),
                    candle_timestamp=now - dt.timedelta(days=400),
                    score=3.0, conf="B", signal=False, blocked=False,
                    layers_json={}, ind_json={}, patterns_json=[],
                ))
                await ar.commit()
            async with app.state.session_factory() as op:
                op.add(Signal(
                    id=10, ticker="NEW",
                    engine_version="5.2.0",
                    fixture_id="qqq_canonical_v1", fixture_version="5.2.0",
                    compute_timestamp=now,
                    candle_timestamp=now,
                    score=7.0, conf="A", signal=True, blocked=False,
                    layers_json={}, ind_json={}, patterns_json=[],
                ))
                await op.commit()
            yield app

    @pytest.mark.asyncio
    async def test_history_merges_archive(self, app_with_archive) -> None:
        transport = ASGITransport(app=app_with_archive)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/signals/history", headers=AUTH)
        assert r.status_code == 200
        items = r.json()["items"]
        ids = [s["id"] for s in items]
        assert ids == [10, 1]

    @pytest.mark.asyncio
    async def test_by_id_hits_archive_when_missing_in_op(
        self, app_with_archive,
    ) -> None:
        transport = ASGITransport(app=app_with_archive)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/signals/1", headers=AUTH)
        assert r.status_code == 200
        assert r.json()["ticker"] == "OLD"

    @pytest.mark.asyncio
    async def test_by_id_404_when_in_neither(self, app_with_archive) -> None:
        transport = ASGITransport(app=app_with_archive)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/api/v1/signals/9999", headers=AUTH)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_history_without_archive_yields_only_op(
        self, client, app,
    ) -> None:
        """Regresión: app sin archive_db_url sigue respondiendo
        solo con filas de op (sin crash por el nuevo Depends)."""
        sig_id = await _insert_signal(
            app, analyze_output=_make_output(),
            candle_timestamp=dt.datetime(2026, 4, 22, 10, tzinfo=ET_TZ),
        )
        r = await client.get("/api/v1/signals/history", headers=AUTH)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()["items"]]
        assert ids == [sig_id]
