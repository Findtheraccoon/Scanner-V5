"""Tests de confirms Bollinger (Fase 5.1) — BB sup/inf en 1H y D.

Cada test arma un trío `(upper, middle, lower)` y un `last_close_15m`
que fuerza la condición exacta del detector. Los valores redondeados
a 2 decimales se pasan como `float` para reflejar cómo los emite el
indicador `bb()` del Observatory.

**Paridad:** las descripciones esperadas son bit-exact con el sample
canonical QQQ. El formato `f"${x}"` sin `.2f` preserva el trailing
comportamiento de Python (498.2 → "$498.2", 498.20 → "$498.2").
"""

from __future__ import annotations

from engines.scoring.confirms import detect_bollinger_confirms


def _bb(upper: float, lower: float, middle: float | None = None) -> tuple:
    """Trío `(upper, middle, lower)` — convención Observatory."""
    if middle is None:
        middle = round((upper + lower) / 2, 2)
    return (upper, middle, lower)


class TestBollingerNoBands:
    def test_both_bands_none_returns_empty(self) -> None:
        assert detect_bollinger_confirms(100.0, None, None) == []

    def test_only_1h_none(self) -> None:
        result = detect_bollinger_confirms(100.0, None, _bb(110.0, 90.0))
        # daily bounds 90-110, close 100 está dentro → no dispara
        assert result == []

    def test_only_daily_none(self) -> None:
        result = detect_bollinger_confirms(100.0, _bb(110.0, 90.0), None)
        assert result == []


class TestBollinger1HSuperior:
    def test_close_above_upper_1h_fires_put(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=501.50,
            bb_1h=_bb(500.00, 480.00),
            bb_daily=None,
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "BB sup 1H ($500.0)"
        assert c["sg"] == "PUT"
        assert c["tf"] == "1H"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 1.0
        assert c["age"] == 0

    def test_close_exactly_at_upper_1h_fires(self) -> None:
        # Observatory usa `>= ind["bbH"]["u"]` — empate cuenta.
        result = detect_bollinger_confirms(500.00, _bb(500.00, 480.00), None)
        assert len(result) == 1
        assert result[0]["d"] == "BB sup 1H ($500.0)"

    def test_close_below_upper_does_not_fire(self) -> None:
        result = detect_bollinger_confirms(499.99, _bb(500.00, 480.00), None)
        assert result == []


class TestBollinger1HInferior:
    def test_close_below_lower_1h_fires_call(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=479.00,
            bb_1h=_bb(500.00, 480.00),
            bb_daily=None,
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "BB inf 1H ($480.0)"
        assert c["sg"] == "CALL"
        assert c["tf"] == "1H"
        assert c["w"] == 3.0

    def test_close_exactly_at_lower_1h_fires(self) -> None:
        result = detect_bollinger_confirms(480.00, _bb(500.00, 480.00), None)
        assert len(result) == 1
        assert result[0]["d"] == "BB inf 1H ($480.0)"
        assert result[0]["sg"] == "CALL"


class TestBollingerDailySuperior:
    def test_close_above_upper_daily_fires_put(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=501.0,
            bb_1h=None,
            bb_daily=_bb(500.0, 400.0),
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "BB sup D ($500.0)"
        assert c["sg"] == "PUT"
        assert c["tf"] == "D"
        assert c["w"] == 1.0


class TestBollingerDailyInferior:
    def test_close_below_lower_daily_fires_call(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=399.0,
            bb_1h=None,
            bb_daily=_bb(500.0, 400.0),
        )
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "BB inf D ($400.0)"
        assert c["sg"] == "CALL"
        assert c["tf"] == "D"
        assert c["w"] == 1.0


class TestBollingerMultipleBands:
    def test_close_above_both_uppers_fires_two_puts(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=501.0,
            bb_1h=_bb(495.0, 480.0),
            bb_daily=_bb(500.0, 400.0),
        )
        assert len(result) == 2
        assert {c["d"] for c in result} == {"BB sup 1H ($495.0)", "BB sup D ($500.0)"}
        assert all(c["sg"] == "PUT" for c in result)

    def test_close_below_both_lowers_fires_two_calls(self) -> None:
        result = detect_bollinger_confirms(
            last_close_15m=395.0,
            bb_1h=_bb(500.0, 480.0),
            bb_daily=_bb(500.0, 400.0),
        )
        assert len(result) == 2
        assert {c["d"] for c in result} == {"BB inf 1H ($480.0)", "BB inf D ($400.0)"}
        assert all(c["sg"] == "CALL" for c in result)


class TestBollingerFormattingParity:
    """Paridad bit-exact con Observatory: valores redondeados a 2d se
    serializan con el trailing natural de Python (ej. 498.2, no 498.20).
    """

    def test_value_with_one_decimal_no_trailing_zero(self) -> None:
        # round(498.20, 2) == 498.2 en Python → f"${498.2}" == "$498.2"
        result = detect_bollinger_confirms(500.0, _bb(498.2, 480.0), None)
        assert result[0]["d"] == "BB sup 1H ($498.2)"

    def test_value_with_two_decimals_preserved(self) -> None:
        result = detect_bollinger_confirms(500.0, _bb(498.25, 480.0), None)
        assert result[0]["d"] == "BB sup 1H ($498.25)"

    def test_value_integer_shows_dot_zero(self) -> None:
        # float(500) == 500.0 → f"${500.0}" == "$500.0"
        result = detect_bollinger_confirms(500.0, _bb(500.0, 480.0), None)
        assert result[0]["d"] == "BB sup 1H ($500.0)"
