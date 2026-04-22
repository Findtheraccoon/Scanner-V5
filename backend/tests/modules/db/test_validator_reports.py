"""Tests del persistence layer para reportes del Validator (AR.4)."""

from __future__ import annotations

import datetime as _dt

import pytest
import pytest_asyncio

from modules.db import (
    ET_TZ,
    init_db,
    make_engine,
    make_session_factory,
    read_validator_report_by_id,
    read_validator_reports_history,
    read_validator_reports_latest,
    write_validator_report,
)
from modules.validator import TestResult, ValidatorReport


def _report(
    *,
    run_id: str = "r-1",
    started_at: _dt.datetime | None = None,
    tests_count: int = 7,
    all_status: str = "skip",
) -> ValidatorReport:
    started_at = started_at or _dt.datetime(2026, 4, 22, 10, 0, tzinfo=ET_TZ)
    ids = ("D", "A", "B", "C", "E", "F", "G")[:tests_count]
    tests = [TestResult(test_id=t, status=all_status) for t in ids]
    return ValidatorReport(
        run_id=run_id,
        started_at=started_at,
        finished_at=started_at + _dt.timedelta(seconds=5),
        tests=tests,
    )


@pytest_asyncio.fixture
async def op_factory():
    engine = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    yield make_session_factory(engine)
    await engine.dispose()


@pytest_asyncio.fixture
async def op_and_archive():
    op = make_engine("sqlite+aiosqlite:///:memory:")
    ar = make_engine("sqlite+aiosqlite:///:memory:")
    await init_db(op)
    await init_db(ar)
    yield make_session_factory(op), make_session_factory(ar)
    await op.dispose()
    await ar.dispose()


class TestWrite:
    @pytest.mark.asyncio
    async def test_persists_and_returns_id(self, op_factory) -> None:
        async with op_factory() as session:
            rec_id = await write_validator_report(
                session, report=_report(), trigger="manual",
            )
        assert rec_id == 1

    @pytest.mark.asyncio
    async def test_two_reports_get_sequential_ids(self, op_factory) -> None:
        async with op_factory() as session:
            id1 = await write_validator_report(
                session, report=_report(run_id="r-1"), trigger="startup",
            )
            id2 = await write_validator_report(
                session, report=_report(run_id="r-2"), trigger="manual",
            )
        assert (id1, id2) == (1, 2)

    @pytest.mark.asyncio
    async def test_tests_preserved_as_json(self, op_factory) -> None:
        r = _report(all_status="pass")
        async with op_factory() as session:
            rec_id = await write_validator_report(
                session, report=r, trigger="manual",
            )
            roundtrip = await read_validator_report_by_id(session, rec_id)
        assert roundtrip is not None
        assert len(roundtrip["tests"]) == 7
        assert all(t["status"] == "pass" for t in roundtrip["tests"])


class TestReadLatest:
    @pytest.mark.asyncio
    async def test_none_when_empty(self, op_factory) -> None:
        async with op_factory() as session:
            assert await read_validator_reports_latest(session) is None

    @pytest.mark.asyncio
    async def test_picks_most_recent_by_started_at(
        self, op_factory,
    ) -> None:
        base = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)
        async with op_factory() as session:
            for i in range(3):
                await write_validator_report(
                    session,
                    report=_report(
                        run_id=f"r-{i}",
                        started_at=base + _dt.timedelta(hours=i),
                    ),
                    trigger="manual",
                )
            latest = await read_validator_reports_latest(session)
        assert latest is not None
        assert latest["run_id"] == "r-2"

    @pytest.mark.asyncio
    async def test_archive_fallback_when_op_empty(
        self, op_and_archive,
    ) -> None:
        op_f, ar_f = op_and_archive
        async with ar_f() as ar:
            await write_validator_report(
                ar, report=_report(run_id="old"), trigger="startup",
            )
        async with op_f() as op, ar_f() as ar:
            latest = await read_validator_reports_latest(
                op, archive_session=ar,
            )
        assert latest is not None
        assert latest["run_id"] == "old"


