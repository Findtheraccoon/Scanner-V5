"""Tests de ORB breakout/breakdown + time gate 10:30 ET (Fase 4c)."""

from __future__ import annotations

import pytest

from engines.scoring.triggers import compute_orb_levels, detect_orb_triggers_15m


def _candle(dt: str, o: float, h: float, low: float, c: float, v: int = 1000) -> dict:
    return {"dt": dt, "o": o, "h": h, "l": low, "c": c, "v": v}


def _today_session(
    day: str = "2025-01-15",
    n_candles: int = 11,
    *,
    first_high: float = 105.0,
    first_low: float = 100.0,
    second_high: float = 104.0,
    second_low: float = 101.0,
    current_close: float = 102.0,
    current_time: str = "10:00:00",
) -> list[dict]:
    """Construye ≥10 velas con las primeras 2 del día definiendo el ORB.

    Los tiempos quedan en formato ET ≤ 10:30 por default.
    """
    times = [
        "09:30:00",
        "09:45:00",
        "10:00:00",
        "10:15:00",
        "10:30:00",
        "10:45:00",
        "11:00:00",
        "11:15:00",
        "11:30:00",
        "11:45:00",
        "12:00:00",
    ][:n_candles]
    candles: list[dict] = []
    # Primera: define el ORB high/low con first_high / first_low
    candles.append(_candle(f"{day} {times[0]}", o=101, h=first_high, low=first_low, c=102.5))
    # Segunda: segunda parte del ORB
    candles.append(_candle(f"{day} {times[1]}", o=102, h=second_high, low=second_low, c=102.5))
    # Resto: velas neutras excepto la última que se ajusta al caller
    for i in range(2, n_candles - 1):
        candles.append(_candle(f"{day} {times[i]}", o=102, h=102.5, low=101.5, c=102))
    # Última: dt controlado por `current_time` para el time gate
    candles.append(
        _candle(
            f"{day} {current_time}",
            o=current_close - 0.5,
            h=current_close + 0.5,
            low=current_close - 1.0,
            c=current_close,
        )
    )
    return candles


# ═══════════════════════════════════════════════════════════════════════════
# compute_orb_levels — cálculo de niveles
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeOrbLevels:
    def test_returns_none_with_too_few_candles(self) -> None:
        candles = [_candle("2025-01-15 09:30:00", 100, 101, 99, 100)]
        assert compute_orb_levels(candles) is None

    def test_returns_none_without_dt(self) -> None:
        candles = _today_session()
        candles[-1]["dt"] = ""  # falta dt en la última
        assert compute_orb_levels(candles) is None

    def test_returns_none_with_less_than_3_today_candles(self) -> None:
        # Solo 2 velas de "hoy" + 8 de "ayer" → filtra por fecha de la última.
        yesterday = [
            _candle(f"2025-01-14 {t}", 100, 101, 99, 100)
            for t in [
                "09:30:00",
                "09:45:00",
                "10:00:00",
                "10:15:00",
                "10:30:00",
                "10:45:00",
                "11:00:00",
                "11:15:00",
            ]
        ]
        today = [
            _candle("2025-01-15 09:30:00", 100, 101, 99, 100),
            _candle("2025-01-15 09:45:00", 100, 101, 99, 100),
        ]
        result = compute_orb_levels(yesterday + today)
        assert result is None

    def test_high_low_taken_from_first_two_today_candles(self) -> None:
        candles = _today_session(
            first_high=110.0, first_low=100.0, second_high=108.0, second_low=102.0
        )
        orb = compute_orb_levels(candles)
        assert orb is not None
        assert orb["high"] == 110.0
        assert orb["low"] == 100.0

    def test_breakup_true_when_current_close_above_high(self) -> None:
        candles = _today_session(first_high=110.0, first_low=100.0, current_close=115.0)
        orb = compute_orb_levels(candles)
        assert orb is not None
        assert orb["breakUp"] is True
        assert orb["breakDown"] is False

    def test_breakdown_true_when_current_close_below_low(self) -> None:
        candles = _today_session(first_high=110.0, first_low=100.0, current_close=95.0)
        orb = compute_orb_levels(candles)
        assert orb is not None
        assert orb["breakDown"] is True
        assert orb["breakUp"] is False

    def test_no_break_when_current_inside_range(self) -> None:
        candles = _today_session(first_high=110.0, first_low=100.0, current_close=105.0)
        orb = compute_orb_levels(candles)
        assert orb is not None
        assert orb["breakUp"] is False
        assert orb["breakDown"] is False


# ═══════════════════════════════════════════════════════════════════════════
# detect_orb_triggers_15m — triggers con time gate + vol filter
# ═══════════════════════════════════════════════════════════════════════════


