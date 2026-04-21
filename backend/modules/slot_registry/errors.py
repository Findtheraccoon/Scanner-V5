"""Errores del loader del slot registry.

Códigos `REG-XXX` definidos en `docs/specs/SLOT_REGISTRY_SPEC.md §5-§8`.

Severidad según §8:

    FATAL (abort del arranque):
        REG-001  archivo no existe
        REG-002  JSON inválido / shape no esperada
        REG-003  cantidad de slots != 6
        REG-004  IDs de slot duplicados / no cubren 1-6
        REG-020  hash del canonical no matchea .sha256
        REG-030  engine_version_required no incluye motor actual

    PER-SLOT DEGRADED (sistema arranca, slot no opera):
        REG-005  ticker duplicado entre enabled slots
        REG-010  archivo de fixture no encontrado
        REG-011  fixture.engine_compat_range no incluye motor actual
        REG-012  slot.ticker != fixture.ticker_info.ticker
        REG-013  slot.benchmark != fixture.ticker_info.benchmark
        (y cualquier código FIX-XXX del loader de fixtures)

    WARNING (no crítico):
        REG-101  slot disabled con campos populados
"""

from __future__ import annotations

# Fatal — abortan el arranque
REG_001 = "REG-001"  # archivo no existe
REG_002 = "REG-002"  # JSON inválido / shape no esperada
REG_003 = "REG-003"  # cantidad de slots != 6 / no cubren 1..6
REG_004 = "REG-004"  # ID de slot duplicado
REG_020 = "REG-020"  # canonical hash mismatch
REG_030 = "REG-030"  # engine_version_required no incluye motor actual

# Per-slot DEGRADED
REG_005 = "REG-005"  # ticker duplicado en slots enabled
REG_010 = "REG-010"  # fixture file not found
REG_011 = "REG-011"  # fixture.engine_compat_range incompatible
REG_012 = "REG-012"  # slot.ticker != fixture ticker
REG_013 = "REG-013"  # slot.benchmark != fixture benchmark

# Warning
REG_101 = "REG-101"  # slot disabled con campos populados


class RegistryError(ValueError):
    """Error fatal del loader del slot registry.

    Solo se lanza para códigos que abortan el arranque. Los errores
    per-slot se reflejan en el campo `status=DEGRADED` del `SlotRecord`
    correspondiente, con `error_code` y `error_detail` describiendo la
    causa.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
