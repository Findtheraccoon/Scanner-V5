"""Tests de los 8 triggers 15M (Fases 4a + 4b extended).

Velas construidas con OHLC exactos para forzar cada condición del
detector (body ratio, wick ratio, proximidad a BB, decay por age,
engulfing).

**Convención de los helpers:** el loop del detector requiere siempre
una vela previa `pv` (paridad con Observatory — `range(min(5, n-1))`).
Por eso todos los tests que quieren examinar la "vela candidata"
usan `_pair(candle)` que prepend una copia como pv — misma dirección
y body que la candidata, lo que impide que se dispare engulfing pero
no afecta a Doji/Hammer/Shooting/Rechazo.
"""

from __future__ import annotations

import pytest

from engines.scoring.triggers import (
    decay_weight,
    detect_candle_15m_triggers,
)

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _candle(o: float, h: float, low: float, c: float, v: int = 1000) -> dict:
    """Vela con OHLC explícito."""
    return {"dt": "2025-01-15 10:00:00", "o": o, "h": h, "l": low, "c": c, "v": v}


def _neutral_candle(price: float = 100.0) -> dict:
    """Vela pequeña, body central. No dispara ningún trigger."""
    return _candle(price, price + 0.1, price - 0.1, price + 0.05)


def _bb(upper: float = 110.0, lower: float = 90.0, middle: float = 100.0) -> tuple:
    return (upper, middle, lower)


def _pair(candle: dict) -> list[dict]:
    """Devuelve `[pv, candle]` con `pv = candle` (duplicado).

    Cumple el requisito del loop Observatory de tener ≥2 velas. Como
    pv y candle son idénticos (misma dirección, mismo body), la lógica
    de engulfing (que requiere direcciones opuestas) no se dispara —
    pero Doji/Hammer/Shooting/Rechazo en la última vela funcionan
    igual que antes.
    """
    return [candle, candle]


# ═══════════════════════════════════════════════════════════════════════════
# decay_weight
# ═══════════════════════════════════════════════════════════════════════════


class TestDecayWeight:
    @pytest.mark.parametrize(
        "age,expected",
        [
            (0, 1.0),
            (1, 1.0),
            (2, 0.85),
            (3, 0.85),
            (4, 0.7),
            (5, 0.7),
            (6, 0.4),
            (10, 0.4),
            (11, 0.2),
            (100, 0.2),
        ],
    )
    def test_decay_schedule_matches_observatory(self, age: int, expected: float) -> None:
        assert decay_weight(age) == expected


# ═══════════════════════════════════════════════════════════════════════════
# Estructura general
# ═══════════════════════════════════════════════════════════════════════════


class TestGeneralBehavior:
    def test_empty_candles_returns_empty(self) -> None:
        assert detect_candle_15m_triggers([]) == []

    def test_single_candle_returns_empty(self) -> None:
        """Observatory requiere ≥2 velas (loop `min(5, n-1)`). Single → 0 iter."""
        candles = [_candle(o=100.0, h=100.2, low=98.0, c=100.1)]
        assert detect_candle_15m_triggers(candles, bb_15m=_bb(lower=98.0)) == []

    def test_no_bb_disables_bb_dependent_triggers(self) -> None:
        # Vela con geometría de Hammer — sin BB no dispara.
        hammer = _candle(o=100.0, h=100.2, low=98.0, c=100.1)
        triggers = detect_candle_15m_triggers(_pair(hammer), bb_15m=None)
        assert not any(t["d"] == "Hammer" for t in triggers)

    def test_zero_range_candle_is_skipped(self) -> None:
        flat = _candle(o=100.0, h=100.0, low=100.0, c=100.0)
        assert detect_candle_15m_triggers(_pair(flat)) == []


# ═══════════════════════════════════════════════════════════════════════════
# Doji BB sup / inf
# ═══════════════════════════════════════════════════════════════════════════


