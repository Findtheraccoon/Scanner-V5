"""Tests del log writer del Validator (TXT a /LOG/)."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from modules.validator import TestResult, ValidatorReport
from modules.validator.log_writer import write_report_log


def _report(tests: list[TestResult] | None = None) -> ValidatorReport:
    return ValidatorReport(
        run_id="abc12345-0000-0000-0000-000000000000",
        started_at=datetime(2026, 4, 22, 10, 30, 0, tzinfo=UTC),
        finished_at=datetime(2026, 4, 22, 10, 30, 5, tzinfo=UTC),
        tests=tests or [
            TestResult(test_id=t, status="skip") for t in
            ("D", "A", "B", "C", "E", "F", "G")
        ],
    )


class TestWrite:
    def test_creates_file_with_stamp_and_short_run_id(
        self, tmp_path: Path,
    ) -> None:
        r = _report()
        target = write_report_log(r, tmp_path)
        assert target.exists()
        assert target.name.startswith("validator-20260422-103000-abc12345")
        assert target.suffix == ".txt"

    def test_includes_run_id_and_overall_status(self, tmp_path: Path) -> None:
        r = _report()
        target = write_report_log(r, tmp_path)
        text = target.read_text()
        assert r.run_id in text
        assert "overall_status:" in text

    def test_includes_all_tests_in_canonical_order(
        self, tmp_path: Path,
    ) -> None:
        r = _report()
        target = write_report_log(r, tmp_path)
        text = target.read_text()
        # Los test headers deben aparecer en orden D → A → B → C → E → F → G
        idx_d = text.index("[D]")
        idx_a = text.index("[A]")
        idx_g = text.index("[G]")
        assert idx_d < idx_a < idx_g

    def test_fail_test_includes_severity_and_error_code(
        self, tmp_path: Path,
    ) -> None:
        r = _report(tests=[
            TestResult(
                test_id="D", status="fail", severity="fatal",
                error_code="ENG-001", message="DB down",
                details={"sub": "checks"},
            ),
            *[TestResult(test_id=t, status="skip") for t in
              ("A", "B", "C", "E", "F", "G")],
        ])
        target = write_report_log(r, tmp_path)
        text = target.read_text()
        assert "severity: fatal" in text
        assert "error_code: ENG-001" in text
        assert "message: DB down" in text
        assert '"sub": "checks"' in text

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "LOG" / "nested"
        target = write_report_log(_report(), nested)
        assert target.is_file()

    def test_pass_test_has_no_severity_line(self, tmp_path: Path) -> None:
        r = _report(tests=[
            TestResult(test_id="D", status="pass"),
            *[TestResult(test_id=t, status="skip") for t in
              ("A", "B", "C", "E", "F", "G")],
        ])
        target = write_report_log(r, tmp_path)
        text = target.read_text()
        d_section = text.split("[D]")[1].split("[A]")[0]
        assert "severity:" not in d_section
        assert "error_code:" not in d_section


class TestRotation:
    def test_old_files_deleted(self, tmp_path: Path) -> None:
        """Archivos validator-*.txt más viejos que retention se borran."""
        # Crear un archivo viejo (mtime 10 días atrás)
        old = tmp_path / "validator-20200101-000000-oldold12.txt"
        old.write_text("old")
        old_mtime = time.time() - (10 * 86400)
        os.utime(old, (old_mtime, old_mtime))

        target = write_report_log(_report(), tmp_path, retention_days=5)
        assert target.exists()
        assert not old.exists()

    def test_recent_files_kept(self, tmp_path: Path) -> None:
        """Archivos recientes no se tocan."""
        recent = tmp_path / "validator-99990101-000000-recent12.txt"
        recent.write_text("recent")
        # mtime = ahora (default)
        write_report_log(_report(), tmp_path, retention_days=5)
        assert recent.exists()

    def test_non_validator_files_kept(self, tmp_path: Path) -> None:
        """Archivos que no matchean validator-*.txt no se rotan."""
        other = tmp_path / "other.log"
        other.write_text("keep")
        os.utime(other, (time.time() - (10 * 86400),) * 2)

        write_report_log(_report(), tmp_path, retention_days=5)
        assert other.exists()
