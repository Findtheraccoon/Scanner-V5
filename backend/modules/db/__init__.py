"""Módulo DB — capa de persistencia del Scanner-V5.

Exporta los modelos SQLAlchemy + helpers de engine/session + función
de bootstrap. Los consumidores (motores + API) importan desde acá.

Invariantes (ver README):

1. Todos los timestamps son tz-aware en Eastern Time (ADR-0002).
2. El caller NO manipula objetos SQLAlchemy directamente — se usan
   los helpers `db.write_*` / `db.read_*` (sub-fase C5.2).
3. El archive es transparente: las queries históricas lo resuelven
   internamente según rango.
"""

from modules.db.backup import (
    S3Config,
    backup_to_s3,
    list_backups,
    restore_from_s3,
)
from modules.db.bootstrap import init_db
from modules.db.helpers import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    CandleTF,
    ValidatorTrigger,
    latest_candle_dt,
    read_candles_window,
    read_signal_by_id,
    read_signals_history,
    read_signals_latest,
    read_validator_report_by_id,
    read_validator_reports_history,
    read_validator_reports_latest,
    write_candles_batch,
    write_heartbeat,
    write_signal,
    write_system_log,
    write_validator_report,
)
from modules.db.models import (
    ET_TZ,
    Base,
    CandleDaily,
    CandleH1,
    CandleM15,
    Heartbeat,
    Signal,
    SystemLog,
    ValidatorReportRecord,
    now_et,
)
from modules.db.session import default_url, make_engine, make_session_factory

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "ET_TZ",
    "MAX_PAGE_LIMIT",
    "Base",
    "CandleDaily",
    "CandleH1",
    "CandleM15",
    "CandleTF",
    "Heartbeat",
    "S3Config",
    "Signal",
    "SystemLog",
    "ValidatorReportRecord",
    "ValidatorTrigger",
    "backup_to_s3",
    "default_url",
    "init_db",
    "latest_candle_dt",
    "list_backups",
    "make_engine",
    "make_session_factory",
    "now_et",
    "read_candles_window",
    "read_signal_by_id",
    "read_signals_history",
    "read_signals_latest",
    "read_validator_report_by_id",
    "read_validator_reports_history",
    "read_validator_reports_latest",
    "restore_from_s3",
    "write_candles_batch",
    "write_heartbeat",
    "write_signal",
    "write_system_log",
    "write_validator_report",
]
