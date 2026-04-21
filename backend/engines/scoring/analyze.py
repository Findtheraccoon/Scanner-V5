"""Función pública `analyze()` del Scoring Engine v5.2.0.

Implementa el contrato definido en `docs/specs/SCORING_ENGINE_SPEC.md`:
stateless, pura, determinística, nunca lanza excepciones, fixture
read-only. El pipeline completo (alignment → trigger → conflict → ORB →
score+band) se construye en fases sucesivas sobre este esqueleto.

**Fase actual (1 — esqueleto + contrato):**

    - Valida fixture via `modules.fixtures.parse_fixture` → ENG-010 si
      falla el schema.
    - Valida cuenta mínima de velas (40/25/25 spec §2.2) → ENG-001.
    - Valida que `requires_spy_daily` / `requires_bench_daily` del
      fixture estén honrados con los inputs correspondientes → ENG-001.
    - Envuelve todo en try/except para garantizar I3 (nunca propaga
      excepciones) → ENG-099 como catch-all.
    - Devuelve NEUTRAL con `blocked="no_triggers_detected"` en el happy
      path, ya que el detector de triggers aún no está implementado.

**Fases siguientes (TODO en commits sucesivos):**

    Fase 2 · indicadores (SMA, EMA, BB, ATR, volumen)
    Fase 3 · alignment + trend gate
    Fase 4 · 14 triggers (patterns.py)
    Fase 5 · 10 confirms (confirms.py)
    Fase 6 · gates (conflict/ORB) + score + band assignment
"""

from __future__ import annotations

from typing import Any

from engines.scoring.constants import (
    ENG_001,
    ENG_010,
    ENG_099,
    MIN_CANDLES_1H,
    MIN_CANDLES_15M,
    MIN_CANDLES_DAILY,
)
from engines.scoring.errors import build_error_output, build_neutral_output
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

        # ── Paso 4+: fases futuras (indicadores, triggers, confirms, gates)
        # Por ahora el motor corre "limpio" pero no detecta nada.
        return build_neutral_output(
            ticker=ticker,
            fixture_id=fixture_id,
            fixture_version=fixture_version,
            blocked="no_triggers_detected",
            layers={"gate": "trigger", "detail": "no trigger detectors wired yet"},
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
