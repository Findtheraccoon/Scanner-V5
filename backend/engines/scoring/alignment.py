"""Alignment gate — estructura del scoring (primer gate del pipeline).

Portado del Observatory (`docs/specs/Observatory/Current/scanner/
scoring.py` funciones `trend()`, `trend_slope()` + `scoring.py`
layered_score sección "LAYER 1: STRUCTURE").

**Trend por timeframe** (3 flavors):

    trend_strict(price, ma20, ma40)
        price > ma20 > ma40 → "bullish"
        price < ma20 < ma40 → "bearish"
        resto              → "neutral"
        (si ma20 o ma40 son None → "neutral")

    trend_slope(candles, ma20)
        Fallback que usa la pendiente de MA20 (valor actual vs. 5 velas
        atrás). Se usa cuando MA40 no está disponible (serie corta) o
        como refuerzo del strict cuando éste es neutral pero el precio
        está del mismo lado que ambas MAs.
        Con <25 velas degrada a price vs. ma20 sin slope.

    trend_with_fallback(candles, ma20, ma40)
        Observatory "Option B". Primero strict; si neutral pero precio
        on-side, intenta slope.

Convención de timeframes (según Observatory engine.py):

    15M   → trend_with_fallback (con slope fallback)
    1H    → trend_with_fallback
    Daily → trend_strict (sin fallback)

**Alignment**:

    compute_alignment(t_15m, t_1h, t_daily) -> (n, dir)
        bullish_count >= 3  → (3, "bullish")
        bearish_count >= 3  → (3, "bearish")
        bullish_count >= 2  → (2, "bullish")
        bearish_count >= 2  → (2, "bearish")
        resto               → (max(bc, uc), "mixed")

**Gate del spec §3 I5**:

    alignment_gate(t_15m, t_1h, t_daily, *, has_catalyst)
        Passes si (n >= 2 AND dir != "mixed") OR catalyst override.
        Catalyst override requiere has_catalyst=True AND 15M+1H
        coincidentes y no-neutrales (override_dir = t_15m).

El caller de `alignment_gate` provee `has_catalyst` según su propio
criterio (en Observatory engine.py: ATR-based change threshold OR
DivSPY detectado).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Trend = Literal["bullish", "bearish", "neutral"]
"""Dirección de un timeframe individual."""

AlignmentDir = Literal["bullish", "bearish", "mixed"]
"""Dirección de la alineación combinada de los 3 TFs."""


# ═══════════════════════════════════════════════════════════════════════════
# Trend por timeframe (3 flavors)
# ═══════════════════════════════════════════════════════════════════════════


def trend_strict(price: float, ma20: float | None, ma40: float | None) -> Trend:
    """Strict: price > MA20 > MA40 (bullish) o inverso (bearish), else neutral.

    Observatory `scoring.py:trend()`.

    Args:
        price: close actual.
        ma20: SMA(20) al final de la serie. `None` → neutral.
        ma40: SMA(40) al final de la serie. `None` → neutral.

    Returns:
        "bullish" | "bearish" | "neutral".
    """
    if ma20 is None or ma40 is None:
        return "neutral"
    if price > ma20 and ma20 > ma40:
        return "bullish"
    if price < ma20 and ma20 < ma40:
        return "bearish"
    return "neutral"


def trend_slope(candles: list[dict], ma20: float | None) -> Trend:
    """Fallback basado en la pendiente de MA20.

    Observatory `scoring.py:trend_slope()`.

    Args:
        candles: lista de velas.
        ma20: SMA(20) al final de la serie. `None` → neutral.

    Returns:
        Con ≥ 25 velas:
            price > ma20 > ma20_prev (5 velas atrás) → "bullish"
            price < ma20 < ma20_prev                  → "bearish"
            resto                                      → "neutral"

        Con < 25 velas (degradación):
            price > ma20 → "bullish"
            price < ma20 → "bearish"
            resto        → "neutral"

    Nota: `ma20_prev` se computa como `round(sum(candles[-25:-5]) / 20, 2)`
    — con round a 2 decimales para paridad con Observatory.
    """
    if ma20 is None or not candles:
        return "neutral"
    price = candles[-1]["c"]
    if len(candles) < 25:
        if price > ma20:
            return "bullish"
        if price < ma20:
            return "bearish"
        return "neutral"
    ma20_prev = round(sum(c["c"] for c in candles[-25:-5]) / 20, 2)
    if price > ma20 and ma20 > ma20_prev:
        return "bullish"
    if price < ma20 and ma20 < ma20_prev:
        return "bearish"
    return "neutral"


def trend_with_fallback(
    candles: list[dict],
    ma20: float | None,
    ma40: float | None,
) -> Trend:
    """Observatory "Option B": strict + slope fallback.

    Args:
        candles: lista de velas.
        ma20: SMA(20).
        ma40: SMA(40). Si `None`, se usa `trend_slope` directamente.

    Returns:
        - Si no hay MA40 → `trend_slope(candles, ma20)`.
        - Else → `trend_strict(price, ma20, ma40)`. Si resulta "neutral"
          pero el precio está del mismo lado de ambas MAs, se intenta
          confirmar con slope.
    """
    if ma40 is None:
        return trend_slope(candles, ma20)
    if not candles:
        return "neutral"
    price = candles[-1]["c"]
    strict = trend_strict(price, ma20, ma40)
    if strict != "neutral" or ma20 is None:
        return strict
    # strict es neutral pero el precio puede estar consistentemente sobre
    # o bajo ambas MAs → probamos slope como desempate.
    if price > ma20 and price > ma40 and trend_slope(candles, ma20) == "bullish":
        return "bullish"
    if price < ma20 and price < ma40 and trend_slope(candles, ma20) == "bearish":
        return "bearish"
    return "neutral"


# ═══════════════════════════════════════════════════════════════════════════
# Alignment — combinar 3 trends
# ═══════════════════════════════════════════════════════════════════════════


def compute_alignment(
    trend_15m: Trend,
    trend_1h: Trend,
    trend_daily: Trend,
) -> tuple[int, AlignmentDir]:
    """Combina 3 trends en `(alignment_n, alignment_dir)`.

    Observatory `engine.py:analyze()` sección "Alignment".

    Args:
        trend_15m, trend_1h, trend_daily: tendencias por timeframe.

    Returns:
        Tupla `(n, dir)`:
          - bullish_count >= 3  → (3, "bullish")
          - bearish_count >= 3  → (3, "bearish")
          - bullish_count >= 2  → (2, "bullish")
          - bearish_count >= 2  → (2, "bearish")
          - resto                → (max(bc, uc), "mixed")
    """
    ts = [trend_15m, trend_1h, trend_daily]
    bearish_count = sum(1 for t in ts if t == "bearish")
    bullish_count = sum(1 for t in ts if t == "bullish")
    if bearish_count >= 3:
        return 3, "bearish"
    if bullish_count >= 3:
        return 3, "bullish"
    if bearish_count >= 2:
        return 2, "bearish"
    if bullish_count >= 2:
        return 2, "bullish"
    return max(bearish_count, bullish_count), "mixed"


# ═══════════════════════════════════════════════════════════════════════════
# Alignment gate — con catalyst override
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AlignmentGateResult:
    """Resultado estructurado del alignment gate.

    `passed`         — True si el gate aprueba (strict o via override)
    `n`              — conteo de la dirección dominante en compute_alignment
    `dir`            — dirección de compute_alignment ("bullish"/"bearish"/"mixed")
    `override`       — True si el gate pasó via catalyst override
    `effective_dir`  — "bullish" o "bearish" si passed=True, None si blocked
    `reason`         — descripción humana del resultado
    """

    passed: bool
    n: int
    dir: AlignmentDir
    override: bool
    effective_dir: AlignmentDir | None
    reason: str


def alignment_gate(
    trend_15m: Trend,
    trend_1h: Trend,
    trend_daily: Trend,
    *,
    has_catalyst: bool = False,
) -> AlignmentGateResult:
    """Evalúa el alignment gate del spec §3 I5.

    Flujo:
        1. `compute_alignment` sobre los 3 TFs → (n, dir).
        2. Si `n >= 2 AND dir != "mixed"` → gate passes.
        3. Else, si `has_catalyst AND trend_15m AND trend_1h son iguales y
           no-neutrales` → override pass con `effective_dir = trend_15m`.
        4. Else → blocked.

    Args:
        trend_15m, trend_1h, trend_daily: tendencias por timeframe
            (salidas de `trend_strict`, `trend_slope` o `trend_with_fallback`).
        has_catalyst: `True` si el caller detectó catalizador (por
            ejemplo, cambio diario > `1.5 * ATR%` o DivSPY activo).
            El cálculo de catalizador es responsabilidad del caller.

    Returns:
        `AlignmentGateResult` con todos los campos relevantes.
    """
    n, direction = compute_alignment(trend_15m, trend_1h, trend_daily)

    # Paso 1: gate strict
    if n >= 2 and direction != "mixed":
        return AlignmentGateResult(
            passed=True,
            n=n,
            dir=direction,
            override=False,
            effective_dir=direction,
            reason=f"{n}/3 {direction}",
        )

    # Paso 2: catalyst override (15M+1H coinciden no-neutrales)
    if has_catalyst and trend_15m != "neutral" and trend_15m == trend_1h:
        override_dir: AlignmentDir = trend_15m  # "bullish" o "bearish"
        return AlignmentGateResult(
            passed=True,
            n=n,
            dir=direction,
            override=True,
            effective_dir=override_dir,
            reason=f"OVERRIDE {n}/3 (15M+1H:{trend_15m}, catalizador)",
        )

    # Paso 3: blocked
    return AlignmentGateResult(
        passed=False,
        n=n,
        dir=direction,
        override=False,
        effective_dir=None,
        reason=f"{n}/3 insuficiente",
    )
