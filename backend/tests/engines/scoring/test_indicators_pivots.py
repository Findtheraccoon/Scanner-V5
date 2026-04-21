"""Tests de find_pivots + key_levels (Sub-fase 5.2e).

Port literal de Observatory `scoring.py` líneas 95-179. Casuísticas:

**find_pivots:**
- < lookback velas → vacío
- Pivot estricto: 5-vela window con centro mayor (high) o menor (low)
  que las 4 vecinas
- Cluster por tolerance comparado contra `group[0]` (no promedio)
- Top 4 por count `tx` descendente

**key_levels:**
- MAs daily clasificadas por posición vs precio
- BB labels con flechas unicode `↑↓` y `m`
- Dedup <0.2%: pivots fusionan label, otros se descartan
- Filtro >0.1% del precio para entrar a r/s
- Top 4 cada lado
"""

from __future__ import annotations

from engines.scoring.indicators import find_pivots, key_levels


def _candle(h: float, low: float) -> dict:
    """Helper: solo h y l importan para find_pivots."""
    return {"o": low, "h": h, "l": low, "c": h, "v": 1000, "dt": ""}


# ═══════════════════════════════════════════════════════════════════════════
# find_pivots — insufficient data
# ═══════════════════════════════════════════════════════════════════════════


class TestFindPivotsInsufficient:
    def test_empty_returns_empty_dict(self) -> None:
        assert find_pivots([]) == {"r": [], "s": []}

    def test_below_lookback_returns_empty(self) -> None:
        # default lookback=50 → <50 velas devuelve vacío
        candles = [_candle(100, 99) for _ in range(49)]
        assert find_pivots(candles) == {"r": [], "s": []}


# ═══════════════════════════════════════════════════════════════════════════
# find_pivots — detección estricta
# ═══════════════════════════════════════════════════════════════════════════


class TestFindPivotsDetection:
    def test_single_pivot_high_detected(self) -> None:
        # Vela en idx 5 con h=110, vecinas 4 lados con h=100
        # lookback=10 → toma todas. Loop range(2, 8) = [2..7]
        candles = [_candle(100, 90)] * 5 + [_candle(110, 90)] + [_candle(100, 90)] * 4
        result = find_pivots(candles, lookback=10)
        assert len(result["r"]) == 1
        assert result["r"][0]["lv"] == 110.0
        assert result["r"][0]["tx"] == 1

    def test_single_pivot_low_detected(self) -> None:
        candles = [_candle(110, 100)] * 5 + [_candle(110, 90)] + [_candle(110, 100)] * 4
        result = find_pivots(candles, lookback=10)
        assert len(result["s"]) == 1
        assert result["s"][0]["lv"] == 90.0

    def test_equal_neighbors_no_pivot(self) -> None:
        # Estricto `>`: si una vecina iguala el centro, NO es pivot.
        candles = [_candle(100, 90)] * 4 + [_candle(110, 90), _candle(110, 90)] + [_candle(100, 90)] * 4
        result = find_pivots(candles, lookback=10)
        assert result["r"] == []

    def test_pivot_in_first_two_or_last_two_ignored(self) -> None:
        # Loop range(2, len-2) excluye los 2 extremos a cada lado.
        # Pivot en idx 0 o idx 9 (de 10) no se detecta.
        candles = [_candle(110, 90)] + [_candle(100, 95)] * 8 + [_candle(110, 90)]
        result = find_pivots(candles, lookback=10)
        assert result["r"] == []


# ═══════════════════════════════════════════════════════════════════════════
# find_pivots — clustering
# ═══════════════════════════════════════════════════════════════════════════


