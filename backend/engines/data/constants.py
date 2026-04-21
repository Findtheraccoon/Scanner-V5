"""Constantes del Data Engine.

Valores derivados de decisiones operativas documentadas en
`docs/operational/FEATURE_DECISIONS.md` y en los ADRs 0002-0004.
"""

from zoneinfo import ZoneInfo

# ───────────────────────────────────────────────────────────────────────────
# Zona horaria del producto (ADR-0002 — ET tz-aware, mono-zona por diseño)
# ───────────────────────────────────────────────────────────────────────────
ET = ZoneInfo("America/New_York")

# ───────────────────────────────────────────────────────────────────────────
# Warmup por timeframe (FEATURE_DECISIONS §3.1, ADR-0003)
#
# Son los tamaños totales requeridos para que todos los indicadores del
# Scoring Engine estén definidos. El warmup real es el gap entre lo que hay
# en DB local y estos totales.
# ───────────────────────────────────────────────────────────────────────────
WARMUP_DAILY_N = 210
WARMUP_1H_N = 80
WARMUP_15M_N = 50

# ───────────────────────────────────────────────────────────────────────────
# Twelve Data
# ───────────────────────────────────────────────────────────────────────────
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
MAX_API_KEYS = 5  # cardinalidad fija del Config del usuario

# ───────────────────────────────────────────────────────────────────────────
# Retry policy (ADR-0004)
#
# Fallo de fetch de un ticker → retry corto 1s → skip en ciclo si falla.
# N ciclos consecutivos fallidos → slot pasa a DEGRADED con código ENG-060.
# Auto-recupera al primer éxito.
# ───────────────────────────────────────────────────────────────────────────
RETRY_SHORT_DELAY_S = 1.0
ENG_060_CYCLES_THRESHOLD = 3  # tentativo — confirmar en implementación real

# ───────────────────────────────────────────────────────────────────────────
# Ciclo AUTO (FEATURE_DECISIONS §3.1)
#
# Cierre vela 15M ET → delay → fetch + integridad → señal al Scoring.
# ───────────────────────────────────────────────────────────────────────────
AUTO_CYCLE_DELAY_AFTER_CLOSE_S = 3.0

# ───────────────────────────────────────────────────────────────────────────
# Heartbeat del motor (FEATURE_DECISIONS transversales)
# ───────────────────────────────────────────────────────────────────────────
HEARTBEAT_INTERVAL_S = 120.0  # cada 2 minutos

# ───────────────────────────────────────────────────────────────────────────
# Códigos de error emitidos por el Data Engine
# ───────────────────────────────────────────────────────────────────────────
ENG_060 = "ENG-060"  # ticker sin datos N ciclos → slot DEGRADED