class TestDojiBB:
    def test_doji_bb_sup_fires_when_near_upper_band(self) -> None:
        # body/rng = 0.01/1.0 = 0.01 < 0.12 ✓
        # h=111 >= upper*0.998 = 109.78 ✓
        doji = _candle(o=110.5, h=111.0, low=110.0, c=110.51)
        triggers = detect_candle_15m_triggers(_pair(doji), bb_15m=_bb(upper=110.0))
        assert any(t["d"] == "Doji BB sup" and t["sg"] == "PUT" and t["w"] == 2.0 for t in triggers)

    def test_doji_bb_inf_fires_when_near_lower_band(self) -> None:
        # body pequeño, l cerca de banda inferior
        doji = _candle(o=90.5, h=91.0, low=89.9, c=90.51)
        triggers = detect_candle_15m_triggers(_pair(doji), bb_15m=_bb(lower=90.0))
        assert any(
            t["d"] == "Doji BB inf" and t["sg"] == "CALL" and t["w"] == 2.0 for t in triggers
        )

    def test_doji_ignored_when_body_too_large(self) -> None:
        # body/rng = 0.5/1.0 = 0.5 > 0.12 → no doji
        big_body = _candle(o=110.0, h=111.0, low=110.0, c=110.5)
        triggers = detect_candle_15m_triggers(_pair(big_body), bb_15m=_bb(upper=110.0))
        assert not any("Doji" in t["d"] for t in triggers)

    def test_doji_ignored_when_far_from_band(self) -> None:
        # body pequeño pero muy lejos de banda
        far = _candle(o=100.0, h=100.5, low=99.5, c=100.01)
        triggers = detect_candle_15m_triggers(_pair(far), bb_15m=_bb(upper=110.0, lower=90.0))
        assert not any("Doji" in t["d"] for t in triggers)

    def test_doji_only_fires_at_age_zero(self) -> None:
        """Una vela doji en age=2 no debe fire Doji, solo Rechazos si aplica."""
        doji = _candle(o=110.5, h=111.0, low=110.0, c=110.51)
        newer = _neutral_candle()
        candles = [doji, newer, newer]  # doji es age=2
        triggers = detect_candle_15m_triggers(candles, bb_15m=_bb(upper=110.0))
        assert not any("Doji" in t["d"] for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Rechazo sup / inf
# ═══════════════════════════════════════════════════════════════════════════


class TestRechazo:
    def test_rechazo_sup_fires_at_age_0(self) -> None:
        # uW = h - max(o,c); con o=100, c=100.5, h=105 → uW=4.5
        # rng = h - l = 105 - 99 = 6. uW/rng = 0.75 > 0.6 ✓
        candle = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(candle))
        match = [t for t in triggers if t["d"].startswith("Rechazo sup")]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 2.0  # age=0 → decay=1.0
        assert match[0]["age"] == 0

    def test_rechazo_inf_fires_at_age_0(self) -> None:
        # lW = min(o,c) - l; con o=100, c=99.5, l=95 → lW=4.5
        # rng=h-l=101-95=6. lW/rng=0.75 > 0.6 ✓
        candle = _candle(o=100.0, h=101.0, low=95.0, c=99.5)
        triggers = detect_candle_15m_triggers(_pair(candle))
        match = [t for t in triggers if t["d"].startswith("Rechazo inf")]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 2.0
        assert match[0]["age"] == 0

    def test_rechazo_with_decay_at_age_3(self) -> None:
        # age=3 → decay=0.85, weight = round(2 * 0.85, 1) = 1.7
        # Con n=5, ages_to_check = min(5, 4) = 4 → ages 0..3.
        # age=3 examina idx=1 (el rechazo).
        rechazo = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        neutral = _neutral_candle()
        candles = [neutral, rechazo, neutral, neutral, neutral]
        triggers = detect_candle_15m_triggers(candles)
        match = [t for t in triggers if "Rechazo sup" in t["d"] and t["age"] == 3]
        assert len(match) == 1
        assert match[0]["w"] == pytest.approx(1.7)
        assert "(3v atrás)" in match[0]["d"]

    def test_rechazo_percentage_appears_in_description(self) -> None:
        # uW/rng = 0.75 → pct rounded to 75
        candle = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(candle))
        rechazo = next(t for t in triggers if t["d"].startswith("Rechazo sup"))
        assert "75%" in rechazo["d"]

    def test_rechazo_not_fired_when_wick_ratio_below_threshold(self) -> None:
        # Body centrado grande: uW/rng y lW/rng pequeños → ni Rechazo sup ni inf.
        # o=99.5, c=100.5, h=100.8, l=99.2 → rng=1.6, body=1.0
        # uW = 100.8 - 100.5 = 0.3, ratio 0.1875 < 0.6 ✓
        # lW = 99.5 - 99.2 = 0.3, ratio 0.1875 < 0.6 ✓
        centered = _candle(o=99.5, h=100.8, low=99.2, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(centered))
        assert not any("Rechazo" in t["d"] for t in triggers)

    def test_rechazo_only_up_to_max_age(self) -> None:
        # Con max_age=4 y 10 velas, solo las últimas 5 (ages 0..4) se chequean.
        rechazo = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        neutrals = [_neutral_candle() for _ in range(9)]
        candles = [rechazo, *neutrals]  # rechazo en idx=0 → age=9 (no debe fire)
        triggers = detect_candle_15m_triggers(candles)
        assert not any("Rechazo" in t["d"] for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Hammer
# ═══════════════════════════════════════════════════════════════════════════


class TestHammer:
    def test_hammer_fires_with_long_lower_wick_near_lower_bb(self) -> None:
        # body = |100.5 - 100.3| = 0.2, lW = 3.3, uW = 0
        # lW > body*2 ✓, uW < body*0.5 ✓, l=97 <= lower*1.005 ✓
        hammer = _candle(o=100.5, h=100.5, low=97.0, c=100.3)
        triggers = detect_candle_15m_triggers(_pair(hammer), bb_15m=_bb(lower=97.0))
        match = [t for t in triggers if t["d"] == "Hammer"]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 2.0

    def test_hammer_not_fired_without_bb(self) -> None:
        hammer = _candle(o=100.5, h=100.5, low=97.0, c=100.3)
        triggers = detect_candle_15m_triggers(_pair(hammer), bb_15m=None)
        assert not any(t["d"] == "Hammer" for t in triggers)

    def test_hammer_not_fired_when_upper_wick_too_large(self) -> None:
        # Upper wick grande → no Hammer
        candle = _candle(o=100.5, h=105.0, low=97.0, c=100.3)
        triggers = detect_candle_15m_triggers(_pair(candle), bb_15m=_bb(lower=97.0))
        assert not any(t["d"] == "Hammer" for t in triggers)

    def test_hammer_not_fired_when_far_from_lower_bb(self) -> None:
        hammer_shape = _candle(o=100.5, h=100.5, low=97.0, c=100.3)
        # lower BB muy abajo → no está "cerca"
        triggers = detect_candle_15m_triggers(_pair(hammer_shape), bb_15m=_bb(lower=50.0))
        assert not any(t["d"] == "Hammer" for t in triggers)

    def test_hammer_only_fires_at_age_zero(self) -> None:
        hammer = _candle(o=100.5, h=100.5, low=97.0, c=100.3)
        newer = _neutral_candle()
        candles = [hammer, newer]  # hammer en idx=0 (age=1, no se chequea porque ages=1)
        triggers = detect_candle_15m_triggers(candles, bb_15m=_bb(lower=97.0))
        assert not any(t["d"] == "Hammer" for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Shooting Star
# ═══════════════════════════════════════════════════════════════════════════


class TestShootingStar:
    def test_shooting_star_fires_with_long_upper_wick_near_upper_bb(self) -> None:
        # body = 0.2, uW = 3.3 (long), lW = 0
        shooting = _candle(o=100.3, h=103.6, low=100.3, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(shooting), bb_15m=_bb(upper=103.5))
        match = [t for t in triggers if t["d"] == "Shooting Star"]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 2.0

    def test_shooting_star_not_fired_without_bb(self) -> None:
        shooting = _candle(o=100.3, h=103.6, low=100.3, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(shooting), bb_15m=None)
        assert not any(t["d"] == "Shooting Star" for t in triggers)

    def test_shooting_star_not_fired_when_lower_wick_too_large(self) -> None:
        candle = _candle(o=100.3, h=103.6, low=95.0, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(candle), bb_15m=_bb(upper=103.5))
        assert not any(t["d"] == "Shooting Star" for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Envolvente 15M (Fase 4b extended)
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvolvente15M:
    def test_bullish_envolvente_fires_at_age_0(self) -> None:
        # prev bear (o=101, c=100, body=1.0), curr bull (o=99, c=102, body=3.0)
        # curr.o (99) <= prev.c (100) ✓
        # curr.c (102) >= prev.o (101) ✓
        # body (3.0) > prev_body (1.0) * 1.1 = 1.1 ✓
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=99, h=102.5, low=98.5, c=102)
        triggers = detect_candle_15m_triggers([prev, curr])
        match = [t for t in triggers if t["d"] == "Envolvente alcista"]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 3.0  # age=0 → decay=1.0
        assert match[0]["tf"] == "15M"
        assert match[0]["age"] == 0

    def test_bearish_envolvente_fires_at_age_0(self) -> None:
        # prev bull (o=100, c=101), curr bear (o=102, c=100, body=2)
        # curr.o (102) >= prev.c (101) ✓
        # curr.c (100) <= prev.o (100) ✓
        # body (2.0) > prev_body (1.0) * 1.1 ✓
        prev = _candle(o=100, h=101.5, low=99.5, c=101)
        curr = _candle(o=102, h=102.5, low=99.5, c=100)
        triggers = detect_candle_15m_triggers([prev, curr])
        match = [t for t in triggers if t["d"] == "Envolvente bajista"]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 3.0

    def test_envolvente_does_not_fire_when_same_direction(self) -> None:
        # Ambas bull → no bullish engulfing (prev debe ser bear)
        prev = _candle(o=100, h=101, low=99.5, c=100.5)
        curr = _candle(o=99, h=103, low=98.5, c=102.5)
        triggers = detect_candle_15m_triggers([prev, curr])
        assert not any("Envolvente" in t["d"] for t in triggers)

    def test_envolvente_does_not_fire_when_body_ratio_insufficient(self) -> None:
        # body curr = 1.0, body prev = 1.0 → 1.0 > 1.1 False
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=99.5, h=101, low=99, c=100.5)
        triggers = detect_candle_15m_triggers([prev, curr])
        assert not any("Envolvente" in t["d"] for t in triggers)

    def test_envolvente_does_not_fire_when_containment_fails(self) -> None:
        # curr.o > prev.c (no contiene el close previo)
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=100.5, h=103, low=100.3, c=102.5)
        triggers = detect_candle_15m_triggers([prev, curr])
        assert not any("Envolvente" in t["d"] for t in triggers)

    def test_envolvente_with_decay_at_age_2(self) -> None:
        # age=2 → decay=0.85, weight = round(3.0 * 0.85, 1)
        # 3.0 * 0.85 = 2.55 (valor exacto en float). round(2.55, 1) en Python
        # usa banker's rounding al dígito par → 2.5. Pero 2.55 como float es
        # 2.5499999... (menor que exacto), así que round da 2.5.
        # Observatory usa `round(3 * decay, 1)` idéntico; misma semántica.
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=99, h=102.5, low=98.5, c=102)
        neutral = _neutral_candle()
        # Para ver la envolvente en age=2: necesitamos n=5 (ages 0..3),
        # y el par (prev, curr) en posiciones (idx=2, idx=3) → age=1.
        # Para age=2, el par debe estar en (idx=1, idx=2) → prepend 1 neutral.
        candles = [neutral, prev, curr, neutral, neutral]
        triggers = detect_candle_15m_triggers(candles)
        match = [t for t in triggers if "Envolvente alcista" in t["d"] and t["age"] == 2]
        assert len(match) == 1
        expected_weight = round(3.0 * 0.85, 1)
        assert match[0]["w"] == pytest.approx(expected_weight)
        assert "(2v atrás)" in match[0]["d"]

    def test_envolvente_description_has_no_1h_suffix(self) -> None:
        """Distingue del Envolvente 1H — descripción diferente."""
        prev = _candle(o=101, h=101.5, low=99.5, c=100)
        curr = _candle(o=99, h=102.5, low=98.5, c=102)
        triggers = detect_candle_15m_triggers([prev, curr])
        match = [t for t in triggers if "Envolvente" in t["d"]]
        assert len(match) == 1
        assert "1H" not in match[0]["d"]