class TestFindPivotsClustering:
    def test_two_close_pivots_merge_into_one_cluster(self) -> None:
        # 2 pivots highs en 100.0 y 100.1 (diff 0.1%) con tolerance 0.3%
        # → cluster con tx=2 y lv=promedio=100.05
        # 12 velas — 2 pivots en idx 3 y 8 (range 2..9 cubre)
        candles = [
            _candle(95, 90),  # 0
            _candle(95, 90),  # 1
            _candle(95, 90),  # 2
            _candle(100.0, 90),  # 3 — pivot
            _candle(95, 90),  # 4
            _candle(95, 90),  # 5
            _candle(95, 90),  # 6
            _candle(95, 90),  # 7
            _candle(100.1, 90),  # 8 — pivot
            _candle(95, 90),  # 9
            _candle(95, 90),  # 10
            _candle(95, 90),  # 11
        ]
        result = find_pivots(candles, lookback=12, tolerance=0.003)
        assert len(result["r"]) == 1
        assert result["r"][0]["tx"] == 2
        assert result["r"][0]["lv"] == 100.05

    def test_far_pivots_separate_clusters(self) -> None:
        # 2 pivots a 100 y 110 (diff 10%) → clusters separados
        candles = [
            _candle(95, 90), _candle(95, 90), _candle(95, 90),
            _candle(100, 90),  # 3 — pivot
            _candle(95, 90), _candle(95, 90), _candle(95, 90), _candle(95, 90),
            _candle(110, 90),  # 8 — pivot
            _candle(95, 90), _candle(95, 90), _candle(95, 90),
        ]
        result = find_pivots(candles, lookback=12, tolerance=0.003)
        assert len(result["r"]) == 2
        # Top sort por tx desc — ambos tienen tx=1, mantiene orden inicial
        # del sorted clusters output. Ambos tx=1.
        assert all(c["tx"] == 1 for c in result["r"])

    def test_top_4_limit_by_tx_descending(self) -> None:
        # 5 clusters distintos (todos tx=1) → debería devolver solo 4
        # Necesitamos 5 pivots en idx [2..lookback-3], lookback grande.
        candles = [_candle(50, 10) for _ in range(60)]
        # 5 picos espaciados en idx 5, 15, 25, 35, 45 con h diferente
        for idx, h in [(5, 100), (15, 110), (25, 120), (35, 130), (45, 140)]:
            candles[idx] = _candle(h, 10)
        result = find_pivots(candles, lookback=50, tolerance=0.003)
        assert len(result["r"]) == 4  # top 4


# ═══════════════════════════════════════════════════════════════════════════
# key_levels
# ═══════════════════════════════════════════════════════════════════════════


class TestKeyLevelsMAs:
    def test_ma_below_price_is_support(self) -> None:
        ind = {"ma20D": 95.0, "ma40D": 90.0, "ma200D": 80.0}
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        # Todos los MAs están por debajo del price → todos son "s"
        # y > price * 0.999 = 99.9 — los 95, 90, 80 cumplen "<99.9"
        assert len(result["s"]) == 3
        assert all(lv["t"] == "s" for lv in result["s"])
        # Orden descendente por proximidad al precio
        assert result["s"][0]["l"] == "MA20D"
        assert result["s"][0]["p"] == 95.0

    def test_ma_above_price_is_resistance(self) -> None:
        ind = {"ma20D": 105.0, "ma40D": 110.0, "ma200D": 120.0}
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        assert len(result["r"]) == 3
        assert all(lv["t"] == "r" for lv in result["r"])
        # Orden ascendente — más cercano primero
        assert result["r"][0]["p"] == 105.0


class TestKeyLevelsBB:
    def test_bb_1h_three_levels_with_unicode_labels(self) -> None:
        ind = {
            "bbH": {"u": 110.0, "m": 100.0, "l": 90.0},
        }
        # price=100 → bbm está exactamente en price → no entra a r ni s
        # (filtros >price*1.001 y <price*0.999)
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        labels_r = [lv["l"] for lv in result["r"]]
        labels_s = [lv["l"] for lv in result["s"]]
        assert "BB↑1H" in labels_r
        assert "BB↓1H" in labels_s

    def test_bb_d_only_upper_lower_no_middle(self) -> None:
        ind = {"bbD": {"u": 115.0, "l": 85.0}}
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        labels = [lv["l"] for lv in result["r"]] + [lv["l"] for lv in result["s"]]
        assert "BB↑D" in labels
        assert "BB↓D" in labels
        # No hay BBmD
        assert all("m" not in lv for lv in labels if lv.startswith("BB"))


