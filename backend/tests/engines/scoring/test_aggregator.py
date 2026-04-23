"""Tests de aggregator 1-minuto → 15M/1H (Fase 5.4a)."""

from __future__ import annotations

from engines.scoring.aggregator import aggregate_to_1h, aggregate_to_15m


def _c(dt: str, o: float, h: float, low: float, c: float, v: int = 100) -> dict:
    return {"dt": dt, "o": o, "h": h, "l": low, "c": c, "v": v}


# ═══════════════════════════════════════════════════════════════════════════
# 15M aggregation
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregate15M:
    def test_empty_returns_empty(self) -> None:
        assert aggregate_to_15m([]) == []

    def test_single_minute_produces_partial_bucket(self) -> None:
        c = [_c("2025-01-02 09:30:00", 100, 101, 99, 100.5)]
        result = aggregate_to_15m(c)
        assert len(result) == 1
        assert result[0]["dt"] == "2025-01-02 09:30:00"
        assert result[0]["o"] == 100
        assert result[0]["c"] == 100.5

    def test_full_bucket_aggregates_ohlc(self) -> None:
        # 15 minutos 09:30-09:44 cubre bucket "09:30"
        candles = [
            _c(f"2025-01-02 09:{30 + i}:00", 100 + i * 0.1, 101 + i * 0.1, 99 + i * 0.1, 100 + i * 0.1 + 0.5, v=1000)
            for i in range(15)
        ]
        result = aggregate_to_15m(candles)
        assert len(result) == 1
        b = result[0]
        assert b["dt"] == "2025-01-02 09:30:00"
        assert b["o"] == 100.0  # open del primer 1min (09:30)
        assert b["c"] == 100 + 14 * 0.1 + 0.5  # close del último 1min (09:44)
        assert b["h"] == 101 + 14 * 0.1  # max high
        assert b["l"] == 99.0  # min low (del primer minuto)
        assert b["v"] == 15000  # suma

    def test_two_buckets(self) -> None:
        # 30 minutos 09:30-09:59 → 2 buckets [09:30, 09:45]
        candles = [
            _c(f"2025-01-02 09:{30 + i}:00", 100, 100, 100, 100)
            for i in range(30)
        ]
        result = aggregate_to_15m(candles)
        assert len(result) == 2
        assert result[0]["dt"] == "2025-01-02 09:30:00"
        assert result[1]["dt"] == "2025-01-02 09:45:00"

    def test_partial_last_bucket_with_until_dt(self) -> None:
        # 30 minutos pero until_dt corta en 09:45 → 2 buckets, el último
        # solo con 1 minuto
        candles = [
            _c(f"2025-01-02 09:{30 + i}:00", 100 + i, 100 + i, 100 + i, 100 + i)
            for i in range(30)
        ]
        result = aggregate_to_15m(candles, until_dt="2025-01-02 09:45:00")
        assert len(result) == 2
        # Primer bucket 09:30: completa [09:30, 09:44]
        assert result[0]["dt"] == "2025-01-02 09:30:00"
        # Segundo bucket 09:45: solo 1 minuto (el de 09:45 mismo)
        assert result[1]["dt"] == "2025-01-02 09:45:00"
        assert result[1]["o"] == 115  # open del 1min 09:45
        assert result[1]["c"] == 115  # close del 1min 09:45

    def test_canonical_convention_matches_price_at_signal(self) -> None:
        """Regresión: confirma que al momento T=12:30, la vela 15M `12:30`
        contiene solo el minuto 12:30 con close=close del 1min 12:30."""
        candles = [
            _c("2025-01-02 12:29:00", 513, 513, 512, 512.5),  # bucket 12:15
            _c("2025-01-02 12:30:00", 509.7, 509.7, 508.93, 509.086),  # bucket 12:30 (inicio)
        ]
        result = aggregate_to_15m(candles, until_dt="2025-01-02 12:30:00")
        assert len(result) == 2
        assert result[1]["dt"] == "2025-01-02 12:30:00"
        assert result[1]["c"] == 509.086


