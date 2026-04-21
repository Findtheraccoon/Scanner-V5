"""Modelos Pydantic de una fixture de ticker.

Reflejan los 5 bloques del schema v5.0.0 descrito en
`docs/specs/FIXTURE_SPEC.md`. La validación de tipos y rangos básicos
la hace Pydantic automáticamente; las validaciones semánticas
cross-campo viven en `loader.py` para poder mapearlas a códigos
`FIX-XXX` específicos con detalle humano.

`Fixture` usa `extra="forbid"` en los 4 bloques strictamente
definidos (ticker_info, detection_thresholds, ScoreBand, Fixture
top-level). `metadata` permite `extra="allow"` para forward-compat
con MINOR bumps del schema que agregan campos opcionales nuevos
(ver `FIXTURE_SPEC.md §4.1`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ═══════════════════════════════════════════════════════════════════════════
# Lista canónica de confirms (Scoring Engine §5.2, FIXTURE_SPEC §3.3)
# ═══════════════════════════════════════════════════════════════════════════

CONFIRM_CATEGORIES: frozenset[str] = frozenset(
    {
        "FzaRel",
        "BBinf_1H",
        "BBsup_1H",
        "BBinf_D",
        "BBsup_D",
        "VolHigh",
        "VolSeq",
        "Gap",
        "SqExp",
        "DivSPY",
    }
)

WEIGHT_MIN: float = 0.0
WEIGHT_MAX: float = 10.0


# ═══════════════════════════════════════════════════════════════════════════
# Bloques del schema
# ═══════════════════════════════════════════════════════════════════════════


class FixtureMetadata(BaseModel):
    """Bloque `metadata` de una fixture.

    Permite campos extra para forward-compat con futuras MINOR del schema
    (ej. `calibration_dataset_hash`). Los campos listados son los
    reconocidos oficialmente en schema v5.0.0.
    """

    model_config = ConfigDict(extra="allow", frozen=True)

    fixture_id: str = Field(description="Identificador único de la fixture.")
    fixture_version: str = Field(description='Semver "MAJOR.MINOR.PATCH".')
    engine_compat_range: str = Field(
        description='Rango semver del motor compatible (ej. ">=5.2.0,<6.0.0").'
    )
    canonical_ref: str | None = Field(default=None)
    generated_at: datetime = Field(description="Timestamp de creación (ISO 8601).")
    generated_from: str | None = Field(default=None)
    description: str = Field(description="Descripción humana corta.")
    author: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class TickerInfo(BaseModel):
    """Bloque `ticker_info`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(description="Símbolo del ticker en mayúsculas.")
    benchmark: str | None = Field(description="Símbolo del benchmark, o null.")
    requires_spy_daily: bool
    requires_bench_daily: bool


class DetectionThresholds(BaseModel):
    """Bloque `detection_thresholds`.

    Rangos por campo definidos en `FIXTURE_SPEC.md §3.4`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fzarel_min_divergence_pct: float = Field(gt=0.0, le=5.0)
    divspy_asset_threshold_pct: float = Field(gt=0.0, le=5.0)
    divspy_spy_threshold_pct: float = Field(gt=0.0, le=5.0)
    volhigh_min_ratio: float = Field(gt=1.0, le=5.0)


class ScoreBand(BaseModel):
    """Una banda de score_bands."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min: float
    max: float | None
    label: str
    signal: Literal["SETUP", "REVISAR", "NEUTRAL"]


class Fixture(BaseModel):
    """Fixture completa de un ticker.

    Producto de `load_fixture()` o `parse_fixture()`. Inmutable tras
    construcción (`frozen=True`).

    `confirm_weights` se expone como `dict[str, float]` — su contenido
    se valida fuera del modelo Pydantic (ver `loader.py`) para poder
    distinguir `FIX-003` (categoría faltante), `FIX-005` (categoría
    desconocida) y `FIX-006` (peso fuera de rango) con detalle humano.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: FixtureMetadata
    ticker_info: TickerInfo
    confirm_weights: dict[str, float]
    detection_thresholds: DetectionThresholds
    score_bands: list[ScoreBand]
