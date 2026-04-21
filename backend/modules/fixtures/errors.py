"""Errores del loader/validador de fixtures.

Códigos `FIX-XXX` definidos en `docs/specs/FIXTURE_SPEC.md §6` y
`FIXTURE_ERRORS.md`. Cada error expone `code` y `detail` para logging
estructurado y presentación al chat de desarrollo.
"""

from __future__ import annotations

# ───────────────────────────────────────────────────────────────────────────
# Códigos de error (FIX-XXX)
# ───────────────────────────────────────────────────────────────────────────

FIX_000 = "FIX-000"  # I/O error (archivo no existe, no JSON válido)
FIX_001 = "FIX-001"  # Campo obligatorio faltante o tipo inválido
FIX_003 = "FIX-003"  # confirm_weights: categoría requerida ausente
FIX_005 = "FIX-005"  # confirm_weights: categoría desconocida
FIX_006 = "FIX-006"  # confirm_weights: peso fuera del rango [0, 10]
FIX_007 = "FIX-007"  # Bloque top-level no reconocido
FIX_011 = "FIX-011"  # ticker_info: benchmark/requires_bench_daily inconsistentes
FIX_020 = "FIX-020"  # score_bands: bandas no contiguas (gap)
FIX_021 = "FIX-021"  # score_bands: bandas superpuestas (overlap)
FIX_022 = "FIX-022"  # score_bands: max=null fuera de la banda superior
FIX_023 = "FIX-023"  # score_bands: banda inferior con min < 0
FIX_024 = "FIX-024"  # score_bands: labels duplicados


class FixtureError(ValueError):
    """Error estructurado del loader/validador de fixtures.

    Siempre tiene un código `FIX-XXX` y un `detail` humano.
    """

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")
