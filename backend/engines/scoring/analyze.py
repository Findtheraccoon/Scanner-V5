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
    ✅ Fase 5 · 10 confirms con pesos de la fixture + score + band.
"""

from __future__ import annotations

from typing import Any

from engines.scoring.alignment import (
    AlignmentDir,
    alignment_gate,
    trend_strict,
    trend_with_fallback,
)
from engines.scoring.bands import resolve_band
from engines.scoring.confirms import (
    apply_confirm_weights,
    detect_bollinger_confirms,
    detect_divspy_confirm,
    detect_fzarel_confirm,
    detect_gap_confirm,
    detect_squeeze_expansion_confirm,
    detect_volume_high_confirm,
    detect_volume_sequence_confirm,
)
from engines.scoring.constants import (
    ENG_001,
    ENG_010,
    ENG_099,
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
    SIGNAL_NEUTRAL,
)
from engines.scoring.errors import (
    build_error_output,
    build_neutral_output,
    build_signal_output,
)
from engines.scoring.ind_builder import build_ind_bundle
from engines.scoring.indicators import (
    bollinger_bands,
    sma,
    vol_ratio_intraday,
)
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
        # Port Observatory `vol_ratio()` con today_only=True: mediana de
        # las velas completas del día (no mean sobre ventana fija) →
        # anula el outlier de 9:30 y compara same-day. Con mean sobre
        # 20 velas cross-day, los primeros 15M del día daban valores
        # ínfimos (0.04-0.31) que bloqueaban incorrectamente el ORB.
        vol_ratio = vol_ratio_intraday(candles_15m, sim_date)
        # `volume_ratio_at` mean-over-window se mantiene exportado por
        # si algún consumer externo lo necesita; ya no se usa para el
        # gate del ORB.

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

        # ── Paso 8: Indicator bundle (Fase 5.3a)
        #
        # Construye el dict `ind` con todos los indicadores consumidos
        # por los confirms. Port parcial de Observatory `calc_indicators`
        # acotado a lo que entra al score. Warmup se resuelve al neutro
        # Observatory (None para BB/gap, 1.0 para vol_ratio, 0 para
        # pct_change).
        ind_bundle = build_ind_bundle(
            candles_daily=candles_daily,
            candles_1h=candles_1h,
            candles_15m=candles_15m,
            spy_daily=spy_daily,
            bench_daily=bench_daily,
            sim_date=sim_date,
        )

        # ── Paso 9: Detectar los 10 confirms (Fase 5.1)
        #
        # FzaRel usa benchmark del fixture (default "SPY") y su pct
        # change. Si el fixture declara un benchmark distinto y se pasa
        # `bench_daily`, se usa ese; sino el pct change de SPY.
        bench_ticker = parsed.ticker_info.benchmark or "SPY"
        bench_chg_for_fzarel = (
            ind_bundle["bench_chg"] if bench_daily else ind_bundle["spy_chg"]
        )

        confirms: list[dict] = []
        confirms.extend(
            detect_bollinger_confirms(
                last_close_15m=ind_bundle["price"],
                bb_1h=ind_bundle["bb_1h"],
                bb_daily=ind_bundle["bb_daily"],
            )
        )
        confirms.extend(detect_volume_high_confirm(ind_bundle["vol_m"]))
        confirms.extend(detect_volume_sequence_confirm(ind_bundle["vol_seq_m"]))
        confirms.extend(detect_squeeze_expansion_confirm(ind_bundle["bb_sq_1h"]))
        confirms.extend(detect_gap_confirm(ind_bundle["gap_info"]))
        confirms.extend(
            detect_fzarel_confirm(
                a_chg=ind_bundle["a_chg"],
                bench_chg=bench_chg_for_fzarel,
                bench_ticker=bench_ticker,
                alignment_dir=gate.effective_dir,
            )
        )
        confirms.extend(
            detect_divspy_confirm(
                ticker=ticker,
                a_chg=ind_bundle["a_chg"],
                spy_chg=ind_bundle["spy_chg"],
            )
        )
        patterns = [*triggers, *risks, *confirms]

        # ── Paso 10: Confirm sum con dedup + pesos del fixture (Fase 5.3)
        #
        # Observatory `scoring.py` L307: confirms en la dirección
        # efectiva o con `sg="CONFIRM"` (neutros). Los direccionales
        # opuestos no suman.
        directional_confirms = [
            c for c in confirms
            if c["sg"] == effective_dir or c["sg"] == "CONFIRM"
        ]
        confirm_sum, confirm_items = apply_confirm_weights(
            directional_confirms,
            parsed.confirm_weights,
        )
        layers["confirm"] = {
            "sum": confirm_sum,
            "volMult": 1.0,  # v5 H-02: volumen no multiplica el score
            "items": confirm_items,
            "bonus": 0,  # v5 H-02: bonus no suma al score
        }

        # ── Paso 11: Score final + banda de confianza
        #
        # Fórmula v5: `raw_score = trigger_sum + confirm_sum` (sin
        # volMult, sin time_w, sin bonus, sin risk_sum — H-02).
        # Clamp a >= 0 y redondeo a 1 decimal para paridad.
        raw_score = trigger_sum + confirm_sum
        score = round(max(0.0, raw_score), 1)

        conf, signal = resolve_band(score, parsed)

        # Score por debajo del umbral mínimo de todas las bandas →
        # output neutro con el score calculado pero sin señal.
        if signal == SIGNAL_NEUTRAL:
            return build_neutral_output(
                ticker=ticker,
                fixture_id=fixture_id,
                fixture_version=fixture_version,
                blocked="Score insuficiente — sin banda asignada",
                layers=layers,
                ind=dict(ind_bundle),
                patterns=patterns,
                dir_=effective_dir,
            )

        return build_signal_output(
            ticker=ticker,
            fixture_id=fixture_id,
            fixture_version=fixture_version,
            score=score,
            conf=conf,
            signal=signal,
            dir_=effective_dir,
            layers=layers,
            ind=dict(ind_bundle),
            patterns=patterns,
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
