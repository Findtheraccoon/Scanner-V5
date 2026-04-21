"""Constantes del Scoring Engine v5.2.0.

Valores inmutables del motor según `docs/specs/SCORING_ENGINE_SPEC.md`.
Cambios acá implican bump semver del motor (ver §4 del spec).
"""

from __future__ import annotations

# ───────────────────────────────────────────────────────────────────────────
# Identidad del motor
# ───────────────────────────────────────────────────────────────────────────

ENGINE_VERSION: str = "5.2.0"
"""Versión del Scoring Engine. Aparece en el output de `analyze()`."""

FIXTURE_COMPAT_RANGE: str = ">=5.0.0,<6.0.0"
"""Rango de schema de fixture que este motor acepta (spec §4.2)."""

# ───────────────────────────────────────────────────────────────────────────
# Mínimos de velas (spec §2.2)
# ───────────────────────────────────────────────────────────────────────────

MIN_CANDLES_DAILY: int = 40
MIN_CANDLES_1H: int = 25
MIN_CANDLES_15M: int = 25

# ───────────────────────────────────────────────────────────────────────────
# Códigos de error (spec §3, invariante I3)
# ───────────────────────────────────────────────────────────────────────────

ENG_001: str = "ENG-001"  # Candles insuficientes / inputs obligatorios faltantes
ENG_010: str = "ENG-010"  # Fixture inválida o ausente de campos críticos
ENG_020: str = "ENG-020"  # División por cero en cálculo de indicador
ENG_050: str = "ENG-050"  # Parity check fallido (healthcheck)
ENG_060: str = "ENG-060"  # Ticker sin datos N ciclos (emitido por el Data Engine)
ENG_099: str = "ENG-099"  # Catch-all inesperado

# ───────────────────────────────────────────────────────────────────────────
# Valores de output (spec §2.3)
# ───────────────────────────────────────────────────────────────────────────

CONF_UNKNOWN: str = "—"  # Cuando no hay señal o está bloqueada
SIGNAL_SETUP: str = "SETUP"
SIGNAL_REVISAR: str = "REVISAR"
SIGNAL_NEUTRAL: str = "NEUTRAL"

DIR_CALL: str = "CALL"
DIR_PUT: str = "PUT"
