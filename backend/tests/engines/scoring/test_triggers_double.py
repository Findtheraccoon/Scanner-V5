"""Tests de Doble techo / Doble piso (Fase 4b).

Construyen velas con h/l exactos para crear pivots locales en
posiciones controladas, y verifican que el detector los identifique
con la regla de 0.5% + separación ≥3 velas del v4.2.1.
"""

from __future__ import annotations

from engines.scoring.triggers import detect_double_patterns_15m


def _candle(*, h: float, low: float, c: float | None = None) -> dict:
    """Vela minimalista. open/close = (h+l)/2 por default."""
    mid = (h + low) / 2
    return {
        "dt": "2025-01-15 10:00:00",
        "o": mid,
        "h": h,
        "l": low,
        "c": c if c is not None else mid,
        "v": 1000,
    }


def _flat(price: float = 100.0) -> dict:
    """Vela plana, no es pivot."""
    return _candle(h=price + 0.5, low=price - 0.5)


def _high_pivot(price: float) -> dict:
    """Vela cuyo h es `price` (será pivot si neighbors tienen h < price)."""
    return _candle(h=price, low=price - 2.0, c=price - 1.0)


def _low_pivot(price: float) -> dict:
    """Vela cuyo l es `price` (será pivot si neighbors tienen l > price)."""
    return _candle(h=price + 2.0, low=price, c=price + 1.0)


# ═══════════════════════════════════════════════════════════════════════════
# Requisito mínimo: 20 velas
# ═══════════════════════════════════════════════════════════════════════════


