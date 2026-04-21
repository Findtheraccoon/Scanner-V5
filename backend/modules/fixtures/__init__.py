"""Módulo de carga y validación de fixtures JSON.

API pública:

    - `load_fixture(path)` → Fixture           # archivo → modelo validado
    - `parse_fixture(data)` → Fixture          # dict → modelo validado
    - `Fixture` y sub-modelos Pydantic
    - `FixtureError` + códigos FIX-XXX constants

Ver `docs/specs/FIXTURE_SPEC.md` para el schema completo y
`modules/fixtures/loader.py` para la secuencia de validación.
"""

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
from modules.fixtures.loader import load_fixture, parse_fixture
from modules.fixtures.models import (
    CONFIRM_CATEGORIES,
    DetectionThresholds,
    Fixture,
    FixtureMetadata,
    ScoreBand,
    TickerInfo,
)

__all__ = [
    "CONFIRM_CATEGORIES",
    "FIX_000",
    "FIX_001",
    "FIX_003",
    "FIX_005",
    "FIX_006",
    "FIX_007",
    "FIX_011",
    "FIX_020",
    "FIX_021",
    "FIX_022",
    "FIX_023",
    "FIX_024",
    "DetectionThresholds",
    "Fixture",
    "FixtureError",
    "FixtureMetadata",
    "ScoreBand",
    "TickerInfo",
    "load_fixture",
    "parse_fixture",
]
