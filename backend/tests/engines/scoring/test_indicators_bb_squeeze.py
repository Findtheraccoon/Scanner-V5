"""Tests de bb_width Observatory (Sub-fase 5.2c) — squeeze + expansion.

Port literal de Observatory `indicators.py:bb_width()` líneas 175-204.
Devuelve dict `{current, min20, percentile, isSqueeze, isExpanding}` o
`None` si no hay suficientes datos.

Casuísticas clave:
- Mínimo `period + 20` valores para retornar dict no-None.
- Percentile entre 0-100 (entero, redondeado).
- isSqueeze: percentile < 15 (estricto).
- isExpanding: 3 widths estrictamente crecientes.
"""

from __future__ import annotations

from engines.scoring.indicators import bb_width

# ═══════════════════════════════════════════════════════════════════════════
# Insufficient data
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidthInsufficient:
    def test_empty_returns_none(self) -> None:
        assert bb_width([]) is None

    def test_below_minimum_returns_none(self) -> None:
        # period=20 → mínimo 40 valores
        assert bb_width([100.0] * 39) is None

    def test_exactly_at_minimum_returns_dict(self) -> None:
        # period=20, len=40 → 21 widths posibles → últimos 20 → OK
        result = bb_width([100.0] * 40)
        assert result is not None
        assert "current" in result
        assert "isSqueeze" in result


# ═══════════════════════════════════════════════════════════════════════════
# Constante → squeeze permanente
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidthConstant:
    def test_constant_series_width_zero(self) -> None:
        result = bb_width([100.0] * 50)
        assert result is not None
        assert result["current"] == 0.0
        assert result["min20"] == 0.0

    def test_constant_series_no_expansion(self) -> None:
        # 3 widths iguales (todos 0) — no es estrictamente creciente
        result = bb_width([100.0] * 50)
        assert result is not None
        assert result["isExpanding"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Percentile + squeeze
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidthPercentile:
    def test_percentile_range_0_to_100(self) -> None:
        # Serie volátil — percentile debe quedar en rango válido
        values = [100.0 + (i % 7) * 0.5 for i in range(50)]
        result = bb_width(values)
        assert result is not None
        assert 0 <= result["percentile"] <= 100

    def test_squeeze_when_current_at_minimum(self) -> None:
        # 20 widths idénticos en su mínimo → percentile=0, squeeze True
        values = [100.0] * 50
        result = bb_width(values)
        assert result is not None
        # current == min20 → numerador=0 → percentile=0
        assert result["percentile"] == 0
        assert result["isSqueeze"] is True

    def test_no_squeeze_when_current_at_maximum(self) -> None:
        # 40 velas planas (widths bajos) + tail con saltos crecientes
        # → la última ventana tiene la stdev máxima → current = max20
        # → percentile=100 → isSqueeze=False
        values = [100.0] * 40 + [100.5, 101.5, 103.0, 105.0, 108.0]
        result = bb_width(values)
        assert result is not None
        assert result["isSqueeze"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Expansion
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidthExpanding:
    def test_constant_then_diverging_expands(self) -> None:
        # 40 velas planas (mínimo para retornar dict) + tail divergente
        # → últimas 3 ventanas tienen stdev cada vez mayor
        values = [100.0] * 40 + [101.0, 102.0, 104.0, 108.0, 116.0]
        result = bb_width(values)
        assert result is not None
        assert result["isExpanding"] is True

    def test_constant_series_not_expanding(self) -> None:
        result = bb_width([100.0] * 50)
        assert result is not None
        assert result["isExpanding"] is False

    def test_diverging_then_collapsing_not_expanding(self) -> None:
        # Tail con valores cada vez más cercanos al promedio →
        # las últimas 3 ventanas tienen widths NO estrictamente
        # crecientes (la última es menor que las previas).
        values = [100.0] * 40 + [108.0, 104.0, 102.0, 101.0, 100.5]
        result = bb_width(values)
        assert result is not None
        assert result["isExpanding"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Override de period y k
# ═══════════════════════════════════════════════════════════════════════════


class TestBBWidthCustomParams:
    def test_custom_period_changes_minimum_length(self) -> None:
        # period=10 → mínimo 30
        assert bb_width([100.0] * 29, period=10) is None
        assert bb_width([100.0] * 30, period=10) is not None

    def test_custom_k_scales_width(self) -> None:
        # Con misma serie, k mayor → width mayor (pero percentile y
        # isSqueeze son invariantes a la escala porque normalizan).
        values = [100.0 + (i % 5) * 0.3 for i in range(50)]
        r1 = bb_width(values, k=2.0)
        r2 = bb_width(values, k=4.0)
        assert r1 is not None and r2 is not None
        assert r2["current"] > r1["current"]
