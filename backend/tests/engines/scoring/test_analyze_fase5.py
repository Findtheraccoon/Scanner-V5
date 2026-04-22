"""Tests de integración de `analyze()` para Fase 5 (wire completo).

Enfoque: validar el pipeline **desde el trigger gate hacia adelante**
(confirms → dedup → score → banda → output) sin depender de la
lógica de detección de triggers. Los detectores se monkeypatchean
con versiones sintéticas controladas.

Los tests de los detectores individuales ya viven en
`test_confirms_*.py`, `test_triggers_*.py`, etc. Acá validamos la
composición.
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from engines.scoring import (
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
    analyze,
)

# El init de `engines.scoring` sobrescribe el atributo `analyze` del
# package con la función — para monkeypatchear el módulo hay que tomarlo
# desde `sys.modules` directamente.
_ANALYZE_MODULE = sys.modules["engines.scoring.analyze"]

# ═══════════════════════════════════════════════════════════════════════════
# Helpers — fixture y series sintéticas
# ═══════════════════════════════════════════════════════════════════════════


def _valid_fixture(
    *,
    benchmark: str | None = "SPY",
    requires_bench_daily: bool = True,
    confirm_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    return {
        "metadata": {
            "fixture_id": "qqq_test_v5",
            "fixture_version": "5.2.0",
            "engine_compat_range": ">=5.2.0,<6.0.0",
            "canonical_ref": None,
            "generated_at": "2025-03-10T00:00:00Z",
            "description": "Fixture sintética para tests de Fase 5.",
        },
        "ticker_info": {
            "ticker": "QQQ",
            "benchmark": benchmark,
            "requires_spy_daily": True,
            "requires_bench_daily": requires_bench_daily,
        },
        "confirm_weights": confirm_weights or {
            "FzaRel": 4.0, "BBinf_1H": 3.0, "BBsup_1H": 1.0,
            "BBinf_D": 1.0, "BBsup_D": 1.0, "VolHigh": 2.0,
            "VolSeq": 0.0, "Gap": 1.0, "SqExp": 0.0, "DivSPY": 1.0,
        },
        "detection_thresholds": {
            "fzarel_min_divergence_pct": 0.5,
            "divspy_asset_threshold_pct": 0.5,
            "divspy_spy_threshold_pct": 0.3,
            "volhigh_min_ratio": 1.2,
        },
        "score_bands": [
            {"min": 16.0, "max": None, "label": "S+", "signal": "SETUP"},
            {"min": 14.0, "max": 16.0, "label": "S", "signal": "SETUP"},
            {"min": 10.0, "max": 14.0, "label": "A+", "signal": "SETUP"},
            {"min": 7.0, "max": 10.0, "label": "A", "signal": "SETUP"},
            {"min": 4.0, "max": 7.0, "label": "B", "signal": "REVISAR"},
            {"min": 2.0, "max": 4.0, "label": "REVISAR", "signal": "REVISAR"},
        ],
    }


def _monotonic_candles(n: int, start: float = 500.0, step: float = 0.1) -> list[dict]:
    """Serie monotónicamente creciente — alignment bullish 3/3."""
    return [
        {
            "dt": f"2025-01-{(i % 28) + 1:02d} 10:{(i * 15) % 60:02d}:00",
            "o": start + i * step,
            "h": start + i * step + 1.0,
            "l": start + i * step - 1.0,
            "c": start + i * step + 0.5,
            "v": 1_000_000 + i,
        }
        for i in range(n)
    ]


def _valid_inputs(**overrides: Any) -> dict[str, Any]:
    base = {
        "ticker": "QQQ",
        "candles_daily": _monotonic_candles(MIN_CANDLES_DAILY, start=500.0),
        "candles_1h": _monotonic_candles(MIN_CANDLES_1H, start=500.0),
        "candles_15m": _monotonic_candles(MIN_CANDLES_15M, start=500.0),
        "fixture": _valid_fixture(),
        "spy_daily": _monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        "bench_daily": _monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
    }
    base.update(overrides)
    return base


def _call_trigger(weight: float = 4.0) -> dict:
    return {
        "tf": "1H", "d": "MA20 cross up (synth)",
        "sg": "CALL", "w": weight, "cat": "TRIGGER", "age": 0,
    }


def _put_trigger(weight: float = 4.0) -> dict:
    return {
        "tf": "1H", "d": "MA20 cross down (synth)",
        "sg": "PUT", "w": weight, "cat": "TRIGGER", "age": 0,
    }


def _confirm_bb_inf_1h(price: float = 410.0, weight: float = 3.0) -> dict:
    return {
        "tf": "1H", "d": f"BB inf 1H (${price})",
        "sg": "CALL", "w": weight, "cat": "CONFIRM", "age": 0,
    }


def _confirm_bb_sup_1h(price: float = 445.0) -> dict:
    return {
        "tf": "1H", "d": f"BB sup 1H (${price})",
        "sg": "PUT", "w": 1.0, "cat": "CONFIRM", "age": 0,
    }


def _confirm_fzarel(diff: float = 1.5) -> dict:
    sign = "+" if diff > 0 else ""
    return {
        "tf": "D", "d": f"FzaRel {sign}{diff}% vs SPY",
        "sg": "CONFIRM", "w": 4.0, "cat": "CONFIRM", "age": 0,
    }


def _patch_triggers(
    monkeypatch: pytest.MonkeyPatch,
    triggers: list[dict],
) -> None:
    """Reemplaza `detect_ma_cross_1h` para que emita una lista fija."""
    monkeypatch.setattr(
        _ANALYZE_MODULE, "detect_ma_cross_1h", lambda candles: triggers,
    )


def _patch_confirms(
    monkeypatch: pytest.MonkeyPatch,
    bollinger: list[dict] | None = None,
    volume_high: list[dict] | None = None,
    volume_sequence: list[dict] | None = None,
    squeeze: list[dict] | None = None,
    gap: list[dict] | None = None,
    fzarel: list[dict] | None = None,
    divspy: list[dict] | None = None,
) -> None:
    """Reemplaza TODOS los detectores de confirms con listas fijas.
    Los no especificados se silencian con `[]` para que el test sea
    determinista (sino VolSeq real dispara sobre la serie monotónica).
    """
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_bollinger_confirms",
        lambda **kw: bollinger if bollinger is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_volume_high_confirm",
        lambda v: volume_high if volume_high is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_volume_sequence_confirm",
        lambda vs: volume_sequence if volume_sequence is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_squeeze_expansion_confirm",
        lambda bs: squeeze if squeeze is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_gap_confirm",
        lambda gi: gap if gap is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_fzarel_confirm",
        lambda **kw: fzarel if fzarel is not None else [],
    )
    monkeypatch.setattr(
        _ANALYZE_MODULE,
        "detect_divspy_confirm",
        lambda **kw: divspy if divspy is not None else [],
    )


# ═══════════════════════════════════════════════════════════════════════════
# Happy path — SETUP real con trigger + confirms
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeSignalOutput:
    def test_trigger_alone_produces_b_band(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trigger peso=4, confirms vacíos → score=4 → banda B, signal REVISAR."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(monkeypatch)
        out = analyze(**_valid_inputs())
        assert out["error"] is False
        assert out["signal"] == "REVISAR"
        assert out["conf"] == "B"
        assert out["score"] == 4.0
        assert out["dir"] == "CALL"
        assert out["blocked"] is None

    def test_trigger_plus_fzarel_produces_a_band(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trigger peso=4 + FzaRel peso=4 = score=8 → banda A, SETUP."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(monkeypatch, fzarel=[_confirm_fzarel(1.5)])
        out = analyze(**_valid_inputs())
        assert out["signal"] == "SETUP"
        assert out["conf"] == "A"
        assert out["score"] == 8.0

    def test_ind_populated_in_signal_output(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(monkeypatch)
        out = analyze(**_valid_inputs())
        # `ind` debe tener al menos `price` poblado (no vacío)
        assert out["ind"] != {}
        assert "price" in out["ind"]
        assert isinstance(out["ind"]["price"], (int, float))

    def test_layers_confirm_has_sum_and_items(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(monkeypatch, fzarel=[_confirm_fzarel(1.5)])
        out = analyze(**_valid_inputs())
        assert out["layers"]["confirm"]["sum"] == 4.0
        assert len(out["layers"]["confirm"]["items"]) == 1
        assert out["layers"]["confirm"]["items"][0]["category"] == "FzaRel"

    def test_patterns_includes_triggers_and_confirms(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(
            monkeypatch,
            bollinger=[_confirm_bb_inf_1h()],
            fzarel=[_confirm_fzarel()],
        )
        out = analyze(**_valid_inputs())
        cats = [p["cat"] for p in out["patterns"]]
        assert "TRIGGER" in cats
        assert "CONFIRM" in cats


# ═══════════════════════════════════════════════════════════════════════════
# Dedup + filtro de dirección
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeConfirmsDedup:
    def test_duplicate_bb_inf_1h_dedupes_first_wins(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dos BB inf 1H distintos → solo uno suma (el primero)."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(
            monkeypatch,
            bollinger=[
                _confirm_bb_inf_1h(price=410.0),
                _confirm_bb_inf_1h(price=408.0),
            ],
        )
        out = analyze(**_valid_inputs())
        # Solo 1 item de BBinf_1H en layers.confirm.items
        bb_items = [
            it for it in out["layers"]["confirm"]["items"]
            if it["category"] == "BBinf_1H"
        ]
        assert len(bb_items) == 1
        assert bb_items[0]["desc"] == "BB inf 1H ($410.0)"
        # confirm_sum = 3 (BBinf_1H weight), NOT 6
        assert out["layers"]["confirm"]["sum"] == 3.0


class TestAnalyzeDirectionFilter:
    def test_opposite_direction_confirm_not_summed(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trigger CALL + confirm PUT (BB sup) → el PUT no suma."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(
            monkeypatch,
            bollinger=[_confirm_bb_sup_1h(price=445.0)],  # sg=PUT
        )
        out = analyze(**_valid_inputs())
        # confirm_sum queda en 0 porque el BB sup 1H es PUT y la dir
        # efectiva es CALL.
        assert out["layers"]["confirm"]["sum"] == 0.0
        # Score = solo el trigger
        assert out["score"] == 4.0

    def test_neutral_sg_confirm_always_sums(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """sg='CONFIRM' (neutro direccional) suma en cualquier dirección."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=1.0)])
        _patch_confirms(monkeypatch, fzarel=[_confirm_fzarel()])
        out = analyze(**_valid_inputs())
        # FzaRel (sg=CONFIRM) suma aunque la dir sea CALL
        assert out["layers"]["confirm"]["sum"] == 4.0


