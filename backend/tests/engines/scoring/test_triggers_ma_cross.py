"""Tests de Cruce MA20/40 1H (Fase 4c)."""

from __future__ import annotations

from engines.scoring.triggers import detect_ma_cross_1h


def _candle(c: float) -> dict:
    """Vela minimalista — solo usamos `c` para el cross de MAs."""
    return {"dt": "2025-01-15 10:00:00", "o": c, "h": c + 0.1, "l": c - 0.1, "c": c, "v": 1000}


# ═══════════════════════════════════════════════════════════════════════════
# Pre-requisitos
# ═══════════════════════════════════════════════════════════════════════════


class TestPrerequisites:
    def test_insufficient_candles_returns_empty(self) -> None:
        # 41 < 42 mínimo
        candles = [_candle(100.0 + i * 0.1) for i in range(41)]
        assert detect_ma_cross_1h(candles) == []

    def test_empty_returns_empty(self) -> None:
        assert detect_ma_cross_1h([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# Cruce alcista
# ═══════════════════════════════════════════════════════════════════════════


class TestBullishCross:
    def test_fires_when_ma20_crosses_above_ma40(self) -> None:
        """Construcción hand-computed:

            closes[0..21]  = 100  (22 velas altas)
            closes[22..41] = 90   (20 velas bajas)
            closes[42..43] = 200  (2 spikes)

        prev (slice[:-2] = closes[0..41]):
            MA20_prev = mean(closes[22..41]) = 90
            MA40_prev = mean(closes[2..41]) = (20*100 + 20*90)/40 = 95
            → 90 < 95 ✓

        curr (closes[0..43]):
            MA20_curr = mean(closes[24..43]) = (18*90 + 2*200)/20 = 101
            MA40_curr = mean(closes[4..43]) = (18*100 + 20*90 + 2*200)/40 = 100.0
            → 101 > 100 ✓  (cruce!)
        """
        closes = [100.0] * 22 + [90.0] * 20 + [200.0, 200.0]
        candles = [_candle(c) for c in closes]
        triggers = detect_ma_cross_1h(candles)
        match = [t for t in triggers if t["d"] == "Cruce alcista MA20/40"]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 2.0
        assert match[0]["tf"] == "1H"


# ═══════════════════════════════════════════════════════════════════════════
# Cruce bajista
# ═══════════════════════════════════════════════════════════════════════════


class TestBearishCross:
    def test_fires_when_ma20_crosses_below_ma40(self) -> None:
        """Espejo del bullish: subida sostenida + 2 crashes al final."""
        closes = [100.0] * 22 + [110.0] * 20 + [10.0, 10.0]
        candles = [_candle(c) for c in closes]
        triggers = detect_ma_cross_1h(candles)
        match = [t for t in triggers if t["d"] == "Cruce bajista MA20/40"]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 2.0


# ═══════════════════════════════════════════════════════════════════════════
# No-cross
# ═══════════════════════════════════════════════════════════════════════════


class TestNoCross:
    def test_no_cross_when_ma20_always_above(self) -> None:
        # Precio siempre subiendo suavemente: MA20 queda arriba de MA40
        # todo el tiempo (no hay cruce, aunque la relación se mantiene).
        closes = [100.0 + i * 0.5 for i in range(50)]
        candles = [_candle(c) for c in closes]
        triggers = detect_ma_cross_1h(candles)
        assert not any("Cruce" in t["d"] for t in triggers)

    def test_no_cross_when_mas_flat(self) -> None:
        closes = [100.0] * 50
        candles = [_candle(c) for c in closes]
        # MA20 == MA40 en todo momento. Strict `<`/`>` no dispara.
        triggers = detect_ma_cross_1h(candles)
        assert not triggers
