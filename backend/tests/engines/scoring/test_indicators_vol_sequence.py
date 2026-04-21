"""Tests de vol_sequence (Sub-fase 5.2b).

Port literal de Observatory `indicators.py:vol_sequence()` líneas 211-235.
Casuísticas clave:

- **Excluye última vela** (incompleta) — analiza `candles[-(n+1):-1]`
- **Tolerancia 5%:** zona donde una misma vela cuenta para growing
  AND declining (es por diseño Observatory)
- **Threshold 75%:** `ceil((n-1) * 0.75)` cumplimientos requeridos
- **Mutex con prioridad growing:** `if growing` evalúa primero
- **Count signo:** positivo growing, negativo declining

Para `n=4` (default): mínimo 6 velas, 3 comparaciones, threshold=3
(las 3 deben cumplir).
"""

from __future__ import annotations

from engines.scoring.indicators import vol_sequence


def _candle(v: float) -> dict:
    """Helper minimal: solo `v` importa para vol_sequence."""
    return {"o": 100.0, "h": 100.0, "l": 100.0, "c": 100.0, "v": v, "dt": ""}


def _vols(values: list[float]) -> list[dict]:
    return [_candle(v) for v in values]


# ═══════════════════════════════════════════════════════════════════════════
# Insufficient data
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceInsufficient:
    def test_empty_returns_neutral(self) -> None:
        assert vol_sequence([]) == {"growing": False, "declining": False, "count": 0}

    def test_below_threshold_n_plus_2(self) -> None:
        # n=4 → necesita >=6 velas
        result = vol_sequence(_vols([10, 100, 200, 300, 400]))  # 5 velas
        assert result == {"growing": False, "declining": False, "count": 0}

    def test_exactly_n_plus_1_still_insufficient(self) -> None:
        # n=4 → necesita 6, no 5. El strict `< n + 2` ⇒ len 5 falla.
        result = vol_sequence(_vols([1, 2, 3, 4, 5]))
        assert result["growing"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Growing claro
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceGrowing:
    def test_pure_growing_three_comparisons(self) -> None:
        # 6 velas, completed = [100, 200, 300, 400] (excluye índice 5)
        # comparaciones: 200>100*0.95, 300>200*0.95, 400>300*0.95 → g=3
        # declining: 200<100*1.05? No. 300<200*1.05? No. 400<300*1.05? No. d=0
        result = vol_sequence(_vols([10, 100, 200, 300, 400, 999]))
        assert result == {"growing": True, "declining": False, "count": 3}

    def test_growing_with_small_dip_in_tolerance(self) -> None:
        # completed = [100, 110, 105, 130]
        # i=1: 110>95 ✓ g=1; 110<105 No d=0
        # i=2: 105>110*0.95=104.5 ✓ g=2; 105<115.5 ✓ d=1 (zona tolerancia)
        # i=3: 130>105*0.95=99.75 ✓ g=3; 130<110.25 No d=1
        # g=3>=3 → growing wins (mutex con prioridad)
        result = vol_sequence(_vols([10, 100, 110, 105, 130, 999]))
        assert result == {"growing": True, "declining": False, "count": 3}


# ═══════════════════════════════════════════════════════════════════════════
# Declining claro
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceDeclining:
    def test_pure_declining_three_comparisons(self) -> None:
        # completed = [400, 300, 200, 100]
        # i=1: 300>380? No g=0; 300<420 ✓ d=1
        # i=2: 200>285? No; 200<315 ✓ d=2
        # i=3: 100>190? No; 100<210 ✓ d=3
        # declining=True, count=-3
        result = vol_sequence(_vols([999, 400, 300, 200, 100, 10]))
        assert result == {"growing": False, "declining": True, "count": -3}

    def test_declining_with_small_uptick_in_tolerance(self) -> None:
        # completed = [400, 380, 395, 350]
        # i=1: 380>400*0.95=380? Estricto No g=0; 380<420 ✓ d=1
        # i=2: 395>380*0.95=361 ✓ g=1; 395<399 ✓ d=2 (zona tolerancia)
        # i=3: 350>395*0.95=375.25? No g=1; 350<414.75 ✓ d=3
        # g=1<3, d=3>=3 → declining wins
        result = vol_sequence(_vols([999, 400, 380, 395, 350, 10]))
        assert result == {"growing": False, "declining": True, "count": -3}


# ═══════════════════════════════════════════════════════════════════════════
# Mutex / prioridad growing
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceMutex:
    def test_flat_volumes_both_meet_threshold_growing_wins(self) -> None:
        # completed = [100, 100, 100, 100] — todas en zona tolerancia
        # i=1: 100>95 ✓ g=1; 100<105 ✓ d=1
        # i=2: 100>95 ✓ g=2; 100<105 ✓ d=2
        # i=3: 100>95 ✓ g=3; 100<105 ✓ d=3
        # Ambos cumplen, pero `if growing` evalúa primero
        result = vol_sequence(_vols([10, 100, 100, 100, 100, 999]))
        assert result == {"growing": True, "declining": False, "count": 3}


# ═══════════════════════════════════════════════════════════════════════════
# Ninguno cumple threshold
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceNeither:
    def test_chaotic_fails_both_thresholds(self) -> None:
        # completed = [100, 200, 50, 80]
        # i=1: 200>95 ✓ g=1; 200<105? No d=0
        # i=2: 50>190? No; 50<210 ✓ d=1
        # i=3: 80>47.5 ✓ g=2; 80<52.5? No d=1
        # g=2<3, d=1<3 → neither
        result = vol_sequence(_vols([10, 100, 200, 50, 80, 999]))
        assert result == {"growing": False, "declining": False, "count": 0}


# ═══════════════════════════════════════════════════════════════════════════
# Custom n
# ═══════════════════════════════════════════════════════════════════════════


class TestVolSequenceCustomN:
    def test_n_3_threshold_2(self) -> None:
        # n=3 → len>=5, completed=candles[-4:-1] (3 velas)
        # threshold = ceil((3-1)*0.75) = ceil(1.5) = 2
        # completed = [100, 200, 300]
        # i=1: 200>95 ✓ g=1; 200<105 No d=0
        # i=2: 300>190 ✓ g=2; 300<210 No d=0
        # g=2>=2 → growing=True, count=2
        result = vol_sequence(_vols([10, 100, 200, 300, 999]), n=3)
        assert result == {"growing": True, "declining": False, "count": 2}

    def test_n_3_insufficient_data(self) -> None:
        # n=3 → necesita >=5
        result = vol_sequence(_vols([1, 2, 3, 4]), n=3)
        assert result["growing"] is False
        assert result["count"] == 0