class TestAggregate15MBuckets:
    def test_bucket_boundaries_00_15_30_45(self) -> None:
        """Buckets agrupan por `minute // 15`. El `dt` = primera 1min del bucket."""
        candles = [
            _c("2025-01-02 10:14:00", 100, 100, 100, 100),  # bucket 00 → dt=10:14
            _c("2025-01-02 10:15:00", 200, 200, 200, 200),  # bucket 15 → dt=10:15
            _c("2025-01-02 10:30:00", 300, 300, 300, 300),  # bucket 30 → dt=10:30
            _c("2025-01-02 10:45:00", 400, 400, 400, 400),  # bucket 45 → dt=10:45
            _c("2025-01-02 10:59:00", 500, 500, 500, 500),  # bucket 45
        ]
        result = aggregate_to_15m(candles)
        assert [r["dt"][11:16] for r in result] == ["10:14", "10:15", "10:30", "10:45"]
        # El último bucket (45) incluye 10:45 y 10:59
        assert result[3]["c"] == 500


# ═══════════════════════════════════════════════════════════════════════════
# 1H aggregation
# ═══════════════════════════════════════════════════════════════════════════


class TestAggregate1H:
    def test_empty_returns_empty(self) -> None:
        assert aggregate_to_1h([]) == []

    def test_full_hour_aggregates(self) -> None:
        # 10:00 - 10:59 = 60 minutos, bucket "10:00"
        candles = [
            _c(f"2025-01-02 10:{i:02d}:00", 100 + i, 101 + i, 99 + i, 100 + i + 0.5)
            for i in range(60)
        ]
        result = aggregate_to_1h(candles)
        assert len(result) == 1
        b = result[0]
        assert b["dt"] == "2025-01-02 10:00:00"
        assert b["o"] == 100
        assert b["c"] == 100 + 59 + 0.5
        assert b["h"] == 101 + 59
        assert b["l"] == 99

    def test_partial_first_bucket_market_open(self) -> None:
        """Mercado abre 09:30 — el `dt` del bucket es la primera 1min (09:30)."""
        candles = [
            _c(f"2025-01-02 09:{30 + i}:00", 100, 100, 100, 100)
            for i in range(30)  # 09:30 - 09:59
        ]
        result = aggregate_to_1h(candles)
        assert len(result) == 1
        assert result[0]["dt"] == "2025-01-02 09:30:00"  # dt = primera 1min
        assert result[0]["v"] == 30 * 100  # solo 30 minutos

    def test_until_dt_cuts_partial_bucket(self) -> None:
        """Until 12:30 → bucket 12:00 parcial con [12:00, 12:30]."""
        candles = [
            _c(f"2025-01-02 11:{i:02d}:00", 100, 100, 100, 100)
            for i in range(60)  # 11:00-11:59 completo
        ] + [
            _c(f"2025-01-02 12:{i:02d}:00", 200, 200, 200, 200 + i * 0.1)
            for i in range(31)  # 12:00 - 12:30
        ]
        result = aggregate_to_1h(candles, until_dt="2025-01-02 12:30:00")
        assert len(result) == 2
        assert result[0]["dt"] == "2025-01-02 11:00:00"
        assert result[1]["dt"] == "2025-01-02 12:00:00"
        # El bucket 12:00 parcial tiene 31 minutos (12:00 a 12:30 inclusive)
        assert result[1]["c"] == 200 + 30 * 0.1


class TestAggregate1HBuckets:
    def test_buckets_aligned_to_hh00(self) -> None:
        candles = [
            _c("2025-01-02 09:59:00", 100, 100, 100, 100),
            _c("2025-01-02 10:00:00", 200, 200, 200, 200),
            _c("2025-01-02 10:59:00", 300, 300, 300, 300),
            _c("2025-01-02 11:00:00", 400, 400, 400, 400),
        ]
        result = aggregate_to_1h(candles)
        assert [r["dt"][11:13] for r in result] == ["09", "10", "11"]
