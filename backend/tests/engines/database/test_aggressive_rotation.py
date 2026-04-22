"""Tests de `check_and_rotate_aggressive` (§9.4 retención agresiva)."""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest
import pytest_asyncio

from engines.database.rotation import (
    AGGRESSIVE_RETENTION_POLICIES,
    DEFAULT_RETENTION_POLICIES,
    DEFAULT_SIZE_LIMIT_MB,
    check_and_rotate_aggressive,
)
from modules.db import (
    ET_TZ,
    Signal,
    init_db,
    make_engine,
    make_session_factory,
)


class TestPolicies:
    def test_aggressive_is_shorter_than_default(self) -> None:
        """Cada política agresiva es <= la normal (heartbeat es igual)."""
        for table, normal in DEFAULT_RETENTION_POLICIES.items():
            aggressive = AGGRESSIVE_RETENTION_POLICIES[table]
            assert aggressive <= normal, (
                f"{table}: aggressive={aggressive} > normal={normal}"
            )

    def test_default_size_limit_is_5gb(self) -> None:
        assert DEFAULT_SIZE_LIMIT_MB == 5000


@pytest_asyncio.fixture
async def op_and_archive_file(tmp_path):
    """Archive + op con DB de archivo (no :memory:) para poder medir
    `.stat().st_size`."""
    op_path = tmp_path / "op.db"
    ar_path = tmp_path / "archive.db"
    op_engine = make_engine(f"sqlite+aiosqlite:///{op_path}")
    ar_engine = make_engine(f"sqlite+aiosqlite:///{ar_path}")
    await init_db(op_engine)
    await init_db(ar_engine)
    yield make_session_factory(op_engine), make_session_factory(ar_engine), op_path
    await op_engine.dispose()
    await ar_engine.dispose()


def _sig(days_ago: int, ticker: str = "QQQ") -> Signal:
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


class TestBelowThreshold:
    @pytest.mark.asyncio
    async def test_no_op_when_under_limit(
        self, op_and_archive_file,
    ) -> None:
        op_f, ar_f, op_path = op_and_archive_file

        # Inserto algo viejo que SÍ sería purgado si disparara — pero
        # como el tamaño está muy debajo del umbral, no se dispara.
        async with op_f() as op:
            op.add(_sig(days_ago=200))
            await op.commit()

        async with op_f() as op, ar_f() as ar:
            result = await check_and_rotate_aggressive(
                op, ar, op_path, size_limit_mb=999999,  # umbral alto
            )

        assert result["triggered"] is False
        assert result["rotation"] is None
        assert result["vacuum_recommended"] is False
        # El row viejo sigue en op
        from sqlalchemy import select
        async with op_f() as op:
            rows = (await op.execute(select(Signal))).scalars().all()
            assert len(rows) == 1


class TestAboveThreshold:
    @pytest.mark.asyncio
    async def test_triggers_when_over_limit(
        self, op_and_archive_file,
    ) -> None:
        op_f, ar_f, op_path = op_and_archive_file

        # Dos filas: una vencida bajo política agresiva (200 días),
        # otra fresca (30 días).
        now = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
        async with op_f() as op:
            op.add(_sig(days_ago=200, ticker="OLD"))
            op.add(_sig(days_ago=30, ticker="NEW"))
            await op.commit()

        # Umbral diminuto (0.001 MB) para forzar trigger independiente
        # del tamaño real de SQLite.
        async with op_f() as op, ar_f() as ar:
            result = await check_and_rotate_aggressive(
                op, ar, op_path, size_limit_mb=0, now=now,
            )

        assert result["triggered"] is True
        assert result["vacuum_recommended"] is True
        rot = result["rotation"]
        # signals política agresiva = 180 días. Fila de 200 días pasa,
        # fila de 30 no.
        assert rot["signals"]["archived"] == 1
        assert rot["signals"]["deleted"] == 1

        # Op queda con NEW, archive tiene OLD
        from sqlalchemy import select
        async with op_f() as op:
            rows = (await op.execute(select(Signal))).scalars().all()
        assert [r.ticker for r in rows] == ["NEW"]
        async with ar_f() as ar:
            rows = (await ar.execute(select(Signal))).scalars().all()
        assert [r.ticker for r in rows] == ["OLD"]

    @pytest.mark.asyncio
    async def test_size_reported_before_and_after(
        self, op_and_archive_file,
    ) -> None:
        op_f, ar_f, op_path = op_and_archive_file
        # Forzar que el archivo tenga bytes para medir
        # Ya creado por init_db — no-op adicional
        async with op_f() as op, ar_f() as ar:
            result = await check_and_rotate_aggressive(
                op, ar, op_path, size_limit_mb=0,
            )
        assert result["size_mb_before"] > 0
        assert result["size_mb_after"] >= 0

    @pytest.mark.asyncio
    async def test_missing_file_returns_zero_size(
        self, tmp_path: Path,
    ) -> None:
        """Si el path no existe (`:memory:` caso), size=0 y no dispara."""
        op_engine = make_engine("sqlite+aiosqlite:///:memory:")
        ar_engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_db(op_engine)
        await init_db(ar_engine)
        op_f = make_session_factory(op_engine)
        ar_f = make_session_factory(ar_engine)

        try:
            ghost = tmp_path / "ghost.db"
            async with op_f() as op, ar_f() as ar:
                result = await check_and_rotate_aggressive(
                    op, ar, ghost, size_limit_mb=100,
                )
            # size=0 < 100 → no dispara
            assert result["triggered"] is False
            assert result["size_mb_before"] == 0.0
        finally:
            await op_engine.dispose()
            await ar_engine.dispose()
