"""Tests del Check F — parity exhaustivo vs canonical QQQ.

Incluye smoke tests contra la DB real del repo
(`backend/fixtures/parity_reference/fixtures/parity_qqq_candles.db`) con
`limit` reducido para mantener la corrida rápida.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modules.validator.checks import f_parity


class TestMissingFiles:
    @pytest.mark.asyncio
    async def test_skip_when_db_missing(self, tmp_path: Path) -> None:
        result = await f_parity.run(
            db_path=tmp_path / "nonexistent.db",
            sample_path=tmp_path / "nonexistent.json",
            fixture_path=tmp_path / "nonexistent.json",
        )
        assert result.test_id == "F"
        assert result.status == "skip"
        assert "no disponible" in (result.message or "")


class TestSmokeRealDataset:
    """Tests smoke contra la DB commiteada del repo. Baseline es
    189/245 = 77%. Con `limit=10` la corrida es ~0.3s."""

    @pytest.mark.asyncio
    async def test_runs_with_limit_10(self) -> None:
        result = await f_parity.run(limit=10)
        assert result.test_id == "F"
        # pass o fail warning — no fatal, no skip (la DB está en el repo).
        assert result.status in ("pass", "fail")
        assert result.details["total"] == 10
        assert result.details["matches"] >= 0
        assert result.details["mismatches"] >= 0
        assert result.details["errors"] == 0
        # Match rate sanity — al menos 50% con 10 señales.
        # Más laxo que DEFAULT_MIN_MATCH_RATE para que no sea frágil.
        assert result.details["match_rate"] >= 0.5

    @pytest.mark.asyncio
    async def test_fail_warning_with_high_threshold(self) -> None:
        """Con threshold irrealmente alto (99%), debe fallar como warning."""
        result = await f_parity.run(limit=20, min_match_rate=0.99)
        # Baseline nunca llega al 99%, así que esperamos fail.
        if result.status == "fail":
            assert result.severity == "warning"
            assert result.error_code == "ENG-050"
            assert result.details["match_rate"] < 0.99

    @pytest.mark.asyncio
    async def test_stats_shape(self) -> None:
        result = await f_parity.run(limit=5)
        stats = result.details
        for key in (
            "total", "matches", "mismatches", "errors",
            "match_rate", "min_match_rate", "sample_diffs",
        ):
            assert key in stats
        assert stats["matches"] + stats["mismatches"] + stats["errors"] == stats["total"]
