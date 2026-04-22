"""Tests de `RegistryRuntime` (SR.1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from engines.registry_runtime import RegistryRuntime
from modules.fixtures import Fixture
from modules.slot_registry import RegistryMetadata, SlotRecord, SlotRegistry


def _fixture_dict(fixture_id: str = "qqq_test") -> dict:
    from modules.fixtures import CONFIRM_CATEGORIES

    return {
        "metadata": {
            "fixture_id": fixture_id,
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "test",
        },
        "ticker_info": {
            "ticker": "QQQ",
            "benchmark": "SPY",
            "requires_spy_daily": True,
            "requires_bench_daily": True,
        },
        "confirm_weights": dict.fromkeys(CONFIRM_CATEGORIES, 1.0),
        "detection_thresholds": {
            "fzarel_min_divergence_pct": 0.5,
            "divspy_asset_threshold_pct": 0.5,
            "divspy_spy_threshold_pct": 0.3,
            "volhigh_min_ratio": 1.2,
        },
        "score_bands": [
            {"min": 2.0, "max": None, "label": "OK", "signal": "REVISAR"},
        ],
    }


def _fixture(fixture_id: str = "qqq_test") -> Fixture:
    return Fixture.model_validate(_fixture_dict(fixture_id))


def _metadata() -> RegistryMetadata:
    return RegistryMetadata(
        registry_version="1.0.0",
        engine_version_required=">=5.2.0,<6.0.0",
        generated_at=datetime(2026, 4, 22, tzinfo=UTC),
        description="test",
    )


def _slot(
    n: int,
    *,
    status: str = "OPERATIVE",
    ticker: str | None = "QQQ",
    with_fixture: bool = True,
) -> SlotRecord:
    return SlotRecord(
        slot=n,
        status=status,  # type: ignore[arg-type]
        ticker=ticker,
        fixture_path=f"fixtures/slot{n}.json" if with_fixture else None,
        fixture=_fixture() if with_fixture and status == "OPERATIVE" else None,
        benchmark="SPY",
        priority=None,
        notes=None,
        error_code=None if status != "DEGRADED" else "REG-010",
        error_detail=None if status != "DEGRADED" else "broken",
    )


def _registry(slots: list[SlotRecord]) -> SlotRegistry:
    # Complete 6 slots (fill with DISABLED if less)
    by_num = {s.slot: s for s in slots}
    full = []
    for i in range(1, 7):
        if i in by_num:
            full.append(by_num[i])
        else:
            full.append(
                SlotRecord(
                    slot=i, status="DISABLED", ticker=None,
                    fixture_path=None, fixture=None, benchmark=None,
                ),
            )
    return SlotRegistry(metadata=_metadata(), slots=full, warnings=[])


# ═══════════════════════════════════════════════════════════════════════════
# list_scannable_tickers
# ═══════════════════════════════════════════════════════════════════════════


class TestListScannableTickers:
    @pytest.mark.asyncio
    async def test_empty_registry(self) -> None:
        rt = RegistryRuntime(_registry([]))
        assert await rt.list_scannable_tickers() == []

    @pytest.mark.asyncio
    async def test_operative_slots_returned(self) -> None:
        rt = RegistryRuntime(_registry([
            _slot(1, ticker="QQQ"),
            _slot(2, ticker="SPY"),
            _slot(3, status="DEGRADED", ticker="AAPL"),
            _slot(5, status="DISABLED", ticker=None, with_fixture=False),
        ]))
        tickers = await rt.list_scannable_tickers()
        # Solo OPERATIVE — DEGRADED y DISABLED excluidos
        assert tickers == [(1, "QQQ"), (2, "SPY")]

    @pytest.mark.asyncio
    async def test_warming_slots_excluded(self) -> None:
        rt = RegistryRuntime(_registry([
            _slot(1, ticker="QQQ"),
            _slot(2, ticker="SPY"),
        ]))
        await rt.mark_warming(1)
        tickers = await rt.list_scannable_tickers()
        assert tickers == [(2, "SPY")]

    @pytest.mark.asyncio
    async def test_ordered_by_slot_id(self) -> None:
        rt = RegistryRuntime(_registry([
            _slot(3, ticker="AAPL"),
            _slot(1, ticker="QQQ"),
            _slot(2, ticker="SPY"),
        ]))
        tickers = await rt.list_scannable_tickers()
        assert [t[0] for t in tickers] == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════════════════
# list_slots / get_slot — serialización completa
# ═══════════════════════════════════════════════════════════════════════════


class TestListSlots:
    @pytest.mark.asyncio
    async def test_always_returns_6(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        slots = await rt.list_slots()
        assert len(slots) == 6

    @pytest.mark.asyncio
    async def test_serialize_operative(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        slot = (await rt.list_slots())[0]
        assert slot["slot"] == 1
        assert slot["ticker"] == "QQQ"
        assert slot["status"] == "active"
        assert slot["base_state"] == "OPERATIVE"
        assert slot["fixture_id"] == "qqq_test"
        assert slot["benchmark"] == "SPY"
        assert slot["error_code"] is None

    @pytest.mark.asyncio
    async def test_serialize_disabled(self) -> None:
        rt = RegistryRuntime(_registry([]))
        slot = (await rt.list_slots())[0]
        assert slot["status"] == "disabled"
        assert slot["ticker"] is None

    @pytest.mark.asyncio
    async def test_serialize_degraded_with_error(self) -> None:
        rt = RegistryRuntime(_registry([
            _slot(1, status="DEGRADED", ticker="QQQ"),
        ]))
        slot = (await rt.list_slots())[0]
        assert slot["status"] == "degraded"
        assert slot["error_code"] == "REG-010"

    @pytest.mark.asyncio
    async def test_serialize_warming(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        await rt.mark_warming(1)
        slot = (await rt.list_slots())[0]
        assert slot["status"] == "warming_up"
        assert slot["base_state"] == "OPERATIVE"


class TestGetSlot:
    @pytest.mark.asyncio
    async def test_existing_slot(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        slot = await rt.get_slot(1)
        assert slot is not None
        assert slot["slot"] == 1

    @pytest.mark.asyncio
    async def test_nonexistent_slot(self) -> None:
        rt = RegistryRuntime(_registry([]))
        slot = await rt.get_slot(99)
        assert slot is None


class TestEffectiveStatus:
    @pytest.mark.asyncio
    async def test_none_for_unknown_slot(self) -> None:
        rt = RegistryRuntime(_registry([]))
        assert await rt.effective_status(99) is None

    @pytest.mark.asyncio
    async def test_active_for_operative(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        assert await rt.effective_status(1) == "active"

    @pytest.mark.asyncio
    async def test_warming_up_overlays_operative(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        await rt.mark_warming(1)
        assert await rt.effective_status(1) == "warming_up"


# ═══════════════════════════════════════════════════════════════════════════
# Overlay warmup
# ═══════════════════════════════════════════════════════════════════════════


class TestWarmingOverlay:
    @pytest.mark.asyncio
    async def test_mark_warmed_is_idempotent(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        await rt.mark_warmed(1)  # nunca estuvo
        await rt.mark_warming(1)
        await rt.mark_warmed(1)
        await rt.mark_warmed(1)  # segunda vez
        assert not await rt.is_warming(1)

    @pytest.mark.asyncio
    async def test_warming_slots_sorted(self) -> None:
        rt = RegistryRuntime(_registry([]))
        await rt.mark_warming(3)
        await rt.mark_warming(1)
        await rt.mark_warming(2)
        assert await rt.warming_slots() == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════════════════
# replace_registry
# ═══════════════════════════════════════════════════════════════════════════


class TestReplaceRegistry:
    @pytest.mark.asyncio
    async def test_replace_updates_slots(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        assert await rt.effective_status(1) == "active"

        # Nuevo registry con slot 1 DEGRADED
        new_reg = _registry([
            _slot(1, status="DEGRADED", ticker="QQQ"),
        ])
        await rt.replace_registry(new_reg)
        assert await rt.effective_status(1) == "degraded"

    @pytest.mark.asyncio
    async def test_replace_clears_warming_overlay(self) -> None:
        rt = RegistryRuntime(_registry([_slot(1, ticker="QQQ")]))
        await rt.mark_warming(1)
        assert await rt.effective_status(1) == "warming_up"

        await rt.replace_registry(_registry([_slot(1, ticker="QQQ")]))
        # El warmup overlay se limpió
        assert await rt.effective_status(1) == "active"