class TestOrbTriggers:
    def test_breakout_fires_before_1030_et(self) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0, current_time="10:00:00")
        triggers = detect_orb_triggers_15m(candles)
        match = [t for t in triggers if t["d"].startswith("ORB breakout")]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 2.0
        assert "110.00" in match[0]["d"]

    def test_breakdown_fires_before_1030_et(self) -> None:
        candles = _today_session(first_low=100.0, current_close=95.0, current_time="10:30:00")
        triggers = detect_orb_triggers_15m(candles)
        match = [t for t in triggers if t["d"].startswith("ORB breakdown")]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"

    def test_does_not_fire_after_1030_et(self) -> None:
        """Time gate: ORB no dispara después de 10:30."""
        candles = _today_session(first_high=110.0, current_close=115.0, current_time="10:31:00")
        triggers = detect_orb_triggers_15m(candles)
        assert not triggers

    def test_exactly_1030_ET_is_valid(self) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0, current_time="10:30:00")
        triggers = detect_orb_triggers_15m(candles)
        assert any(t["d"].startswith("ORB breakout") for t in triggers)

    def test_sim_datetime_overrides_candle_dt(self) -> None:
        """Si sim_datetime está después de 10:30, no dispara aunque el
        candle dt esté antes."""
        candles = _today_session(first_high=110.0, current_close=115.0, current_time="10:00:00")
        triggers = detect_orb_triggers_15m(candles, sim_datetime="2025-01-15 11:00:00")
        assert not triggers

    def test_sim_datetime_allows_when_candle_time_out_of_range(self) -> None:
        """Si sim_datetime está dentro del gate, la hora del candle se ignora."""
        candles = _today_session(first_high=110.0, current_close=115.0, current_time="11:30:00")
        triggers = detect_orb_triggers_15m(candles, sim_datetime="2025-01-15 10:00:00")
        assert any(t["d"].startswith("ORB breakout") for t in triggers)

    def test_volume_filter_suppresses_below_1x(self) -> None:
        """Gate binario de volumen — si volM < 1.0, el trigger no fire.

        Paridad con Observatory engine.py:193-199. H-02 del Observatory
        ("volumen sale del score") se refiere al `volMult` multiplicador,
        NO a este gate binario que sí se mantiene.
        """
        candles = _today_session(first_high=110.0, current_close=115.0)
        triggers = detect_orb_triggers_15m(candles, volume_ratio=0.5)
        assert not triggers

    def test_volume_filter_allows_at_1x_exactly(self) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0)
        triggers = detect_orb_triggers_15m(candles, volume_ratio=1.0)
        assert any(t["d"].startswith("ORB breakout") for t in triggers)

    def test_none_volume_ratio_skips_filter(self) -> None:
        """Si el caller no pasa volume_ratio, el gate se omite."""
        candles = _today_session(first_high=110.0, current_close=115.0)
        triggers = detect_orb_triggers_15m(candles, volume_ratio=None)
        assert any(t["d"].startswith("ORB breakout") for t in triggers)

    def test_no_breakup_or_breakdown_yields_no_triggers(self) -> None:
        candles = _today_session(first_high=110.0, first_low=100.0, current_close=105.0)
        triggers = detect_orb_triggers_15m(candles)
        assert not triggers


# ═══════════════════════════════════════════════════════════════════════════
# Time gate — edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestTimeGate:
    @pytest.mark.parametrize(
        "time_str,should_fire",
        [
            ("09:30:00", True),
            ("10:00:00", True),
            ("10:30:00", True),  # edge inclusivo
            # Observatory usa `dt_str[11:16]` — slice fijo "HH:MM", ignora
            # segundos. 10:30:59 → "10:30" → válido. 10:31:00 → "10:31" → inválido.
            ("10:30:01", True),
            ("10:30:59", True),
            ("10:31:00", False),
            ("11:00:00", False),
            ("15:00:00", False),
            ("00:00:00", True),  # medianoche ET (raro pero válido por ≤ 10:30)
        ],
    )
    def test_time_gate_boundary(self, time_str: str, should_fire: bool) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0, current_time=time_str)
        triggers = detect_orb_triggers_15m(candles)
        if should_fire:
            assert any(t["d"].startswith("ORB breakout") for t in triggers)
        else:
            assert not triggers

    def test_unparseable_time_returns_no_triggers(self) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0)
        # Corromper el dt de la última vela
        candles[-1]["dt"] = "no-time-here"
        triggers = detect_orb_triggers_15m(candles)
        assert not triggers

    def test_empty_dt_returns_no_triggers(self) -> None:
        candles = _today_session(first_high=110.0, current_close=115.0)
        candles[-1]["dt"] = ""
        triggers = detect_orb_triggers_15m(candles)
        assert not triggers
