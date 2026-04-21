"""Función pública `analyze()` del Scoring Engine v5.2.0.

Implementa el contrato definido en `docs/specs/SCORING_ENGINE_SPEC.md`:
stateless, pura, determinística, nunca lanza excepciones, fixture
read-only. El pipeline completo (alignment → trigger → conflict → ORB →
score+band) se construye en fases sucesivas sobre este esqueleto.

**Estado:**

    ✅ Fase 1 · esqueleto + contrato + errors (ENG-001/010/099).
    ✅ Fase 2 · indicadores (SMA/EMA/BB/ATR/volumen) en `indicators/`.
    ✅ Fase 3 · alignment gate (trend 15m/1h/daily + compute_alignment).
    ✅ Fase 4 · triggers (16) + risks (4) + trigger gate + conflict gate.
    ⬜ Fase 5 · 10 confirms con pesos de la fixture + score + band.
"""

from __future__ import annotations

from typing import Any

from engines.scoring.alignment import (
    AlignmentDir,
    alignment_gate,
    trend_strict,
    trend_with_fallback,
)
from engines.scoring.constants import (
    ENG_001,
    ENG_010,
    ENG_099,
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
)
from engines.scoring.errors import build_error_output, build_neutral_output
from engines.scoring.indicators import bollinger_bands, sma, volume_ratio_at
from engines.scoring.risks import detect_bb_fakeouts_15m, detect_volume_risks_15m
from engines.scoring.triggers import (
    detect_candle_15m_triggers,
    detect_double_patterns_15m,
    detect_engulfing_1h,
    detect_ma_cross_1h,
    detect_orb_triggers_15m,
)
from modules.fixtures import Fixture, FixtureError, parse_fixture

_BB_WINDOW: int = 20
_BB_K: float = 2.0
_VOLUME_RATIO_WINDOW: int = 20


