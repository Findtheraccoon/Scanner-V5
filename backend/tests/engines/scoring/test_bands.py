"""Tests de resolve_band (Fase 5.3b).

Casuísticas:
- Cada banda del fixture canonical QQQ matchea su rango
- Intervalos semi-abiertos [min, max): `score < max` estricto
- Banda con `max=None` = `[min, +∞)`
- Score por debajo del mínimo → NEUTRAL + CONF_UNKNOWN
- Boundaries exactos: `score == min` entra, `score == max` no entra
"""

from __future__ import annotations

from engines.scoring.bands import resolve_band
from engines.scoring.constants import CONF_UNKNOWN, SIGNAL_NEUTRAL
from modules.fixtures import parse_fixture


def _fixture_with_bands(bands: list[dict]) -> object:
    """Crea una fixture válida con bandas dadas."""
    fixture_dict = {
        "metadata": {
            "fixture_id": "test",
            "fixture_version": "5.0.0",
            "engine_compat_range": ">=5.0.0,<6.0.0",
            "generated_at": "2026-04-22T00:00:00Z",
            "description": "test",
        },
        "ticker_info": {
            "ticker": "TEST",
            "benchmark": None,
            "requires_spy_daily": False,
            "requires_bench_daily": False,
        },
        "detection_thresholds": {
            "fzarel_min_divergence_pct": 0.5,
            "divspy_asset_threshold_pct": 0.5,
            "divspy_spy_threshold_pct": 0.3,
            "volhigh_min_ratio": 1.2,
        },
        "confirm_weights": {
            "BBinf_1H": 3, "BBinf_D": 1, "BBsup_1H": 1, "BBsup_D": 1,
            "DivSPY": 1, "FzaRel": 4, "Gap": 1, "SqExp": 0,
            "VolHigh": 2, "VolSeq": 0,
        },
        "score_bands": bands,
    }
    return parse_fixture(fixture_dict)


def _canonical_qqq_bands() -> list[dict]:
    return [
        {"label": "S+", "max": None, "min": 16.0, "signal": "SETUP"},
        {"label": "S", "max": 16.0, "min": 14.0, "signal": "SETUP"},
        {"label": "A+", "max": 14.0, "min": 10.0, "signal": "SETUP"},
        {"label": "A", "max": 10.0, "min": 7.0, "signal": "SETUP"},
        {"label": "B", "max": 7.0, "min": 4.0, "signal": "REVISAR"},
        {"label": "REVISAR", "max": 4.0, "min": 2.0, "signal": "REVISAR"},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# Cada banda
# ═══════════════════════════════════════════════════════════════════════════


class TestCanonicalBands:
    def setup_method(self) -> None:
        self.fixture = _fixture_with_bands(_canonical_qqq_bands())

    def test_score_below_minimum_is_neutral(self) -> None:
        conf, signal = resolve_band(1.9, self.fixture)
        assert conf == CONF_UNKNOWN
        assert signal == SIGNAL_NEUTRAL

    def test_score_zero_is_neutral(self) -> None:
        conf, signal = resolve_band(0.0, self.fixture)
        assert conf == CONF_UNKNOWN
        assert signal == SIGNAL_NEUTRAL

    def test_revisar_band_lower_boundary(self) -> None:
        # min=2 inclusive
        conf, signal = resolve_band(2.0, self.fixture)
        assert conf == "REVISAR"
        assert signal == "REVISAR"

    def test_revisar_band_middle(self) -> None:
        conf, _ = resolve_band(3.5, self.fixture)
        assert conf == "REVISAR"

    def test_revisar_upper_boundary_excluded(self) -> None:
        # max=4 exclusive: score=4 debe ir a B, no a REVISAR
        conf, _ = resolve_band(4.0, self.fixture)
        assert conf == "B"

    def test_b_band(self) -> None:
        conf, signal = resolve_band(5.5, self.fixture)
        assert conf == "B"
        assert signal == "REVISAR"

    def test_a_band_lower_boundary(self) -> None:
        # min=7 inclusive
        conf, signal = resolve_band(7.0, self.fixture)
        assert conf == "A"
        assert signal == "SETUP"

    def test_a_band_middle(self) -> None:
        conf, signal = resolve_band(8.5, self.fixture)
        assert conf == "A"
        assert signal == "SETUP"

    def test_a_plus_band(self) -> None:
        conf, signal = resolve_band(12.0, self.fixture)
        assert conf == "A+"
        assert signal == "SETUP"

    def test_s_band(self) -> None:
        conf, signal = resolve_band(15.0, self.fixture)
        assert conf == "S"
        assert signal == "SETUP"

    def test_s_plus_band(self) -> None:
        conf, signal = resolve_band(16.0, self.fixture)
        assert conf == "S+"
        assert signal == "SETUP"

    def test_s_plus_band_high_score(self) -> None:
        # max=None → sin tope
        conf, signal = resolve_band(100.0, self.fixture)
        assert conf == "S+"
        assert signal == "SETUP"


# ═══════════════════════════════════════════════════════════════════════════
# Edge cases — dentro de los invariantes del loader (top.max=null, contiguidad)
# ═══════════════════════════════════════════════════════════════════════════


class TestBandsEdgeCases:
    def test_single_band_covers_all(self) -> None:
        bands = [{"label": "OK", "max": None, "min": 0.0, "signal": "SETUP"}]
        fixture = _fixture_with_bands(bands)
        conf, signal = resolve_band(0.0, fixture)
        assert conf == "OK"
        assert signal == "SETUP"

    def test_single_band_below_min_is_neutral(self) -> None:
        bands = [{"label": "OK", "max": None, "min": 5.0, "signal": "SETUP"}]
        fixture = _fixture_with_bands(bands)
        conf, signal = resolve_band(4.9, fixture)
        assert conf == CONF_UNKNOWN
        assert signal == SIGNAL_NEUTRAL
