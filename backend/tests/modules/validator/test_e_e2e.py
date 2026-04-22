"""Tests del Check E — test end-to-end con `is_validator_test`."""

from __future__ import annotations

import pytest

from modules.validator.checks import e_e2e


@pytest.mark.asyncio
async def test_skip_when_no_executor() -> None:
    result = await e_e2e.run(scan_executor=None)
    assert result.status == "skip"
    assert "no provisto" in (result.message or "")


@pytest.mark.asyncio
async def test_pass_with_valid_output() -> None:
    """Executor devuelve output con shape esperada → pass."""

    async def executor() -> dict:
        return {
            "ticker": "QQQ",
            "signal": "NEUTRAL",
            "score": 0.0,
            "persisted": False,
            "id": None,
        }

    result = await e_e2e.run(scan_executor=executor)
    assert result.status == "pass"
    assert result.severity is None
    assert result.details["ticker"] == "QQQ"
    assert result.details["persisted"] is False


@pytest.mark.asyncio
async def test_fatal_when_executor_raises() -> None:
    async def executor() -> dict:
        raise RuntimeError("fetch timeout")

    result = await e_e2e.run(scan_executor=executor)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "fetch timeout" in (result.message or "")


@pytest.mark.asyncio
async def test_fatal_when_executor_returns_non_dict() -> None:
    async def executor():  # type: ignore[no-untyped-def]
        return ["not", "a", "dict"]

    result = await e_e2e.run(scan_executor=executor)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "dict" in (result.message or "")


@pytest.mark.asyncio
async def test_fatal_when_output_missing_keys() -> None:
    """El pipeline debe devolver al menos ticker/signal/score/persisted."""

    async def executor() -> dict:
        return {"ticker": "QQQ"}  # faltan signal, score, persisted

    result = await e_e2e.run(scan_executor=executor)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "signal" in (result.message or "")


@pytest.mark.asyncio
async def test_fatal_when_executor_persisted_true() -> None:
    """Si el executor persistió, es un bug del wiring — is_validator_test
    debe usar persist=False."""

    async def executor() -> dict:
        return {
            "ticker": "QQQ",
            "signal": "NEUTRAL",
            "score": 0.0,
            "persisted": True,  # bug: no debería haberse persistido
            "id": 42,
        }

    result = await e_e2e.run(scan_executor=executor)
    assert result.status == "fail"
    assert result.severity == "fatal"
    assert "persist=False" in (result.message or "")