class TestKeyLevelsPivots:
    def test_daily_pivots_added_with_label_format(self) -> None:
        pivots_d = {
            "r": [{"lv": 110.0, "tx": 3}],
            "s": [{"lv": 90.0, "tx": 2}],
        }
        result = key_levels({}, pivots_d, {"r": [], "s": []}, price=100.0)
        assert any(lv["l"] == "PivD(3x)" for lv in result["r"])
        assert any(lv["l"] == "PivD(2x)" for lv in result["s"])

    def test_pivots_1h_label_format(self) -> None:
        pivots_h = {"r": [{"lv": 105.0, "tx": 5}], "s": []}
        result = key_levels({}, {"r": [], "s": []}, pivots_h, price=100.0)
        assert any(lv["l"] == "Piv1H(5x)" for lv in result["r"])


class TestKeyLevelsDedup:
    def test_pivot_close_to_existing_merges_label(self) -> None:
        # MA20D=110 y PivD a 110.1 (diff 0.09%, < 0.2% threshold)
        # → fusiona porque es Piv: label se concatena con " +"
        ind = {"ma20D": 110.0}
        pivots_d = {"r": [{"lv": 110.1, "tx": 2}], "s": []}
        result = key_levels(ind, pivots_d, {"r": [], "s": []}, price=100.0)
        # Debe haber UN solo nivel en r con label fusionado
        assert len(result["r"]) == 1
        assert "MA20D" in result["r"][0]["l"]
        assert "+PivD(2x)" in result["r"][0]["l"]

    def test_non_pivot_close_to_existing_discarded(self) -> None:
        # BB↑1H a 110.0 y MA20D a 110.05 (diff < 0.2%)
        # MA no es Piv → se descarta el segundo
        ind = {"ma20D": 110.05, "bbH": {"u": 110.0, "m": 100.0, "l": 90.0}}
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        # Sólo aparece el primero (BB↑1H, viene del orden por price)
        # No se fusiona MA20D porque su label no contiene "Piv"
        labels = [lv["l"] for lv in result["r"]]
        assert "BB↑1H" in labels
        # MA20D NO debe estar (descartado)
        assert "MA20D" not in labels


class TestKeyLevelsFilters:
    def test_too_close_to_price_excluded(self) -> None:
        # MA20D=100.05 está a 0.05% del price=100 → no entra
        # (filtro >price*1.001 = >100.1)
        ind = {"ma20D": 100.05}
        result = key_levels(
            ind, {"r": [], "s": []}, {"r": [], "s": []}, price=100.0,
        )
        # 100.05 < 100.1 (no resistencia) y 100.05 > 99.9 (no soporte)
        assert result["r"] == []
        assert result["s"] == []

    def test_top_4_limit_per_side(self) -> None:
        # 6 resistencias → debería devolver solo 4
        ind = {}
        pivots_d = {
            "r": [
                {"lv": 105.0, "tx": 1},
                {"lv": 110.0, "tx": 1},
                {"lv": 115.0, "tx": 1},
                {"lv": 120.0, "tx": 1},
                {"lv": 125.0, "tx": 1},
                {"lv": 130.0, "tx": 1},
            ],
            "s": [],
        }
        result = key_levels(ind, pivots_d, {"r": [], "s": []}, price=100.0)
        assert len(result["r"]) == 4
        # Los 4 más cercanos al precio
        assert result["r"][0]["p"] == 105.0
        assert result["r"][3]["p"] == 120.0
