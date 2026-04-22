"""Tests de los modelos del Validator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from modules.validator import (
    TEST_DESCRIPTIONS,
    TEST_ORDER,
    TestResult,
    ValidatorReport,
)


class TestConstants:
    def test_test_order_is_d_first(self) -> None:
        """Spec §3.2: orden canónico D → A → B → C → E → F → G."""
        assert TEST_ORDER == ("D", "A", "B", "C", "E", "F", "G")

    def test_descriptions_cover_all_tests(self) -> None:
        assert set(TEST_DESCRIPTIONS.keys()) == set(TEST_ORDER)


class TestTestResult:
    def test_pass_minimal(self) -> None:
        r = TestResult(test_id="D", status="pass")
        assert r.severity is None
        assert r.error_code is None
        assert r.details == {}
        assert r.duration_ms == 0.0

    def test_fail_fatal(self) -> None:
        r = TestResult(
            test_id="D",
            status="fail",
            severity="fatal",
            message="DB no accesible",
            error_code="ENG-001",
        )
        assert r.severity == "fatal"
        assert r.error_code == "ENG-001"

    def test_frozen_cannot_mutate(self) -> None:
        r = TestResult(test_id="D", status="pass")
        with pytest.raises(ValidationError):
            r.status = "fail"  # type: ignore[misc]

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TestResult(test_id="D", status="pass", unknown=1)  # type: ignore[call-arg]


class TestValidatorReportOverallStatus:
    def _report(self, tests: list[TestResult]) -> ValidatorReport:
        return ValidatorReport(
            run_id="r1",
            started_at=datetime(2026, 4, 22, tzinfo=UTC),
            finished_at=datetime(2026, 4, 22, tzinfo=UTC),
            tests=tests,
        )

    def test_all_pass_is_pass(self) -> None:
        r = self._report([
            TestResult(test_id=t, status="pass") for t in TEST_ORDER
        ])
        assert r.overall_status == "pass"

    def test_pass_with_skip_is_pass(self) -> None:
        r = self._report([
            TestResult(test_id="D", status="pass"),
            *[TestResult(test_id=t, status="skip") for t in TEST_ORDER[1:]],
        ])
        assert r.overall_status == "pass"

    def test_all_skip_is_partial(self) -> None:
        r = self._report([
            TestResult(test_id=t, status="skip") for t in TEST_ORDER
        ])
        assert r.overall_status == "partial"

    def test_fail_fatal_is_fail(self) -> None:
        r = self._report([
            TestResult(test_id="D", status="fail", severity="fatal"),
            *[TestResult(test_id=t, status="skip") for t in TEST_ORDER[1:]],
        ])
        assert r.overall_status == "fail"

    def test_fail_warning_is_partial(self) -> None:
        r = self._report([
            TestResult(test_id="D", status="pass"),
            TestResult(test_id="A", status="fail", severity="warning"),
            *[TestResult(test_id=t, status="skip") for t in TEST_ORDER[2:]],
        ])
        assert r.overall_status == "partial"

    def test_fail_degraded_is_partial(self) -> None:
        r = self._report([
            TestResult(test_id="D", status="pass"),
            TestResult(test_id="A", status="fail", severity="degraded"),
            *[TestResult(test_id=t, status="skip") for t in TEST_ORDER[2:]],
        ])
        assert r.overall_status == "partial"
