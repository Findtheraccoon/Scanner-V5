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

from modules.db.bootstrap import init_db
from modules.db.helpers import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    read_signal_by_id,
    read_signals_history,
    read_signals_latest,
    write_heartbeat,
    write_signal,
    write_system_log,
)
from modules.db.models import ET_TZ, Base, Heartbeat, Signal, SystemLog, now_et
from modules.db.session import default_url, make_engine, make_session_factory

__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "ET_TZ",
    "MAX_PAGE_LIMIT",
    "Base",
    "Heartbeat",
    "Signal",
    "SystemLog",
    "default_url",
    "init_db",
    "make_engine",
    "make_session_factory",
    "now_et",
    "read_signal_by_id",
    "read_signals_history",
    "read_signals_latest",
    "write_heartbeat",
    "write_signal",
    "write_system_log",
]
