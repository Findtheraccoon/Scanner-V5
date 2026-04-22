"""Tests del pipeline analyze → persist → broadcast (C5.6)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
import pytest_asyncio

from api.broadcaster import Broadcaster
from api.events import EVENT_SIGNAL_NEW
from modules.db import (
    ET_TZ,
    default_url,
    init_db,
    make_engine,
    make_session_factory,
    read_signal_by_id,
)
from modules.signal_pipeline import build_chat_format, build_ws_payload, scan_and_emit

# ═══════════════════════════════════════════════════════════════════════════
# Fixtures + helpers
# ═══════════════════════════════════════════════════════════════════════════


class RecordingWS:
    """Mock broadcaster client que graba los envelopes."""

    def __init__(self) -> None:
        self.received: list[dict] = []

    async def send_json(self, data: Any) -> None:
        self.received.append(data)


@pytest_asyncio.fixture
async def session():
    engine = make_engine(default_url(":memory:"))
    await init_db(engine)
    factory = make_session_factory(engine)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest_asyncio.fixture
async def broadcaster_with_client():
    b = Broadcaster()
    ws = RecordingWS()
    await b.register(ws)
    return b, ws


def _valid_fixture() -> dict:
    from modules.fixtures import CONFIRM_CATEGORIES

    return {
        "metadata": {
            "fixture_id": "qqq_test",
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "test fixture",
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
            {"min": 16.0, "max": None, "label": "S+", "signal": "SETUP"},
            {"min": 14.0, "max": 16.0, "label": "S", "signal": "SETUP"},
            {"min": 10.0, "max": 14.0, "label": "A+", "signal": "SETUP"},
            {"min": 7.0, "max": 10.0, "label": "A", "signal": "SETUP"},
            {"min": 4.0, "max": 7.0, "label": "B", "signal": "REVISAR"},
            {"min": 2.0, "max": 4.0, "label": "REVISAR", "signal": "REVISAR"},
        ],
    }


def _monotonic_candles(n: int, start: float = 500.0) -> list[dict]:
    return [
        {
            "dt": f"2025-01-{(i % 28) + 1:02d} 10:00:00",
            "o": start + i * 0.1, "h": start + i * 0.1 + 1.0,
            "l": start + i * 0.1 - 1.0, "c": start + i * 0.1 + 0.5,
            "v": 1_000_000 + i,
        }
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# scan_and_emit
# ═══════════════════════════════════════════════════════════════════════════


class TestScanAndEmitNeutral:
    @pytest.mark.asyncio
    async def test_neutral_output_persisted_but_not_broadcast(
        self, session, broadcaster_with_client,
    ) -> None:
        """Un NEUTRAL se persiste pero NO se broadcast."""
        b, ws = broadcaster_with_client
        from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY

        # Serie monotónica sin triggers → output NEUTRAL
        result = await scan_and_emit(
            session=session,
            broadcaster=b,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            slot_id=1,
            ticker="QQQ",
            candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
            candles_1h=_monotonic_candles(MIN_CANDLES_1H),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M),
            fixture=_valid_fixture(),
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        )

        # Persistido
        assert "id" in result
        assert result["id"] > 0
        persisted = await read_signal_by_id(session, result["id"])
        assert persisted is not None
        assert persisted["signal"] is False  # NEUTRAL → False

        # NO broadcast
        assert len(ws.received) == 0


class TestScanAndEmitSetup:
    @pytest.mark.asyncio
    async def test_setup_persists_and_broadcasts(
        self, session, broadcaster_with_client, monkeypatch,
    ) -> None:
        """SETUP real → persist + broadcast signal.new con payload completo."""
        import sys

        b, ws = broadcaster_with_client
        from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY

        # Monkeypatch el detector de MA cross 1H para que emita un trigger
        # sintético — mismo patrón que test_analyze_fase5.
        analyze_mod = sys.modules["engines.scoring.analyze"]
        monkeypatch.setattr(
            analyze_mod, "detect_ma_cross_1h",
            lambda candles: [{
                "tf": "1H", "d": "MA20 cross up (synth)",
                "sg": "CALL", "w": 4.0, "cat": "TRIGGER", "age": 0,
            }],
        )

        result = await scan_and_emit(
            session=session,
            broadcaster=b,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            slot_id=1,
            ticker="QQQ",
            candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
            candles_1h=_monotonic_candles(MIN_CANDLES_1H),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M),
            fixture=_valid_fixture(),
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        )

        # Persistido con signal=True
        persisted = await read_signal_by_id(session, result["id"])
        assert persisted["signal"] is True

        # Broadcast realizado
        assert len(ws.received) == 1
        envelope = ws.received[0]
        assert envelope["event"] == EVENT_SIGNAL_NEW
        assert envelope["payload"]["id"] == result["id"]
        assert envelope["payload"]["ticker"] == "QQQ"
        # chat_format está presente
        assert envelope["payload"]["chat_format"].startswith("[QQQ]")


# ═══════════════════════════════════════════════════════════════════════════
# scan_and_emit con persist=False (is_validator_test — V.3)
# ═══════════════════════════════════════════════════════════════════════════


class TestScanAndEmitNoPersist:
    @pytest.mark.asyncio
    async def test_no_persist_no_broadcast(
        self, session, broadcaster_with_client,
    ) -> None:
        """persist=False: no escribe en DB ni broadcasta. Retorna output igual."""
        b, ws = broadcaster_with_client
        from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY

        result = await scan_and_emit(
            session=session,
            broadcaster=b,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            slot_id=1,
            ticker="QQQ",
            candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
            candles_1h=_monotonic_candles(MIN_CANDLES_1H),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M),
            fixture=_valid_fixture(),
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            persist=False,
        )

        # Output del analyze sigue llegando
        assert result["ticker"] == "QQQ"
        assert "signal" in result
        # Pero sin id (no persistido) y con flag explícito
        assert result["id"] is None
        assert result["persisted"] is False
        # WS no recibió nada
        assert len(ws.received) == 0

    @pytest.mark.asyncio
    async def test_no_persist_accepts_none_session_and_broadcaster(self) -> None:
        """Con persist=False, session y broadcaster pueden ser None."""
        from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY

        result = await scan_and_emit(
            session=None,
            broadcaster=None,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
            slot_id=1,
            ticker="QQQ",
            candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
            candles_1h=_monotonic_candles(MIN_CANDLES_1H),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M),
            fixture=_valid_fixture(),
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            persist=False,
        )
        assert result["persisted"] is False

    @pytest.mark.asyncio
    async def test_persist_true_with_none_session_raises(self) -> None:
        """Salvaguarda: persist=True + session=None es un bug del caller."""
        from engines.scoring import MIN_CANDLES_1H, MIN_CANDLES_15M, MIN_CANDLES_DAILY

        with pytest.raises(ValueError, match="requeridos cuando persist=True"):
            await scan_and_emit(
                session=None,
                broadcaster=None,
                candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
                slot_id=1,
                ticker="QQQ",
                candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
                candles_1h=_monotonic_candles(MIN_CANDLES_1H),
                candles_15m=_monotonic_candles(MIN_CANDLES_15M),
                fixture=_valid_fixture(),
                spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
                bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            )


# ═══════════════════════════════════════════════════════════════════════════
# build_chat_format
# ═══════════════════════════════════════════════════════════════════════════


class TestChatFormat:
    def test_header_includes_ticker_score_conf(self) -> None:
        out = {
            "ticker": "QQQ", "score": 8.0, "conf": "A",
            "dir": "CALL", "signal": "SETUP", "layers": {}, "patterns": [],
        }
        text = build_chat_format(
            out, candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        assert "[QQQ]" in text
        assert "CALL" in text
        assert "score 8.0" in text
        assert "(A)" in text
        assert "SETUP" in text

    def test_includes_alignment_block(self) -> None:
        out = {
            "ticker": "QQQ", "score": 4.0, "conf": "B",
            "dir": "CALL", "signal": "REVISAR",
            "layers": {"alignment": {"n": 2, "dir": "bullish"}},
            "patterns": [],
        }
        text = build_chat_format(
            out, candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        assert "Alignment: bullish 2/3" in text

    def test_includes_triggers_and_confirms(self) -> None:
        out = {
            "ticker": "QQQ", "score": 8.0, "conf": "A",
            "dir": "CALL", "signal": "SETUP",
            "layers": {
                "alignment": {"n": 3, "dir": "bullish"},
                "confirm": {
                    "items": [{"desc": "FzaRel +1.5% vs SPY", "weight": 4.0}],
                },
            },
            "patterns": [
                {"cat": "TRIGGER", "w": 3.0, "d": "Doble piso ~$514.64"},
            ],
        }
        text = build_chat_format(
            out, candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        assert "Doble piso" in text
        assert "FzaRel" in text

    def test_error_short_format(self) -> None:
        out = {
            "ticker": "QQQ", "score": 0.0, "conf": "—",
            "dir": None, "signal": "NEUTRAL",
            "error": True, "error_code": "ENG-001",
            "layers": {}, "patterns": [],
        }
        text = build_chat_format(
            out, candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        assert "ERROR: ENG-001" in text
        # No layers/triggers se incluyen después del error
        assert "Alignment" not in text


# ═══════════════════════════════════════════════════════════════════════════
# build_ws_payload
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildWsPayload:
    def test_includes_all_required_keys(self) -> None:
        out = {
            "ticker": "QQQ", "engine_version": "5.2.0",
            "fixture_id": "qqq_v1", "fixture_version": "5.2.0",
            "score": 8.0, "conf": "A", "signal": "SETUP", "dir": "CALL",
            "blocked": None,
            "layers": {"alignment": {"n": 3, "dir": "bullish"}},
            "ind": {"price": 500.0},
            "patterns": [{"cat": "TRIGGER", "w": 3.0, "d": "P1"}],
        }
        payload = build_ws_payload(
            out, sig_id=42,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        required = {
            "id", "ticker", "candle_timestamp", "engine_version",
            "fixture_id", "fixture_version", "score", "conf", "signal",
            "dir", "blocked", "layers", "ind", "patterns", "chat_format",
        }
        assert set(payload.keys()) == required
        assert payload["id"] == 42
        assert payload["chat_format"].startswith("[QQQ]")

    def test_no_snapshot_in_payload(self) -> None:
        """Spec §3.6: el WS NO envía el snapshot (demasiado pesado)."""
        out = {
            "ticker": "QQQ", "engine_version": "5.2.0",
            "fixture_id": "qqq_v1", "fixture_version": "5.2.0",
            "score": 8.0, "conf": "A", "signal": "SETUP", "dir": "CALL",
            "blocked": None, "layers": {}, "ind": {}, "patterns": [],
        }
        payload = build_ws_payload(
            out, sig_id=1,
            candle_timestamp=dt.datetime(2026, 4, 22, 10, 30, tzinfo=ET_TZ),
        )
        assert "candles_snapshot_gzip" not in payload
        assert "candles_snapshot_gzip_b64" not in payload
