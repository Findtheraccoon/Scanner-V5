"""Loader y validador de fixture JSON.

Punto de entrada único: `load_fixture(path)` para archivo, o
`parse_fixture(dict)` si el dict ya está decodeado (ej. tests, fixtures
embebidas en Config del usuario).

Estrategia de validación (en orden):

    1. I/O (abrir + `json.load`) — mapea a `FIX-000` si falla.
    2. Bloques top-level: 5 esperados, ni más ni menos — `FIX-007`.
    3. `confirm_weights`: exactamente las 10 categorías canónicas, pesos
       en [0, 10] — `FIX-003` / `FIX-005` / `FIX-006`.
    4. Pydantic `Fixture.model_validate(data)`: tipos, rangos de
       thresholds, required fields — `FIX-001` como fallback genérico.
    5. Cross-campo semántica:
       - `ticker_info.benchmark` vs `requires_bench_daily` — `FIX-011`.
       - `score_bands`: contiguidad, overlap, max=null solo en top,
         bottom.min ≥ 0, labels únicos — `FIX-020..024`.

Cada paso puede abortar con `FixtureError` que lleva su código y un
detail humano.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from modules.fixtures.errors import (
    FIX_000,
    FIX_001,
    FIX_003,
    FIX_005,
    FIX_006,
    FIX_007,
    FIX_011,
    FIX_020,
    FIX_021,
    FIX_022,
    FIX_023,
    FIX_024,
    FixtureError,
)
from modules.fixtures.models import (
    CONFIRM_CATEGORIES,
    WEIGHT_MAX,
    WEIGHT_MIN,
    Fixture,
)

_TOP_LEVEL_BLOCKS: frozenset[str] = frozenset(
    {
        "metadata",
        "ticker_info",
        "confirm_weights",
        "detection_thresholds",
        "score_bands",
    }
)


# ═══════════════════════════════════════════════════════════════════════════
# API pública
# ═══════════════════════════════════════════════════════════════════════════


def load_fixture(path: str | Path) -> Fixture:
    """Carga y valida una fixture desde un archivo JSON.

    Args:
        path: ruta al archivo `.json`.

    Returns:
        `Fixture` validada.

    Raises:
        FixtureError: cualquier problema de I/O, schema o semántica.
            `code` contiene el `FIX-XXX` específico.
    """
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        raise FixtureError(FIX_000, f"no se pudo leer {p!s}: {e}") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise FixtureError(FIX_000, f"JSON inválido en {p!s}: {e}") from e
    if not isinstance(data, dict):
        raise FixtureError(FIX_000, f"la fixture en {p!s} no es un objeto JSON top-level")
    return parse_fixture(data)


def parse_fixture(data: dict[str, Any]) -> Fixture:
    """Valida un dict ya JSON-decodeado como fixture.

    Args:
        data: dict con los 5 bloques top-level.

    Returns:
        `Fixture` validada.

    Raises:
        FixtureError: según las reglas de §1-§5 del módulo.
    """
    _validate_top_level_blocks(data)
    _validate_confirm_weights_dict(data.get("confirm_weights", {}))
    try:
        fixture = Fixture.model_validate(data)
    except ValidationError as e:
        raise FixtureError(FIX_001, _summarize_pydantic_errors(e)) from e
    _validate_ticker_info_consistency(fixture)
    _validate_score_bands(fixture)
    return fixture


# ═══════════════════════════════════════════════════════════════════════════
# Validadores (internos)
# ═══════════════════════════════════════════════════════════════════════════


def _validate_top_level_blocks(data: dict[str, Any]) -> None:
    """Bloques top-level: los 5 esperados, ni más ni menos.

    - Faltante → FIX-001 ("missing required block ...")
    - Desconocido → FIX-007 ("unknown top-level block ...")
    """
    keys = set(data.keys())
    missing = _TOP_LEVEL_BLOCKS - keys
    if missing:
        raise FixtureError(
            FIX_001,
            f"missing required top-level block(s): {sorted(missing)}",
        )
    extra = keys - _TOP_LEVEL_BLOCKS
    if extra:
        raise FixtureError(
            FIX_007,
            f"unknown top-level block(s): {sorted(extra)}. "
            f"Valid blocks: {sorted(_TOP_LEVEL_BLOCKS)}",
        )


def _validate_confirm_weights_dict(weights: Any) -> None:
    """Categorías exactas, pesos numéricos en [0, 10].

    - Faltantes → FIX-003
    - Desconocidas → FIX-005
    - Fuera de rango o tipo no numérico → FIX-006
    """
    if not isinstance(weights, dict):
        raise FixtureError(FIX_001, "confirm_weights must be an object")
    keys = set(weights.keys())
    missing = CONFIRM_CATEGORIES - keys
    if missing:
        raise FixtureError(
            FIX_003,
            f"confirm_weights missing required categor(y|ies): {sorted(missing)}",
        )
    unknown = keys - CONFIRM_CATEGORIES
    if unknown:
        raise FixtureError(
            FIX_005,
            f"confirm_weights contains unknown categor(y|ies): {sorted(unknown)}. "
            f"Valid categories: {sorted(CONFIRM_CATEGORIES)}",
        )
    for cat, value in weights.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            # bool es subclass de int — excluir explícitamente.
            raise FixtureError(
                FIX_006,
                f"confirm_weights.{cat} has non-numeric value: {value!r}",
            )
        if not (WEIGHT_MIN <= value <= WEIGHT_MAX):
            raise FixtureError(
                FIX_006,
                f"confirm_weights.{cat} value {value} out of range [{WEIGHT_MIN}, {WEIGHT_MAX}]",
            )


def _validate_ticker_info_consistency(fx: Fixture) -> None:
    """`benchmark=null` ⇔ `requires_bench_daily=False`.

    Violaciones → FIX-011.
    """
    bench = fx.ticker_info.benchmark
    requires = fx.ticker_info.requires_bench_daily
    if bench is None and requires:
        raise FixtureError(
            FIX_011,
            "ticker_info inconsistent. benchmark is null but requires_bench_daily is true",
        )
    if bench is not None and not requires:
        raise FixtureError(
            FIX_011,
            f"ticker_info inconsistent. benchmark is {bench!r} but requires_bench_daily is false",
        )


def _validate_score_bands(fx: Fixture) -> None:
    """Reglas de §3.5 del spec."""
    bands = fx.score_bands
    if not bands:
        raise FixtureError(FIX_001, "score_bands must be a non-empty array")

    # Solo la banda superior (índice 0) puede tener max=null.
    if bands[0].max is not None:
        raise FixtureError(
            FIX_022,
            f"top score_band (label={bands[0].label!r}) must have max=null",
        )
    for i, band in enumerate(bands[1:], start=1):
        if band.max is None:
            raise FixtureError(
                FIX_022,
                f"score_band[{i}] (label={band.label!r}) has max=null but is not the top band",
            )

    # Contiguidad + overlap: para i>=1, band.max == bands[i-1].min.
    for i in range(1, len(bands)):
        prev_min = bands[i - 1].min
        curr_max = bands[i].max
        if curr_max is None:
            continue  # ya capturado arriba
        if curr_max < prev_min:
            raise FixtureError(
                FIX_020,
                (
                    f"score_bands are not contiguous. Gap between band "
                    f"{bands[i - 1].label!r} (min={prev_min}) and band "
                    f"{bands[i].label!r} (max={curr_max})"
                ),
            )
        if curr_max > prev_min:
            raise FixtureError(
                FIX_021,
                (
                    f"score_bands overlap. Band {bands[i - 1].label!r} "
                    f"(min={prev_min}) overlaps with band "
                    f"{bands[i].label!r} (max={curr_max})"
                ),
            )

    # Bottom band min ≥ 0.
    if bands[-1].min < 0:
        raise FixtureError(
            FIX_023,
            f"bottom score_band (label={bands[-1].label!r}) has min={bands[-1].min} < 0",
        )

    # Labels únicos.
    labels = [b.label for b in bands]
    if len(set(labels)) != len(labels):
        seen: set[str] = set()
        dupes: list[str] = []
        for lab in labels:
            if lab in seen:
                dupes.append(lab)
            seen.add(lab)
        raise FixtureError(FIX_024, f"score_bands have duplicate label(s): {dupes}")


def _summarize_pydantic_errors(err: ValidationError) -> str:
    """Genera un detail humano de los errores de Pydantic para FIX-001."""
    lines: list[str] = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e.get("loc", ()))
        msg = e.get("msg", "")
        lines.append(f"{loc}: {msg}")
    return "; ".join(lines) if lines else "schema validation failed"