class TestReadHistory:
    @pytest.mark.asyncio
    async def test_empty(self, op_factory) -> None:
        async with op_factory() as session:
            items, cur = await read_validator_reports_history(session)
        assert items == []
        assert cur is None

    @pytest.mark.asyncio
    async def test_ordered_desc_by_id(self, op_factory) -> None:
        async with op_factory() as session:
            for i in range(5):
                await write_validator_report(
                    session,
                    report=_report(run_id=f"r-{i}"),
                    trigger="manual",
                )
            items, _ = await read_validator_reports_history(session, limit=10)
        assert [it["run_id"] for it in items] == [
            "r-4", "r-3", "r-2", "r-1", "r-0",
        ]

    @pytest.mark.asyncio
    async def test_cursor_pagination(self, op_factory) -> None:
        async with op_factory() as session:
            for i in range(5):
                await write_validator_report(
                    session,
                    report=_report(run_id=f"r-{i}"),
                    trigger="manual",
                )
            first, cur = await read_validator_reports_history(session, limit=2)
            assert [it["run_id"] for it in first] == ["r-4", "r-3"]
            assert cur is not None
            second, cur2 = await read_validator_reports_history(
                session, cursor=cur, limit=2,
            )
        assert [it["run_id"] for it in second] == ["r-2", "r-1"]
        assert cur2 is not None

    @pytest.mark.asyncio
    async def test_filter_by_trigger(self, op_factory) -> None:
        async with op_factory() as session:
            await write_validator_report(
                session, report=_report(run_id="a"), trigger="startup",
            )
            await write_validator_report(
                session, report=_report(run_id="b"), trigger="manual",
            )
            await write_validator_report(
                session, report=_report(run_id="c"), trigger="hot_reload",
            )
            items, _ = await read_validator_reports_history(
                session, trigger="startup",
            )
        assert [it["run_id"] for it in items] == ["a"]
        assert items[0]["trigger"] == "startup"

    @pytest.mark.asyncio
    async def test_filter_by_overall_status(self, op_factory) -> None:
        async with op_factory() as session:
            await write_validator_report(
                session, report=_report(run_id="a", all_status="pass"),
                trigger="manual",
            )
            await write_validator_report(
                session, report=_report(run_id="b", all_status="skip"),
                trigger="manual",
            )
            items, _ = await read_validator_reports_history(
                session, overall_status="pass",
            )
        # all_status=pass → ValidatorReport.overall_status=pass
        assert [it["run_id"] for it in items] == ["a"]

    @pytest.mark.asyncio
    async def test_merges_op_and_archive(self, op_and_archive) -> None:
        """Los ids en op+archive NO colisionan en uso real porque la
        rotación copia el id del op al archive y después lo borra en
        op. En este test simulamos ese estado con ids explícitos."""
        from modules.db import ValidatorReportRecord

        op_f, ar_f = op_and_archive
        base = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)

        async with ar_f() as ar:
            ar.add(ValidatorReportRecord(
                id=1, run_id="old", trigger="startup",
                started_at=base - _dt.timedelta(days=60),
                finished_at=base - _dt.timedelta(days=60),
                overall_status="pass", tests_json=[],
            ))
            await ar.commit()
        async with op_f() as op:
            op.add(ValidatorReportRecord(
                id=2, run_id="new", trigger="manual",
                started_at=base,
                finished_at=base,
                overall_status="pass", tests_json=[],
            ))
            await op.commit()

        async with op_f() as op, ar_f() as ar:
            items, _ = await read_validator_reports_history(
                op, archive_session=ar, limit=10,
            )
        run_ids = [it["run_id"] for it in items]
        assert run_ids == ["new", "old"]


class TestReadById:
    @pytest.mark.asyncio
    async def test_none_when_not_found(self, op_factory) -> None:
        async with op_factory() as session:
            assert await read_validator_report_by_id(session, 9999) is None

    @pytest.mark.asyncio
    async def test_found_in_archive_when_missing_in_op(
        self, op_and_archive,
    ) -> None:
        op_f, ar_f = op_and_archive
        async with ar_f() as ar:
            rec_id = await write_validator_report(
                ar, report=_report(run_id="old"), trigger="startup",
            )
        async with op_f() as op, ar_f() as ar:
            result = await read_validator_report_by_id(
                op, rec_id, archive_session=ar,
            )
        assert result is not None
        assert result["run_id"] == "old"


class TestRotationIncludesReports:
    @pytest.mark.asyncio
    async def test_rotation_moves_old_reports_to_archive(
        self, op_and_archive,
    ) -> None:
        from engines.database.rotation import rotate_with_archive

        op_f, ar_f = op_and_archive
        now = _dt.datetime(2026, 4, 22, tzinfo=ET_TZ)

        # 1 reporte vencido (60 días) + 1 fresco (10 días)
        async with op_f() as op:
            await write_validator_report(
                op,
                report=_report(
                    run_id="old",
                    started_at=now - _dt.timedelta(days=60),
                ),
                trigger="startup",
            )
            await write_validator_report(
                op,
                report=_report(
                    run_id="new",
                    started_at=now - _dt.timedelta(days=10),
                ),
                trigger="manual",
            )

        async with op_f() as op, ar_f() as ar:
            result = await rotate_with_archive(op, ar, now=now)

        assert result["validator_reports"]["archived"] == 1
        assert result["validator_reports"]["deleted"] == 1

        # Op queda con `new`; archive tiene `old`
        async with op_f() as op:
            items, _ = await read_validator_reports_history(op)
        assert [it["run_id"] for it in items] == ["new"]

        async with ar_f() as ar:
            items_ar, _ = await read_validator_reports_history(ar)
        assert [it["run_id"] for it in items_ar] == ["old"]