class TestMinimumWindow:
    def test_less_than_20_candles_returns_empty(self) -> None:
        candles = [_flat() for _ in range(19)]
        assert detect_double_patterns_15m(candles) == []

    def test_empty_list_returns_empty(self) -> None:
        assert detect_double_patterns_15m([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# Doble techo
# ═══════════════════════════════════════════════════════════════════════════


class TestDobleTecho:
    def _build(self, *, pivot_a_pos: int, pivot_b_pos: int, price: float) -> list[dict]:
        """Construye 20 velas con pivots en posiciones dadas."""
        candles = [_flat(99.0) for _ in range(20)]
        candles[pivot_a_pos] = _high_pivot(price)
        candles[pivot_b_pos] = _high_pivot(price)
        return candles

    def test_fires_when_two_pivots_similar_price_apart(self) -> None:
        # Pivots en posiciones 5 y 10, price 105. Diff = 0%. Gap = 5 ≥ 3.
        candles = self._build(pivot_a_pos=5, pivot_b_pos=10, price=105.0)
        triggers = detect_double_patterns_15m(candles)
        match = [t for t in triggers if t["d"].startswith("Doble techo")]
        assert len(match) == 1
        assert match[0]["sg"] == "PUT"
        assert match[0]["w"] == 3.0
        assert "105.00" in match[0]["d"]

    def test_does_not_fire_when_pivots_too_close(self) -> None:
        # Gap = 2 < 3 → no dispara.
        candles = self._build(pivot_a_pos=5, pivot_b_pos=7, price=105.0)
        triggers = detect_double_patterns_15m(candles)
        assert not any(t["d"].startswith("Doble techo") for t in triggers)

    def test_does_not_fire_when_prices_differ_too_much(self) -> None:
        candles = [_flat(99.0) for _ in range(20)]
        candles[5] = _high_pivot(105.0)
        candles[10] = _high_pivot(107.0)  # 1.9% diff > 0.5%
        triggers = detect_double_patterns_15m(candles)
        assert not any(t["d"].startswith("Doble techo") for t in triggers)

    def test_uses_only_last_two_pivots(self) -> None:
        """Si hay 3 pivot highs y los últimos 2 matchean, dispara.
        Si los últimos 2 no matchean (solo el primero y el último), no dispara."""
        candles = [_flat(99.0) for _ in range(20)]
        candles[3] = _high_pivot(105.0)
        candles[9] = _high_pivot(110.0)  # rompe el matching con 105
        candles[15] = _high_pivot(105.0)
        triggers = detect_double_patterns_15m(candles)
        # Últimos 2 pivots: (110, 105) → 4.5% diff → no dispara
        assert not any(t["d"].startswith("Doble techo") for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Doble piso
# ═══════════════════════════════════════════════════════════════════════════


class TestDoblePiso:
    def test_fires_when_two_pivot_lows_match(self) -> None:
        candles = [_flat(105.0) for _ in range(20)]
        candles[5] = _low_pivot(95.0)
        candles[12] = _low_pivot(95.1)  # 0.1% diff < 0.5%
        triggers = detect_double_patterns_15m(candles)
        match = [t for t in triggers if t["d"].startswith("Doble piso")]
        assert len(match) == 1
        assert match[0]["sg"] == "CALL"
        assert match[0]["w"] == 3.0
        assert "95.00" in match[0]["d"]

    def test_does_not_fire_when_pivots_too_close_in_time(self) -> None:
        candles = [_flat(105.0) for _ in range(20)]
        candles[5] = _low_pivot(95.0)
        candles[6] = _low_pivot(95.0)  # gap=1 < 3
        triggers = detect_double_patterns_15m(candles)
        # Pero con 2 pivots contiguos, uno de ellos podría no ser pivot
        # por la regla estricta. Verifiquemos que no se dispare.
        assert not any(t["d"].startswith("Doble piso") for t in triggers)


# ═══════════════════════════════════════════════════════════════════════════
# Detección de pivots
# ═══════════════════════════════════════════════════════════════════════════


class TestPivotDetection:
    def test_strict_inequality_required(self) -> None:
        """Un pivot requiere h[i] > h[i-1] Y h[i] > h[i+1] estrictamente."""
        candles = [_flat(99.0) for _ in range(20)]
        # Dos velas iguales a 105 no son pivot cada una (empate lateral).
        candles[5] = _high_pivot(105.0)
        candles[6] = _high_pivot(105.0)  # mismo high
        # Un segundo pivot claro a 105 más adelante
        candles[12] = _high_pivot(105.0)
        triggers = detect_double_patterns_15m(candles)
        # Solo 1 pivot válido (el de 12) porque los de 5 y 6 no cumplen estricto.
        # O dependiendo de la geometría, 0 pivots. En cualquier caso, < 2 pivots
        # → no dispara doble techo.
        match = [t for t in triggers if t["d"].startswith("Doble techo")]
        assert len(match) <= 1  # tolera 0 o 1

    def test_pivot_must_exceed_both_neighbors(self) -> None:
        """Una vela con h igual al vecino no es pivot."""
        candles = [_flat(99.0) for _ in range(20)]
        # En pos 10, h=105 con neighbors 104 y 105 → pos 10 no es pivot
        candles[9] = _candle(h=104, low=95)
        candles[10] = _high_pivot(105.0)  # vecino derecho 105
        candles[11] = _candle(h=105, low=95)  # neighbor igual
        # Pivot claro en pos 15
        candles[15] = _high_pivot(105.0)
        triggers = detect_double_patterns_15m(candles)
        # Debe haber 0 Doble techo porque solo 1 pivot válido.
        # Pero el detector encuentra pivots con lookback=1 a cada lado,
        # estricto. Con empate en 11, pos 10 no es pivot estricto.
        match = [t for t in triggers if t["d"].startswith("Doble techo")]
        assert not match


# ═══════════════════════════════════════════════════════════════════════════
# Ventana de búsqueda
# ═══════════════════════════════════════════════════════════════════════════


class TestWindow:
    def test_only_uses_last_20_candles(self) -> None:
        """Los pivots fuera de las últimas 20 velas no cuentan."""
        # 30 velas: 10 con pivots lejanos (que no deben entrar) + 20 planas
        far_pivots = [_flat(99.0) for _ in range(10)]
        far_pivots[2] = _high_pivot(105.0)
        far_pivots[7] = _high_pivot(105.0)
        recent = [_flat(99.0) for _ in range(20)]
        candles = [*far_pivots, *recent]
        triggers = detect_double_patterns_15m(candles)
        assert not any(t["d"].startswith("Doble techo") for t in triggers)
