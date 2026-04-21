"""Función pública `analyze()` del Scoring Engine v5.2.0.

Implementa el contrato definido en `docs/specs/SCORING_ENGINE_SPEC.md`:
stateless, pura, determinística, nunca lanza excepciones, fixture
read-only. El pipeline completo (alignment → trigger → conflict → ORB →
score+band) se construye en fases sucesivas sobre este esqueleto.

**Estado:**

    ✅ Fase 1 · esqueleto + contrato + errors (ENG-001/010/099).
    ✅ Fase 2 · indicadores (SMA/EMA/BB/ATR/volumen) en `indicators/`.
    ✅ Fase 3 · alignment gate (trend 15m/1h/daily + compute_alignment).
    ⬜ Fase 4 · 14 triggers hardcoded (port v4.2.1).
    ⬜ Fase 5 · 10 confirms con pesos de la fixture.
    ⬜ Fase 6 · gates conflict + ORB + score + band assignment.
"""

from __future__ import annotations

from typing import Any

from engines.scoring.alignment import (
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
from engines.scoring.indicators import sma
from modules.fixtures import Fixture, FixtureError, parse_fixture


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

        # ── Paso 5+: fases futuras (triggers, confirms, conflict/ORB, score)
        # Por ahora alineamos pero sin detectores de trigger conectados.
        layers["trigger"] = {"pass": False, "count": 0, "sum": 0}
        return build_neutral_output(
            ticker=ticker,
            fixture_id=fixture_id,
            fixture_version=fixture_version,
            blocked="Sin trigger de entrada",
            layers=layers,
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
