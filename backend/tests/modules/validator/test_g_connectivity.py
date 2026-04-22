"""Tests del Check G — conectividad externa (TD + S3)."""

from __future__ import annotations

import pytest

from modules.validator.checks import g_connectivity


@pytest.mark.asyncio
async def test_skip_when_no_probes() -> None:
    result = await g_connectivity.run(td_probe=None, s3_probe=None)
    assert result.status == "skip"
    assert "sin probes" in (result.message or "")


@pytest.mark.asyncio
async def test_pass_when_all_tds_ok_and_no_s3() -> None:
    async def td() -> list[dict]:
        return [
            {"key_id": "k1", "ok": True},
            {"key_id": "k2", "ok": True},
        ]

    result = await g_connectivity.run(td_probe=td, s3_probe=None)
    assert result.status == "pass"
    assert result.severity is None
    assert len(result.details["twelvedata"]) == 2
    assert "s3" not in result.details


@pytest.mark.asyncio
async def test_pass_when_tds_and_s3_ok() -> None:
    async def td() -> list[dict]:
        return [{"key_id": "k1", "ok": True}]

    async def s3() -> dict:
        return {"ok": True}

    result = await g_connectivity.run(td_probe=td, s3_probe=s3)
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_warning_when_one_td_fails() -> None:
    async def td() -> list[dict]:
        return [
            {"key_id": "k1", "ok": True},
            {"key_id": "k2", "ok": False, "error": "401"},
        ]

    result = await g_connectivity.run(td_probe=td, s3_probe=None)
    assert result.status == "fail"
    assert result.severity == "warning"
    assert "1/2" in (result.message or "")


@pytest.mark.asyncio
async def test_fatal_when_all_tds_fail() -> None:
    async def td() -> list[dict]:
        return [
            {"key_id": "k1", "ok": False, "error": "timeout"},
            {"key_id": "k2", "ok": False, "error": "401"},
        ]

    result = await g_connectivity.run(td_probe=td, s3_probe=None)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "todas las 2" in (result.message or "")


@pytest.mark.asyncio
async def test_warning_when_s3_fails_but_tds_ok() -> None:
    async def td() -> list[dict]:
        return [{"key_id": "k1", "ok": True}]

    async def s3() -> dict:
        return {"ok": False, "error": "bucket not found"}

    result = await g_connectivity.run(td_probe=td, s3_probe=s3)
    assert result.status == "fail"
    assert result.severity == "warning"
    assert "S3" in (result.message or "")


@pytest.mark.asyncio
async def test_td_probe_exception_treated_as_all_fail() -> None:
    """Si td_probe lanza, se trata como 0 keys OK → fatal si es la única info."""
    async def td() -> list[dict]:
        raise RuntimeError("network error")

    result = await g_connectivity.run(td_probe=td, s3_probe=None)
    # 0 keys (lista vacía), no hay fatal path porque td_total==0
    # Entonces cae en warning
    assert result.status == "fail"
    assert result.severity == "warning"
    assert "twelvedata_error" in result.details


@pytest.mark.asyncio
async def test_s3_probe_exception_reported_as_failure() -> None:
    async def td() -> list[dict]:
        return [{"key_id": "k1", "ok": True}]

    async def s3() -> dict:
        raise RuntimeError("conn refused")

    result = await g_connectivity.run(td_probe=td, s3_probe=s3)
    assert result.status == "fail"
    assert result.severity == "warning"
    assert result.details["s3"]["ok"] is False