def analyze(
    ticker: str,
    candles_daily: list[dict],
    candles_1h: list[dict],
    candles_15m: list[dict],
    fixture: dict,
    spy_daily: list[dict] | None = None,
    sim_datetime: str | None = None,
    sim_date: str | None = None,
    bench_daily: list[dict] | None = None,
) -> dict[str, Any]:
    """Ejecuta el scoring sobre las velas de un ticker.

    **Invariantes garantizadas** (spec §3):
        I1 · Sin look-ahead (trust-based; caller hace el slicing).
        I2 · Determinístico: mismos inputs → mismo output.
        I3 · Nunca lanza excepciones. Errores operativos → `error=True`.
        I4 · Fixture read-only (Pydantic frozen + defensive copy interno).
        I5 · Structure gate siempre primero (alignment → trigger →
              conflict → ORB → score+band), ver fases siguientes.

    Args:
        ticker: símbolo para trazabilidad (no afecta la lógica).
        candles_daily: lista de velas daily ordenadas antigua→reciente.
        candles_1h: velas 1H.
        candles_15m: velas 15M.
        fixture: dict con el schema de `FIXTURE_SPEC.md`.
        spy_daily: velas daily de SPY. Requerido si fixture usa DivSPY.
        sim_datetime: timestamp simulado "YYYY-MM-DD HH:MM:SS" ET. Sólo
            lo usan Observatory y Validator. En live siempre es None.
        sim_date: fecha simulada para slicing sin look-ahead.
        bench_daily: velas del benchmark. Requerido si FzaRel tiene
            peso > 0 y `requires_bench_daily=True`.

    Returns:
        Dict con la forma completa del spec §2.3. Nunca se omite ningún
        campo — si no aplica, se setea a `None`, `0.0`, `""` o lista
        vacía según el tipo.
    """
    try:
        # ── Paso 1: Validar fixture (ENG-010)
        try:
            parsed = parse_fixture(fixture)
        except FixtureError as e:
            return build_error_output(
                ticker=ticker,
                error_code=ENG_010,
                error_detail=f"fixture validation failed: {e.code}: {e.detail}",
            )

        fixture_id = parsed.metadata.fixture_id
        fixture_version = parsed.metadata.fixture_version

        # ── Paso 2: Validar cuenta mínima de velas (ENG-001)
        shortage = _candle_shortage(candles_daily, candles_1h, candles_15m)
        if shortage:
            return build_error_output(
                ticker=ticker,
                error_code=ENG_001,
                error_detail=shortage,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
            )

        # ── Paso 3: Validar prerequisitos según la fixture (ENG-001)
        missing = _missing_required_inputs(parsed, spy_daily, bench_daily)
        if missing:
            return build_error_output(
                ticker=ticker,
                error_code=ENG_001,
                error_detail=missing,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
            )

        # ── Paso 4: Alignment gate (spec §3 I5, primer gate del pipeline)
        #
        # Computamos trends con la lógica Observatory Option B:
        #   - 15M y 1H → trend_with_fallback (strict + slope fallback)
        #   - Daily   → trend_strict (sin fallback, spec + Observatory)
        #
        # Para `has_catalyst` (override): el criterio de catalizador
        # (cambio diario > 1.5*ATR% o DivSPY) se determina fuera de
        # este motor. En Fase 4d+ el wiring pasará el valor real; por
        # ahora asumimos False para comportamiento strict del gate.
        closes_15m = [c["c"] for c in candles_15m]
        closes_1h = [c["c"] for c in candles_1h]
        closes_daily = [c["c"] for c in candles_daily]

        ma20_15m = _safe_last(sma(closes_15m, 20))
        ma40_15m = _safe_last(sma(closes_15m, 40))
        ma20_1h = _safe_last(sma(closes_1h, 20))
        ma40_1h = _safe_last(sma(closes_1h, 40))
        ma20_daily = _safe_last(sma(closes_daily, 20))
        ma40_daily = _safe_last(sma(closes_daily, 40))

        t_15m = trend_with_fallback(candles_15m, ma20_15m, ma40_15m)
        t_1h = trend_with_fallback(candles_1h, ma20_1h, ma40_1h)
        t_daily = trend_strict(candles_daily[-1]["c"], ma20_daily, ma40_daily)

        gate = alignment_gate(t_15m, t_1h, t_daily, has_catalyst=False)

        # `layers` adopta la estructura del Observatory scoring.py para
        # facilitar paridad:
        #   layers.structure = {pass, reason, override}
        #   layers.trends    = {t15m, t1h, tdaily}       (extra informativo)
        #   layers.alignment = {n, dir, effective_dir}   (extra informativo)
        layers: dict[str, Any] = {
            "structure": {
                "pass": gate.passed,
                "reason": gate.reason,
                "override": gate.override,
            },
            "trends": {"t15m": t_15m, "t1h": t_1h, "tdaily": t_daily},
            "alignment": {
                "n": gate.n,
                "dir": gate.dir,
                "effective_dir": gate.effective_dir,
            },
        }

        if not gate.passed:
            return build_neutral_output(
                ticker=ticker,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
                blocked="Alineación insuficiente",
                layers=layers,
            )

        # Dirección efectiva según el alignment gate (CALL o PUT).
        # Por construcción del gate, aquí effective_dir es "bullish" o
        # "bearish" (nunca None ni "mixed"); protegemos con assert.
        assert gate.effective_dir is not None
        effective_dir = _dir_from_alignment(gate.effective_dir)

        # ── Paso 5: Detección de triggers + risks
        #
        # BB 15M y BB 1H se computan una única vez sobre las closes del
        # timeframe respectivo; se pasa el último trío (upper, middle,
        # lower) a los detectores que lo consumen (Doji/Hammer/Shooting
        # en 15M; Fakeouts contra BB 1H). Convención Observatory.
        bb_15m_series = bollinger_bands(closes_15m, _BB_WINDOW, _BB_K)
        bb_1h_series = bollinger_bands(closes_1h, _BB_WINDOW, _BB_K)
        bb_15m = _last_bb_tuple(bb_15m_series)
        bb_1h = _last_bb_tuple(bb_1h_series)

        # volume_ratio de la última vela 15M — gate binario del ORB.
        # Semántica divergente con Observatory (mean sobre ventana fija
        # vs. median intraday). Se ajusta cuando se port vol_ratio real
        # del Observatory.
        vol_ratio = volume_ratio_at(
            candles_15m,
            len(candles_15m) - 1,
            _VOLUME_RATIO_WINDOW,
        )

        # Triggers (5 detectores, cubren los 16 patrones).
        triggers: list[dict] = []
        triggers.extend(detect_candle_15m_triggers(candles_15m, bb_15m))
        triggers.extend(detect_engulfing_1h(candles_1h))
        triggers.extend(detect_double_patterns_15m(candles_15m))
        triggers.extend(detect_ma_cross_1h(candles_1h))
        triggers.extend(
            detect_orb_triggers_15m(
                candles_15m,
                volume_ratio=vol_ratio,
                sim_datetime=sim_datetime,
            )
        )

        # Risks — informacionales (cat="RISK"), NO suman al score.
        # `volume_seq_declining` queda en False hasta portear
        # vol_sequence() del Observatory (tolerancia 5% + threshold 75%).
        risks: list[dict] = []
        risks.extend(
            detect_volume_risks_15m(
                candles_15m,
                volume_ratio=vol_ratio,
                volume_seq_declining=False,
            )
        )
        risks.extend(detect_bb_fakeouts_15m(candles_15m, bb_1h))

        patterns: list[dict] = [*triggers, *risks]

        # ── Paso 6: Trigger gate (spec §3 I5 item 2)
        #
        # Al menos 1 trigger en la dirección efectiva del alignment.
        # Observatory: `triggers_in_direction = [p for p in triggers if sg == direction]`.
        directional_triggers = [t for t in triggers if t["sg"] == effective_dir]
        trigger_sum = round(sum(t["w"] for t in directional_triggers), 2)
        layers["trigger"] = {
            "pass": len(directional_triggers) >= 1,
            "count": len(directional_triggers),
            "sum": trigger_sum,
        }

        # Risks se agregan al layer "risk" con items y sum (informacional).
        risk_sum = round(sum(r["w"] for r in risks), 2)

        if not layers["trigger"]["pass"]:
            layers["risk"] = {
                "sum": risk_sum,
                "blocked": False,
                "items": risks,
                "conflictInfo": None,
            }
            return build_neutral_output(
                ticker=ticker,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
                blocked="Sin trigger de entrada",
                layers=layers,
                ind={},
                patterns=patterns,
                dir_=effective_dir,
            )

        # ── Paso 7: Conflict gate (spec §3 I5 item 3)
        #
        # Si hay triggers en AMBAS direcciones, la diferencia de pesos
        # totales debe ser ≥ 2. Sino se bloquea el scan.
        put_w = round(
            sum(t["w"] for t in triggers if t["sg"] == "PUT"),
            2,
        )
        call_w = round(
            sum(t["w"] for t in triggers if t["sg"] == "CALL"),
            2,
        )
        conflict_diff = round(abs(put_w - call_w), 2)
        conflict_info: dict[str, Any] | None = None
        conflict_blocked = False
        if put_w > 0 and call_w > 0:
            conflict_info = {"put": put_w, "call": call_w, "diff": conflict_diff}
            if conflict_diff < 2:
                conflict_blocked = True

        layers["risk"] = {
            "sum": risk_sum,
            "blocked": conflict_blocked,
            "items": risks,
            "conflictInfo": conflict_info,
        }

        if conflict_blocked:
            return build_neutral_output(
                ticker=ticker,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
                blocked=(f"Conflicto PUT({put_w})/CALL({call_w}) — diferencia {conflict_diff} < 2"),
                layers=layers,
                ind={},
                patterns=patterns,
                dir_=effective_dir,
            )

        # ── Paso 8+: confirmaciones + score + band (Fase 5)
        #
        # Llegamos hasta acá cuando alignment, trigger gate y conflict
        # gate pasan. Los siguientes pasos (confirms con pesos de la
        # fixture, suma final, band assignment) vienen en la Fase 5 del
        # scoring. Por ahora devolvemos NEUTRAL con dirección y trigger
        # info pero sin score final.
        layers["confirm"] = {"sum": 0, "volMult": 1.0, "items": [], "bonus": 0}
        return build_neutral_output(
            ticker=ticker,
            fixture_id=fixture_id,
            fixture_version=fixture_version,
            blocked="Score pendiente — confirms no wireados (Fase 5)",
            layers=layers,
            ind={},
            patterns=patterns,
            dir_=effective_dir,
        )

    except Exception as e:
        # Cualquier excepción inesperada se materializa como ENG-099.
        # Nunca propagamos al caller.
        return build_error_output(
            ticker=ticker,
            error_code=ENG_099,
            error_detail=f"unexpected: {type(e).__name__}: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════
# Validadores internos
# ═══════════════════════════════════════════════════════════════════════════


def _safe_last(series: list[float | None]) -> float | None:
    """Último valor no-`None` de una serie, o `None` si vacía / puros None."""
    if not series:
        return None
    return series[-1]


def _last_bb_tuple(
    bb_series: tuple[list[float | None], list[float | None], list[float | None]],
) -> tuple[float, float, float] | None:
    """Último trío `(upper, middle, lower)` de una serie de Bollinger.

    Devuelve `None` si alguno de los tres es `None` en el último índice
    (warmup incompleto). Tupla de tres `float` en caso contrario.
    """
    lower, middle, upper = bb_series
    lo = lower[-1] if lower else None
    mi = middle[-1] if middle else None
    up = upper[-1] if upper else None
    if lo is None or mi is None or up is None:
        return None
    return (up, mi, lo)


def _dir_from_alignment(alignment_dir: AlignmentDir) -> str:
    """Convierte la dirección del alignment en la convención "CALL"/"PUT".

    Observatory: `"PUT" if alignment["dir"] == "bearish" else "CALL"`.
    Sólo se llama cuando `alignment_dir` es "bullish" o "bearish"
    (nunca "mixed", el gate ya filtró ese caso).
    """
    return "PUT" if alignment_dir == "bearish" else "CALL"


def _candle_shortage(
    daily: list[dict],
    h1: list[dict],
    m15: list[dict],
) -> str | None:
    """Devuelve un detail humano si alguna lista está por debajo del mínimo."""
    shortages: list[str] = []
    if len(daily) < MIN_CANDLES_DAILY:
        shortages.append(f"daily={len(daily)} (min {MIN_CANDLES_DAILY})")
    if len(h1) < MIN_CANDLES_1H:
        shortages.append(f"1h={len(h1)} (min {MIN_CANDLES_1H})")
    if len(m15) < MIN_CANDLES_15M:
        shortages.append(f"15m={len(m15)} (min {MIN_CANDLES_15M})")
    if not shortages:
        return None
    return "candles below minimum: " + ", ".join(shortages)


def _missing_required_inputs(
    fixture: Fixture,
    spy_daily: list[dict] | None,
    bench_daily: list[dict] | None,
) -> str | None:
    """Verifica presencia de spy_daily / bench_daily según la fixture.

    Evita depender de pesos individuales (FzaRel, DivSPY) que el motor
    aún no lee — se confía en los flags declarativos de `ticker_info`.
    """
    missing: list[str] = []
    if fixture.ticker_info.requires_spy_daily and not spy_daily:
        missing.append("spy_daily required by fixture but not provided")
    if fixture.ticker_info.requires_bench_daily and not bench_daily:
        missing.append("bench_daily required by fixture but not provided")
    if not missing:
        return None
    return "; ".join(missing)