# ═══════════════════════════════════════════════════════════════════════════
# Escenarios combinados
# ═══════════════════════════════════════════════════════════════════════════


class TestCombined:
    def test_multiple_rechazos_across_ages_accumulate(self) -> None:
        """6 velas de Rechazo sup → 5 triggers (ages 0..4) con decay."""
        # Con n=6, ages_to_check = min(5, 5) = 5 → ages 0..4.
        rechazo = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        candles = [rechazo] * 6
        triggers = detect_candle_15m_triggers(candles)
        rechazos_sup = [t for t in triggers if t["d"].startswith("Rechazo sup")]
        assert len(rechazos_sup) == 5
        # Weights esperados: 2.0, 2.0, 1.7, 1.7, 1.4 (decay 1, 1, 0.85, 0.85, 0.7)
        weights_by_age = {t["age"]: t["w"] for t in rechazos_sup}
        assert weights_by_age[0] == pytest.approx(2.0)
        assert weights_by_age[1] == pytest.approx(2.0)
        assert weights_by_age[2] == pytest.approx(1.7)
        assert weights_by_age[3] == pytest.approx(1.7)
        assert weights_by_age[4] == pytest.approx(1.4)

    def test_doji_and_rechazo_can_coexist_on_same_candle(self) -> None:
        """Una vela con body muy pequeño y wick largo puede disparar
        Doji BB + Rechazo simultáneamente."""
        # body=0.01, rng=6 → body/rng ~0.002 < 0.12 ✓
        # uW = 105 - max(100, 100.01) = 4.99, uW/rng = 0.83 > 0.6 ✓
        # h=105 >= upper*0.998 (104.79) ✓
        candle = _candle(o=100.0, h=105.0, low=99.0, c=100.01)
        triggers = detect_candle_15m_triggers(_pair(candle), bb_15m=_bb(upper=105.0))
        descs = [t["d"] for t in triggers]
        assert "Doji BB sup" in descs
        assert any(d.startswith("Rechazo sup") for d in descs)

    def test_output_shape_is_trigger_dict(self) -> None:
        candle = _candle(o=100.0, h=105.0, low=99.0, c=100.5)
        triggers = detect_candle_15m_triggers(_pair(candle))
        assert triggers, "se esperaba al menos 1 trigger"
        for t in triggers:
            assert set(t.keys()) == {"tf", "d", "sg", "w", "cat", "age"}
            assert t["cat"] == "TRIGGER"
            assert t["tf"] == "15M"
            assert t["sg"] in ("CALL", "PUT")
            assert isinstance(t["age"], int)
            assert isinstance(t["w"], float)
