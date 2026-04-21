"""Tests del confirm SqExp (Fase 5.1) — Squeeze → Expansión.

Observatory condición: `bbSqH.isSqueeze AND bbSqH.isExpanding`. Ambos
deben ser True simultáneamente. Squeeze sin expansión NO dispara este
confirm (Observatory emite un pattern aparte con cat="SQUEEZE", que
no está portado acá porque no participa del score).
"""

from __future__ import annotations

from engines.scoring.confirms import detect_squeeze_expansion_confirm


def _bb_sq(is_squeeze: bool, is_expanding: bool, percentile: int = 10) -> dict:
    return {
        "current": 1.5,
        "min20": 1.0,
        "percentile": percentile,
        "isSqueeze": is_squeeze,
        "isExpanding": is_expanding,
    }


class TestSqueezeExpansionNone:
    def test_none_returns_empty(self) -> None:
        assert detect_squeeze_expansion_confirm(None) == []


class TestSqueezeExpansionFires:
    def test_both_true_fires(self) -> None:
        result = detect_squeeze_expansion_confirm(_bb_sq(True, True))
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Squeeze → Expansión (ruptura)"
        assert c["sg"] == "CONFIRM"
        assert c["tf"] == "1H"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 0.0
        assert c["age"] == 0


class TestSqueezeExpansionDoesNotFire:
    def test_squeeze_true_expanding_false(self) -> None:
        assert detect_squeeze_expansion_confirm(_bb_sq(True, False)) == []

    def test_squeeze_false_expanding_true(self) -> None:
        # Expansión sin squeeze: no es una ruptura de compresión.
        assert detect_squeeze_expansion_confirm(_bb_sq(False, True)) == []

    def test_both_false(self) -> None:
        assert detect_squeeze_expansion_confirm(_bb_sq(False, False)) == []


class TestSqueezeExpansionMissingKeys:
    def test_missing_is_squeeze(self) -> None:
        assert detect_squeeze_expansion_confirm({"isExpanding": True}) == []

    def test_missing_is_expanding(self) -> None:
        assert detect_squeeze_expansion_confirm({"isSqueeze": True}) == []
