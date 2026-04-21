"""Tests de today_candles + vol_ratio_intraday (Sub-fase 5.2a).

Port literal de Observatory `indicators.py` líneas 64-108. Casuísticas:

**today_candles:**
    - Vacío → []
    - sim_date explícito filtra por prefix
    - sim_date None infiere del último candle (formatos " " y "T")

**vol_ratio_intraday:**
    - <4 velas del día → 1.0 neutro
    - Mediana protegida (≤ 0 → 1.0)
    - Penúltima completa vs mediana de las previas (excluye [-1] y [-2])
    - Resistencia a outlier de apertura (cualidad de la mediana)
"""

from __future__ import annotations

from engines.scoring.indicators import today_candles, vol_ratio_intraday


def _candle(dt: str, v: float) -> dict:
    """Helper: candle mínima con dt + volumen (resto irrelevante)."""
    return {"o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": v, "dt": dt}


# ═══════════════════════════════════════════════════════════════════════════
# today_candles
# ═══════════════════════════════════════════════════════════════════════════


class TestTodayCandlesEmpty:
    def test_empty_list_returns_empty(self) -> None:
        assert today_candles([]) == []

    def test_empty_with_sim_date_returns_empty(self) -> None:
        assert today_candles([], sim_date="2025-04-01") == []


class TestTodayCandlesExplicitSimDate:
    def test_filters_by_prefix(self) -> None:
        candles = [
            _candle("2025-03-31 15:30:00", 100),
            _candle("2025-04-01 09:30:00", 200),
            _candle("2025-04-01 09:45:00", 300),
            _candle("2025-04-02 09:30:00", 400),
        ]
        result = today_candles(candles, sim_date="2025-04-01")
        assert len(result) == 2
        assert result[0]["v"] == 200
        assert result[1]["v"] == 300

    def test_no_match_returns_empty(self) -> None:
        candles = [_candle("2025-04-01 09:30:00", 100)]
        assert today_candles(candles, sim_date="2025-04-02") == []


class TestTodayCandlesInferredSimDate:
    def test_infers_from_last_candle_space_format(self) -> None:
        # Observatory: split en " " si está presente.
        candles = [
            _candle("2025-04-01 15:30:00", 100),
            _candle("2025-04-02 09:30:00", 200),
            _candle("2025-04-02 09:45:00", 300),
        ]
        result = today_candles(candles)
        assert len(result) == 2
        assert all(c["dt"].startswith("2025-04-02") for c in result)

    def test_infers_from_last_candle_iso_format(self) -> None:
        # Formato ISO con "T" — Observatory lo soporta también.
        candles = [
            _candle("2025-04-01T15:30:00", 100),
            _candle("2025-04-02T09:30:00", 200),
        ]
        result = today_candles(candles)
        assert len(result) == 1
        assert result[0]["v"] == 200

    def test_date_only_dt(self) -> None:
        # dt sin hora — el split no encuentra " " ni "T", usa el dt entero.
        candles = [_candle("2025-04-01", 100), _candle("2025-04-02", 200)]
        result = today_candles(candles)
        assert len(result) == 1
        assert result[0]["v"] == 200


# ═══════════════════════════════════════════════════════════════════════════
# vol_ratio_intraday
# ═══════════════════════════════════════════════════════════════════════════


class TestVolRatioIntradayInsufficientData:
    def test_empty_returns_neutral(self) -> None:
        assert vol_ratio_intraday([]) == 1.0

    def test_three_candles_today_returns_neutral(self) -> None:
        # Observatory: <4 → 1.0 (necesita 3 completas + 1 actual)
        candles = [
            _candle("2025-04-01 09:30:00", 1000),
            _candle("2025-04-01 09:45:00", 500),
            _candle("2025-04-01 10:00:00", 400),
        ]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 1.0

    def test_zero_intraday_candles_returns_neutral(self) -> None:
        # sim_date no matchea ninguna vela
        candles = [_candle("2025-03-31 15:30:00", 1000)]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 1.0


class TestVolRatioIntradayBasic:
    def test_four_candles_uses_first_two_as_median(self) -> None:
        # tc[:-2] = [v=100, v=200] → median=150
        # completed = tc[-2] (v=300)
        # ratio = 300/150 = 2.0
        candles = [
            _candle("2025-04-01 09:30:00", 100),
            _candle("2025-04-01 09:45:00", 200),
            _candle("2025-04-01 10:00:00", 300),  # completed
            _candle("2025-04-01 10:15:00", 999),  # current (excluida)
        ]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 2.0

    def test_five_candles_median_of_three(self) -> None:
        # tc[:-2] = [100, 200, 300] → median=200
        # completed = tc[-2] (v=600) → 600/200=3.0
        candles = [
            _candle("2025-04-01 09:30:00", 100),
            _candle("2025-04-01 09:45:00", 200),
            _candle("2025-04-01 10:00:00", 300),
            _candle("2025-04-01 10:15:00", 600),  # completed
            _candle("2025-04-01 10:30:00", 999),  # current
        ]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 3.0


class TestVolRatioIntradayMedianResistance:
    def test_opening_outlier_does_not_inflate_median(self) -> None:
        # La vela 9:30 con volumen huge no debe sesgar (cualidad clave
        # de la mediana — razón documentada en Observatory).
        # tc[:-2] = [10000(outlier), 100, 100] → median=100
        # completed = 200 → 200/100 = 2.0
        candles = [
            _candle("2025-04-01 09:30:00", 10000),  # outlier apertura
            _candle("2025-04-01 09:45:00", 100),
            _candle("2025-04-01 10:00:00", 100),
            _candle("2025-04-01 10:15:00", 200),  # completed
            _candle("2025-04-01 10:30:00", 999),  # current
        ]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 2.0


class TestVolRatioIntradayProtectedDivision:
    def test_zero_median_returns_neutral(self) -> None:
        # Todos los previos completos en 0 → median=0 → división protegida
        candles = [
            _candle("2025-04-01 09:30:00", 0),
            _candle("2025-04-01 09:45:00", 0),
            _candle("2025-04-01 10:00:00", 500),  # completed
            _candle("2025-04-01 10:15:00", 999),  # current
        ]
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 1.0


class TestVolRatioIntradayMixedDays:
    def test_only_today_candles_count(self) -> None:
        # Velas de días anteriores deben ignorarse — solo "hoy" cuenta.
        candles = [
            _candle("2025-03-31 09:30:00", 99999),  # día previo, ignorado
            _candle("2025-03-31 15:30:00", 99999),  # día previo, ignorado
            _candle("2025-04-01 09:30:00", 100),
            _candle("2025-04-01 09:45:00", 200),
            _candle("2025-04-01 10:00:00", 300),  # completed
            _candle("2025-04-01 10:15:00", 999),  # current
        ]
        # tc[:-2] = [100, 200] → median=150 → 300/150=2.0
        assert vol_ratio_intraday(candles, sim_date="2025-04-01") == 2.0

    def test_inferred_sim_date_from_last_candle(self) -> None:
        # Sin sim_date explícito, infiere del último candle.
        candles = [
            _candle("2025-03-31 15:30:00", 99999),
            _candle("2025-04-01 09:30:00", 100),
            _candle("2025-04-01 09:45:00", 200),
            _candle("2025-04-01 10:00:00", 600),  # completed
            _candle("2025-04-01 10:15:00", 999),  # current → infiere 04-01
        ]
        # tc[:-2] = [100, 200] → median=150 → 600/150=4.0
        assert vol_ratio_intraday(candles) == 4.0
