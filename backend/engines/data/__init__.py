"""Data Engine — motor vivo responsable de la obtención de datos de mercado.

API pública del paquete. Los consumers del motor solo deben importar
desde este módulo, no de submódulos internos.

Ver `backend/engines/data/README.md` para responsabilidades completas y
contratos con otros componentes.
"""

from engines.data.api_keys import KeyPool, KeyPoolExhaustedError
from engines.data.config import DataEngineConfig
from engines.data.constants import (
    AUTO_CYCLE_DELAY_AFTER_CLOSE_S,
    ENG_060,
    ENG_060_CYCLES_THRESHOLD,
    ET,
    HEARTBEAT_INTERVAL_S,
    MAX_API_KEYS,
    RETRY_SHORT_DELAY_S,
    WARMUP_1H_N,
    WARMUP_15M_N,
    WARMUP_DAILY_N,
)
from engines.data.fetcher import TwelveDataClient, TwelveDataError
from engines.data.integrity import check_integrity
from engines.data.market_calendar import (
    is_market_day,
    is_market_open,
    next_close,
    previous_close,
    session_close,
)
from engines.data.models import (
    ApiKeyConfig,
    ApiKeyState,
    Candle,
    EngineStatus,
    FetchResult,
    IntegrityResult,
    SlotStatus,
    Timeframe,
)

__all__ = [
    "AUTO_CYCLE_DELAY_AFTER_CLOSE_S",
    "ENG_060",
    "ENG_060_CYCLES_THRESHOLD",
    "ET",
    "HEARTBEAT_INTERVAL_S",
    "MAX_API_KEYS",
    "RETRY_SHORT_DELAY_S",
    "WARMUP_1H_N",
    "WARMUP_15M_N",
    "WARMUP_DAILY_N",
    "ApiKeyConfig",
    "ApiKeyState",
    "Candle",
    "DataEngineConfig",
    "EngineStatus",
    "FetchResult",
    "IntegrityResult",
    "KeyPool",
    "KeyPoolExhaustedError",
    "SlotStatus",
    "Timeframe",
    "TwelveDataClient",
    "TwelveDataError",
    "check_integrity",
    "is_market_day",
    "is_market_open",
    "next_close",
    "previous_close",
    "session_close",
]
