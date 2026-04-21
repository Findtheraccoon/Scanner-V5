"""Tests del confirm Gap (Fase 5.1) — Gap alcista/bajista.

Observatory condición: `gap["significant"]` debe ser True. Si falso o
si `gap is None`, no dispara. Dirección: `CALL` para bullish, `PUT`
para bearish. El formato del pct aplica `"+"` manualmente cuando es
positivo (el `-` para negativos ya viene dentro del número).
"""

from __future__ import annotations

from engines.scoring.confirms import detect_gap_confirm


class TestGapNone:
    def test_none_returns_empty(self) -> None:
        assert detect_gap_confirm(None) == []

    def test_not_significant_returns_empty(self) -> None:
        gap_info = {"pct": 0.2, "significant": False, "dir": "bullish"}
        assert detect_gap_confirm(gap_info) == []


class TestGapBullish:
    def test_bullish_positive_fires_call_with_plus(self) -> None:
        gap_info = {"pct": 1.25, "significant": True, "dir": "bullish"}
        result = detect_gap_confirm(gap_info)
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Gap alcista +1.25%"
        assert c["sg"] == "CALL"
        assert c["tf"] == "D"
        assert c["cat"] == "CONFIRM"
        assert c["w"] == 1.0

    def test_bullish_integer_pct(self) -> None:
        # Un gap alcista exacto de 2% → "+2%" sin decimales trailing
        # (Python f-string de int 2 da "2"; pero gap pct viene de
        # round(x, 2) → float). Verificamos que no se agrega ".0".
        gap_info = {"pct": 2.0, "significant": True, "dir": "bullish"}
        result = detect_gap_confirm(gap_info)
        assert result[0]["d"] == "Gap alcista +2.0%"


class TestGapBearish:
    def test_bearish_negative_fires_put_without_extra_sign(self) -> None:
        gap_info = {"pct": -1.5, "significant": True, "dir": "bearish"}
        result = detect_gap_confirm(gap_info)
        assert len(result) == 1
        c = result[0]
        assert c["d"] == "Gap bajista -1.5%"
        assert c["sg"] == "PUT"
        assert c["tf"] == "D"
        assert c["w"] == 1.0

    def test_bearish_two_decimals(self) -> None:
        gap_info = {"pct": -0.75, "significant": True, "dir": "bearish"}
        result = detect_gap_confirm(gap_info)
        assert result[0]["d"] == "Gap bajista -0.75%"


class TestGapEdgeCases:
    def test_zero_pct_bullish_no_plus_sign(self) -> None:
        # pct == 0 no debería ocurrir con significant=True, pero
        # la rama bullish con `pct > 0 else ''` cubre el empate.
        gap_info = {"pct": 0.0, "significant": True, "dir": "bullish"}
        result = detect_gap_confirm(gap_info)
        assert result[0]["d"] == "Gap alcista 0.0%"
        assert result[0]["sg"] == "CALL"
