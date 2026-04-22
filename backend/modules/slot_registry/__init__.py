"""Módulo del slot registry del scanner.

Carga y valida `slot_registry.json` — el archivo de topología operativa
que el scanner lee al arrancar para saber qué corre en cada slot.

API pública:

    - `load_registry(path, *, engine_version)` → SlotRegistry
    - `SlotRegistry`, `SlotRecord`, `RegistryMetadata` (Pydantic types)
    - `RegistryError` + códigos REG-XXX

Ver `docs/specs/SLOT_REGISTRY_SPEC.md` para el schema completo y las
reglas de validación con severidades (fatal vs per-slot DEGRADED).
"""

from modules.slot_registry.errors import (
    REG_001,
    REG_002,
    REG_003,
    REG_004,
    REG_005,
    REG_010,
    REG_011,
    REG_012,
    REG_013,
    REG_020,
    REG_030,
    REG_101,
    RegistryError,
)
from modules.slot_registry.loader import load_registry
from modules.slot_registry.models import (
    RegistryMetadata,
    SlotRecord,
    SlotRegistry,
    SlotState,
)
from modules.slot_registry.writer import save_registry

__all__ = [
    "REG_001",
    "REG_002",
    "REG_003",
    "REG_004",
    "REG_005",
    "REG_010",
    "REG_011",
    "REG_012",
    "REG_013",
    "REG_020",
    "REG_030",
    "REG_101",
    "RegistryError",
    "RegistryMetadata",
    "SlotRecord",
    "SlotRegistry",
    "SlotState",
    "load_registry",
    "save_registry",
]
