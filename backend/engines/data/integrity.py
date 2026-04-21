"""Verificación estructural de integridad de velas del Data Engine.

El Data Engine NUNCA pasa velas con integridad no verificada al Scoring
Engine (invariante I1 del motor en `backend/engines/data/README.md`).
Esta verificación es estructural: revisa que la lista esté bien formada,
sin decidir si los datos están "frescos" ni si hay gaps entre sesiones.

Checks realizados:

    - Cuenta mínima por timeframe (Scoring Engine §2.2: 40/25/25).
    - Todas las velas tienen `dt` tz-aware (ADR-0002).
    - Las velas están ordenadas antigua→reciente (requisito del motor).
    - No hay timestamps duplicados.
    - La relación OHLC es válida: l ≤ o ≤ h, l ≤ c ≤ h, h ≥ l.
    - Todos los precios son positivos.

Checks NO realizados (responsabilidad del caller / otros módulos):

    - Intervalos correctos entre velas consecutivas (requiere market
      calendar para distinguir gaps normales entre sesiones de gaps
      corruptos intra-sesión).
    - Staleness (la última vela es reciente): lo chequea el scheduler
      del ciclo AUTO con su propio criterio.

`check_integrity()` acumula TODOS los issues en `notes` — un único call
da el diagnóstico completo para logs y para el chat de desarrollo.
"""

from __future__ import annotations

from engines.data.models import Candle, IntegrityResult, Timeframe

# ───────────────────────────────────────────────────────────────────────────
# Mínimos por timeframe (Scoring Engine §2.2 — "mínimo 40 para MAs", etc.).
# Nota: el *warmup* del Data Engine es mayor (210/80/50 de FEATURE_DECISIONS
# §3.1), pero la integridad solo rechaza listas por debajo del mínimo
# funcional del motor. Una lista con 50 daily pasa integridad aunque esté
# por debajo del warmup deseado — el Data Engine decidirá si la usa o
# disparará más fetches.
# ───────────────────────────────────────────────────────────────────────────
_MIN_REQUIRED: dict[Timeframe, int] = {
    Timeframe.DAILY: 40,
    Timeframe.H1: 25,
    Timeframe.M15: 25,
}


def check_integrity(
    candles: list[Candle],
    timeframe: Timeframe,
    *,
    min_count: int | None = None,
) -> IntegrityResult:
    """Verifica integridad estructural de una lista de velas.

    Args:
        candles: velas a verificar. Se espera orden antigua→reciente.
        timeframe: el timeframe al que corresponden. Determina el mínimo
            de velas requerido si `min_count` no se provee.
        min_count: override del mínimo requerido. Útil para tests y para
            casos donde el caller sabe que una cantidad menor es válida.

    Returns:
        `IntegrityResult`. `ok=True` si y solo si `notes` está vacía.
    """
    notes: list[str] = []

    if not candles:
        notes.append("empty: lista de velas vacía")
        return IntegrityResult(
            ok=False,
            notes=notes,
            checked_count=0,
            timeframe=timeframe,
        )

    required = min_count if min_count is not None else _MIN_REQUIRED[timeframe]
    if len(candles) < required:
        notes.append(f"too_few_candles: recibidas={len(candles)}, mínimo={required}")

    # TZ awareness — reportamos todos los índices con problema.
    for i, c in enumerate(candles):
        if c.dt.tzinfo is None:
            notes.append(f"missing_tz: candle[{i}] dt={c.dt!s} sin tzinfo")

    # Orden + duplicados — comparación vela-a-vela. Saltamos pares con tz
    # mixta (naive + aware) porque Python lanza TypeError al comparar; el
    # problema de fondo ya quedó reportado como `missing_tz` arriba.
    for i in range(1, len(candles)):
        prev = candles[i - 1]
        curr = candles[i]
        if (curr.dt.tzinfo is None) != (prev.dt.tzinfo is None):
            continue
        if curr.dt == prev.dt:
            notes.append(f"duplicate_ts: candle[{i}] mismo dt que candle[{i - 1}] ({curr.dt!s})")
        elif curr.dt < prev.dt:
            notes.append(
                f"out_of_order: candle[{i}].dt ({curr.dt!s}) < candle[{i - 1}].dt ({prev.dt!s})"
            )

    # OHLC válido + precios positivos.
    for i, c in enumerate(candles):
        if c.h < c.l:
            notes.append(f"invalid_ohlc: candle[{i}] high={c.h} < low={c.l}")
            continue  # resto de checks OHLC no tienen sentido si h<l
        if c.o < c.l or c.o > c.h:
            notes.append(
                f"invalid_ohlc: candle[{i}] open={c.o} fuera del rango [low={c.l}, high={c.h}]"
            )
        if c.c < c.l or c.c > c.h:
            notes.append(
                f"invalid_ohlc: candle[{i}] close={c.c} fuera del rango [low={c.l}, high={c.h}]"
            )
        if c.o <= 0 or c.h <= 0 or c.l <= 0 or c.c <= 0:
            notes.append(
                f"non_positive_price: candle[{i}] tiene precio ≤ 0 "
                f"(o={c.o}, h={c.h}, l={c.l}, c={c.c})"
            )

    return IntegrityResult(
        ok=len(notes) == 0,
        notes=notes,
        checked_count=len(candles),
        timeframe=timeframe,
    )
