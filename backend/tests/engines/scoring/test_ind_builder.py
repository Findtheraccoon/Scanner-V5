"""Tests de build_ind_bundle (Sub-fase 5.3a).

Cubre:
- Campo por campo con warmup y datos completos.
- Fallback a neutro Observatory cuando no hay suficientes velas.
- Helpers internos `_pct_change` y `_last_bb_tuple`.

Los inputs de las funciones upstream (`sma`, `bollinger_bands`, `atr`,
`vol_ratio_intraday`, etc.) ya tienen sus tests dedicados; acá validamos
que el builder los orqueste correctamente y entregue las claves que
consume el wiring de 5.3b.
"""

from __future__ import annotations

from engines.scoring.ind_builder import (
    _last_bb_tuple,
    _pct_change,
    build_ind_bundle,
)


def _candle(o: float, h: float, low: float, c: float, v: float = 1000, dt: str = "") -> dict:
    return {"o": o, "h": h, "l": low, "c": c, "v": v, "dt": dt}


def _flat_series(n: int, close: float = 100.0, dt_prefix: str = "2025-04-01") -> list[dict]:
    """Helper: serie plana con dt incrementando por minuto."""
    return [
        _candle(close, close, close, close, v=1000, dt=f"{dt_prefix} {9 + i // 60:02d}:{i % 60:02d}:00")
        for i in range(n)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# _pct_change
# ═══════════════════════════════════════════════════════════════════════════


class TestPctChange:
    def test_empty_returns_zero(self) -> None:
        assert _pct_change([]) == 0.0

    def test_none_returns_zero(self) -> None:
        assert _pct_change(None) == 0.0

    def test_insufficient_candles_returns_zero(self) -> None:
        # n=1 requiere >=2
        assert _pct_change([_candle(100, 100, 100, 100)]) == 0.0

    def test_basic_positive_change(self) -> None:
        candles = [_candle(100, 100, 100, 100), _candle(100, 100, 100, 102)]
        assert _pct_change(candles) == 2.0

    def test_basic_negative_change(self) -> None:
        candles = [_candle(100, 100, 100, 100), _candle(100, 100, 100, 98)]
        assert _pct_change(candles) == -2.0

    def test_rounded_to_two_decimals(self) -> None:
        candles = [_candle(100, 100, 100, 100), _candle(100, 100, 100, 100.1234)]
        assert _pct_change(candles) == 0.12

    def test_zero_prev_returns_zero(self) -> None:
        # División protegida: prev <= 0 → 0
        candles = [_candle(0, 0, 0, 0), _candle(10, 10, 10, 10)]
        assert _pct_change(candles) == 0.0

    def test_n_2_compares_two_back(self) -> None:
        # n=2 toma prev = candles[-1 - 2] = candles[-3]
        candles = [
            _candle(100, 100, 100, 100),  # -3 (prev para n=2)
            _candle(100, 100, 100, 110),  # -2
            _candle(100, 100, 100, 120),  # -1 (cur)
        ]
        # cur=120 vs prev=100 → +20%
        assert _pct_change(candles, n=2) == 20.0


# ═══════════════════════════════════════════════════════════════════════════
# _last_bb_tuple
# ═══════════════════════════════════════════════════════════════════════════


class TestLastBBTuple:
    def test_returns_none_when_warmup(self) -> None:
        # Todos None → warmup incompleto
        bb = ([None, None], [None, None], [None, None])
        assert _last_bb_tuple(bb) is None

    def test_returns_none_when_any_is_none(self) -> None:
        bb = ([95.0, None], [100.0, 100.0], [105.0, 105.0])
        assert _last_bb_tuple(bb) is None

    def test_returns_upper_middle_lower_order(self) -> None:
        # bollinger_bands devuelve (lower, middle, upper)
        bb = ([95.0, 96.0], [100.0, 100.5], [105.0, 105.0])
        result = _last_bb_tuple(bb)
        assert result == (105.0, 100.5, 96.0)  # (upper, middle, lower)


# ═══════════════════════════════════════════════════════════════════════════
# build_ind_bundle — happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildIndBundleHappyPath:
    def test_returns_dict_with_all_keys(self) -> None:
        # Serie con suficientes velas para todos los indicadores:
        # bollinger_bands: window=20 → min 20 velas
        # bb_width: period=20 + 20 → min 40 velas
        # vol_sequence: n=4 → min 6 velas
        # vol_ratio_intraday: 4+ velas del día
        candles_daily = _flat_series(50, close=100.0)
        candles_1h = _flat_series(50, close=100.0)
        # 15m: mismo día para vol_ratio_intraday funcione
        candles_15m = [
            _candle(100, 100, 100, 100, v=1000, dt=f"2025-04-01 10:{i:02d}:00")
            for i in range(10)
        ]
        bundle = build_ind_bundle(
            candles_daily=candles_daily,
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            sim_date="2025-04-01",
        )
        # Todas las keys deben estar presentes (TypedDict lo garantiza pero
        # explicitamos por seguridad en uso downstream)
        for key in (
            "price", "bb_1h", "bb_daily", "bb_sq_1h", "gap_info",
            "vol_m", "vol_seq_m", "a_chg", "spy_chg", "bench_chg",
            "atr_daily", "atr_pct",
        ):
            assert key in bundle

    def test_price_is_last_close_15m(self) -> None:
        candles_daily = _flat_series(50)
        candles_1h = _flat_series(50)
        candles_15m = [
            _candle(100, 100, 100, 123.45, dt="2025-04-01 10:00:00"),
        ]
        # Pass insuficientes en otros para que no falle la función en None
        # pero sí popule price
        candles_15m = [_candle(100, 100, 100, 100)] * 9 + [
            _candle(100, 100, 100, 123.45)
        ]
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["price"] == 123.45

    def test_bb_daily_is_tuple_upper_middle_lower(self) -> None:
        # Construyo una serie con volatilidad conocida
        candles_daily = _flat_series(50, close=100.0)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        # Serie plana → upper = middle = lower
        assert bundle["bb_daily"] is not None
        upper, middle, lower = bundle["bb_daily"]
        assert upper == middle == lower == 100.0


class TestBuildIndBundleWarmup:
    def test_bb_daily_none_when_insufficient(self) -> None:
        # <20 velas daily → bollinger_bands retorna todo None
        candles_daily = _flat_series(10)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["bb_daily"] is None

    def test_bb_sq_1h_none_when_insufficient(self) -> None:
        # bb_width requiere period(20) + 20 = 40 velas mínimo
        candles_1h = _flat_series(30)
        candles_daily = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["bb_sq_1h"] is None

    def test_gap_info_none_when_less_than_2_daily_candles(self) -> None:
        candles_daily = [_candle(100, 100, 100, 100)]
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["gap_info"] is None

    def test_vol_m_neutral_when_insufficient_intraday(self) -> None:
        # <4 velas del día → 1.0 neutro
        candles_15m = [_candle(100, 100, 100, 100, dt="2025-04-01 10:00:00")]
        candles_1h = _flat_series(50)
        candles_daily = _flat_series(50)
        bundle = build_ind_bundle(
            candles_daily, candles_1h, candles_15m, sim_date="2025-04-01",
        )
        assert bundle["vol_m"] == 1.0

    def test_vol_seq_m_neutral_when_insufficient(self) -> None:
        # n=4 requiere >=6 velas
        candles_15m = _flat_series(3)
        candles_1h = _flat_series(50)
        candles_daily = _flat_series(50)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["vol_seq_m"] == {
            "growing": False, "declining": False, "count": 0,
        }

    def test_atr_none_when_insufficient(self) -> None:
        # atr requiere period+1 = 15 velas mínimo (default window=14)
        candles_daily = _flat_series(10)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["atr_daily"] is None
        assert bundle["atr_pct"] is None


class TestBuildIndBundleBenchmarks:
    def test_a_chg_is_pct_change_of_ticker_daily(self) -> None:
        candles_daily = [
            _candle(100, 100, 100, 100),
            _candle(100, 100, 100, 102),
        ]
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        assert bundle["a_chg"] == 2.0

    def test_spy_chg_zero_when_no_spy_daily(self) -> None:
        candles_daily = _flat_series(50)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(
            candles_daily, candles_1h, candles_15m, spy_daily=None,
        )
        assert bundle["spy_chg"] == 0.0

    def test_spy_chg_computed_from_spy_daily(self) -> None:
        candles_daily = _flat_series(50)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        spy = [_candle(100, 100, 100, 400), _candle(100, 100, 100, 404)]
        bundle = build_ind_bundle(
            candles_daily, candles_1h, candles_15m, spy_daily=spy,
        )
        assert bundle["spy_chg"] == 1.0

    def test_bench_chg_zero_when_no_bench_daily(self) -> None:
        candles_daily = _flat_series(50)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        bundle = build_ind_bundle(
            candles_daily, candles_1h, candles_15m, bench_daily=None,
        )
        assert bundle["bench_chg"] == 0.0

    def test_bench_chg_computed_from_bench_daily(self) -> None:
        candles_daily = _flat_series(50)
        candles_1h = _flat_series(50)
        candles_15m = _flat_series(10)
        qqq = [_candle(100, 100, 100, 500), _candle(100, 100, 100, 495)]
        bundle = build_ind_bundle(
            candles_daily, candles_1h, candles_15m, bench_daily=qqq,
        )
        assert bundle["bench_chg"] == -1.0


class TestBuildIndBundleAtrPct:
    def test_atr_pct_computed_from_atr_over_price(self) -> None:
        # Serie con volatilidad mínima controlada
        candles_daily = _flat_series(20, close=100.0)
        candles_1h = _flat_series(50)
        candles_15m = [_candle(100, 100, 100, 100, dt="2025-04-01 10:00:00")]
        bundle = build_ind_bundle(candles_daily, candles_1h, candles_15m)
        # Serie plana → atr_daily = 0 → atr_pct = 0
        assert bundle["atr_daily"] == 0.0
        assert bundle["atr_pct"] == 0.0
