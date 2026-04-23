"""Tests del watchdog automático de rotación agresiva (§9.4)."""

from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
from pathlib import Path

import pytest
import pytest_asyncio

from engines.database import aggressive_rotation_watchdog
from modules.db import (
    ET_TZ,
    Signal,
    init_db,
    make_engine,
    make_session_factory,
)


@pytest_asyncio.fixture
async def op_archive_file(tmp_path):
    """Op + archive con archivos reales para `.stat().st_size`."""
    op_path = tmp_path / "op.db"
    ar_path = tmp_path / "archive.db"
    op_engine = make_engine(f"sqlite+aiosqlite:///{op_path}")
    ar_engine = make_engine(f"sqlite+aiosqlite:///{ar_path}")
    await init_db(op_engine)
    await init_db(ar_engine)
    op_f = make_session_factory(op_engine)
    ar_f = make_session_factory(ar_engine)
    yield op_f, ar_f, op_path
    await op_engine.dispose()
    await ar_engine.dispose()


def _old_sig(days_ago: int, ticker: str = "QQQ") -> Signal:
    now = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
    ts = now - _dt.timedelta(days=days_ago)
    return Signal(
        ticker=ticker,
        engine_version="5.2.0",
        fixture_id="qqq_test", fixture_version="5.2.0",
        compute_timestamp=ts, candle_timestamp=ts,
        score=5.0, conf="NEUTRAL", signal=False, blocked=False,
        layers_json={}, ind_json={}, patterns_json=[],
    )


class TestWatchdogUnderLimit:
    @pytest.mark.asyncio
    async def test_no_op_when_under_limit(self, op_archive_file) -> None:
        """Con umbral gigante, el watchdog corre pero no dispara
        rotación. El row viejo se mantiene."""
        op_f, ar_f, op_path = op_archive_file
        async with op_f() as op:
            op.add(_old_sig(200))
            await op.commit()

        task = asyncio.create_task(
            aggressive_rotation_watchdog(
                op_f, ar_f, op_path,
                size_limit_mb=999999,
                interval_s=0.05,
            ),
            name="wd",
        )
        await asyncio.sleep(0.15)  # 2-3 ticks
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        from sqlalchemy import select
        async with op_f() as op:
            rows = (await op.execute(select(Signal))).scalars().all()
        assert len(rows) == 1  # no se tocó


class TestWatchdogTriggers:
    @pytest.mark.asyncio
    async def test_fires_when_over_limit(self, op_archive_file) -> None:
        """Con umbral 0 MB, dispara al primer tick y mueve al archive."""
        op_f, ar_f, op_path = op_archive_file
        async with op_f() as op:
            op.add(_old_sig(200, ticker="OLD"))
            op.add(_old_sig(30, ticker="NEW"))
            await op.commit()

        task = asyncio.create_task(
            aggressive_rotation_watchdog(
                op_f, ar_f, op_path,
                size_limit_mb=0,
                interval_s=0.05,
            ),
            name="wd2",
        )
        await asyncio.sleep(0.15)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        from sqlalchemy import select
        async with op_f() as op:
            remaining = [r.ticker for r in (
                await op.execute(select(Signal))
            ).scalars().all()]
        # Policy agresiva signals=180d. Fila 200d pasó, 30d quedó.
        assert remaining == ["NEW"]
        async with ar_f() as ar:
            archived = [r.ticker for r in (
                await ar.execute(select(Signal))
            ).scalars().all()]
        assert archived == ["OLD"]


class TestWatchdogResilience:
    @pytest.mark.asyncio
    async def test_survives_rotation_exception(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        """Si rotate_with_archive lanza, el watchdog loguea y sigue."""
        op_engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'op.db'}")
        ar_engine = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'ar.db'}")
        await init_db(op_engine)
        await init_db(ar_engine)
        op_f = make_session_factory(op_engine)
        ar_f = make_session_factory(ar_engine)

        # Monkey-patch check_and_rotate_aggressive para lanzar
        from engines.database import watchdog as wd_mod

        call_count = {"n": 0}

        async def _raises(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated rotation error")
            return {
                "triggered": False,
                "size_mb_before": 0.0,
                "size_mb_after": 0.0,
                "size_limit_mb": 5000,
                "rotation": None,
                "vacuum_recommended": False,
            }

        monkeypatch.setattr(
            wd_mod, "check_and_rotate_aggressive", _raises,
        )

        try:
            task = asyncio.create_task(
                aggressive_rotation_watchdog(
                    op_f, ar_f, tmp_path / "op.db",
                    size_limit_mb=5000,
                    interval_s=0.05,
                ),
                name="wd3",
            )
            await asyncio.sleep(0.15)
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            # Al menos 2 ticks: el primero lanzó, el segundo no.
            assert call_count["n"] >= 2
        finally:
            await op_engine.dispose()
            await ar_engine.dispose()