# ═══════════════════════════════════════════════════════════════════════════
# Score < 2 → NEUTRAL con blocked explicativo
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeBelowMinBand:
    def test_trigger_weight_1_no_confirms_returns_neutral(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Trigger peso=1 + sin confirms → score=1 < 2 (min band) → NEUTRAL."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=1.0)])
        _patch_confirms(monkeypatch)
        out = analyze(**_valid_inputs())
        assert out["signal"] == "NEUTRAL"
        assert out["conf"] == "—"
        assert out["score"] == 0.0  # output neutro pone 0.0
        assert "Score insuficiente" in out["blocked"]
        # Pero la dirección sigue reportada
        assert out["dir"] == "CALL"


# ═══════════════════════════════════════════════════════════════════════════
# DivSPY / FzaRel — edge cases específicos
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeDivSpyGuard:
    def test_ticker_spy_still_runs_pipeline(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Con ticker=SPY el pipeline corre igual; DivSPY no se emite
        pero eso lo valida el test del detector — acá sólo verificamos
        que analyze no explote."""
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        # No patcheamos DivSPY — usa el real. Ticker=SPY → detector
        # devuelve [] por construcción (ver test_confirms_relative_strength).
        fixture = _valid_fixture(benchmark=None, requires_bench_daily=False)
        out = analyze(
            ticker="SPY",
            candles_daily=_monotonic_candles(MIN_CANDLES_DAILY),
            candles_1h=_monotonic_candles(MIN_CANDLES_1H),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M),
            fixture=fixture,
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY),
        )
        assert out["error"] is False
        # Ningún confirm DivSPY debe aparecer
        assert not any(
            it["category"] == "DivSPY"
            for it in out["layers"].get("confirm", {}).get("items", [])
        )


# ═══════════════════════════════════════════════════════════════════════════
# Determinismo — mismos inputs → mismo output
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzeDeterminism:
    def test_same_inputs_produce_same_output(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _patch_triggers(monkeypatch, [_call_trigger(weight=4.0)])
        _patch_confirms(monkeypatch, fzarel=[_confirm_fzarel()])
        out1 = analyze(**_valid_inputs())
        out2 = analyze(**_valid_inputs())
        # Evaluamos claves clave que reflejan el flujo (excluye ind que
        # tiene TypedDict → dict conversión consistente igual).
        assert out1["score"] == out2["score"]
        assert out1["conf"] == out2["conf"]
        assert out1["signal"] == out2["signal"]
        assert out1["layers"]["confirm"]["sum"] == out2["layers"]["confirm"]["sum"]


# ═══════════════════════════════════════════════════════════════════════════
# PUT direction — espejo del caso CALL
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyzePutDirection:
    def test_bearish_series_triggers_put_direction(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Serie monotónicamente decreciente → alignment bearish → dir=PUT."""
        _patch_triggers(monkeypatch, [_put_trigger(weight=4.0)])
        _patch_confirms(monkeypatch)
        # Serie decreciente
        bearish = _monotonic_candles(MIN_CANDLES_DAILY, start=500.0, step=-0.1)
        out = analyze(
            ticker="QQQ",
            candles_daily=bearish,
            candles_1h=_monotonic_candles(MIN_CANDLES_1H, start=500.0, step=-0.1),
            candles_15m=_monotonic_candles(MIN_CANDLES_15M, start=500.0, step=-0.1),
            fixture=_valid_fixture(),
            spy_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
            bench_daily=_monotonic_candles(MIN_CANDLES_DAILY, start=600.0),
        )
        assert out["error"] is False
        assert out["dir"] == "PUT"
        assert out["signal"] == "REVISAR"
        assert out["conf"] == "B"
