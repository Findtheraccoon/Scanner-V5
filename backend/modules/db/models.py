"""Modelos SQLAlchemy 2.0 async del módulo DB.

Tres tablas iniciales según `docs/specs/SCANNER_V5_FEATURE_DECISIONS.md §3.6/3.7`:

1. **`signals`** — schema híbrido 3 (columnas planas + blobs JSON +
   snapshot gzip). ~3 KB/señal. Persistencia inmutable — las señales
   nunca se actualizan después de emitidas.
2. **`heartbeat`** — estado de motores cada 2 min. TTL 24h (la limpieza
   la hace el Database Engine, no el ORM).
3. **`system_log`** — eventos críticos del sistema. Retención 30 días.

**Timestamps ET tz-aware** (ADR-0002): todos los `datetime` persistidos
llevan `zoneinfo.ZoneInfo("America/New_York")`. El helper `now_et()`
centraliza la convención y se usa como default factory.
"""

from __future__ import annotations

import datetime as _dt
import zoneinfo

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ET_TZ = zoneinfo.ZoneInfo("America/New_York")


def now_et() -> _dt.datetime:
    """Timestamp tz-aware en Eastern Time (ADR-0002).

    Usar como default factory en todos los campos `ts`/`compute_timestamp`.
    Nunca usar `datetime.now()` naive — rompería la invariante ET-aware.
    """
    return _dt.datetime.now(ET_TZ)


class ETDateTime(TypeDecorator):
    """`DateTime` que garantiza tz-aware ET al leer y escribir (ADR-0002).

    SQLite no soporta `ETDateTime()` nativamente — descarta el
    tzinfo al persistir. Este decorator:

    - **Al escribir (bind):** exige que el `datetime` sea tz-aware y lo
      convierte a ET si viniera de otra zona. Persiste el string ISO8601
      con el offset de ET.
    - **Al leer (result):** re-ata `ET_TZ` al datetime naive que devuelve
      SQLite. En Postgres (futuro) el tzinfo ya viene y se normaliza a ET.

    El resultado es que el código que consume estos campos siempre ve
    `datetime` con `tzinfo == ET_TZ`, cumpliendo ADR-0002 cualquiera sea
    el motor de DB.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: _dt.datetime | None, dialect,
    ) -> _dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                "ETDateTime requires tz-aware datetime (ADR-0002). "
                "Use `now_et()` or explicit `zoneinfo.ZoneInfo('America/New_York')`."
            )
        return value.astimezone(ET_TZ)

    def process_result_value(
        self, value: _dt.datetime | None, dialect,
    ) -> _dt.datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            # SQLite strip: re-atachar ET (el valor guardado YA estaba en ET
            # por el bind, así que el datetime naive representa "ET").
            return value.replace(tzinfo=ET_TZ)
        return value.astimezone(ET_TZ)


class Base(DeclarativeBase):
    """Base declarativa común a todos los modelos."""


class Signal(Base):
    """Señal emitida por el Scoring Engine.

    Schema híbrido 3: columnas planas para filtros + blobs JSON para el
    desglose + snapshot gzip opcional para reproducibilidad perfecta.

    **Inmutable** — las señales no se modifican después de escritas. Si
    el motor se actualiza, las señales viejas quedan como histórico del
    estado en el momento del cálculo.
    """

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Timestamps — ambos tz-aware ET
    candle_timestamp: Mapped[_dt.datetime] = mapped_column(ETDateTime())
    compute_timestamp: Mapped[_dt.datetime] = mapped_column(
        ETDateTime(), default=now_et,
    )

    # Terna spec (engine + fixture)
    engine_version: Mapped[str] = mapped_column(String(32))
    fixture_id: Mapped[str] = mapped_column(String(64))
    fixture_version: Mapped[str] = mapped_column(String(16))

    # Contexto operacional
    slot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ticker: Mapped[str] = mapped_column(String(10))

    # Resultado (columnas planas para filtros rápidos)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    conf: Mapped[str] = mapped_column(String(8))
    signal: Mapped[bool] = mapped_column(default=False)
    dir: Mapped[str | None] = mapped_column(String(4), nullable=True)
    blocked: Mapped[bool] = mapped_column(default=False)
    error: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Blobs JSON — desglose completo del análisis
    layers_json: Mapped[dict] = mapped_column(JSON)
    ind_json: Mapped[dict] = mapped_column(JSON)
    patterns_json: Mapped[list] = mapped_column(JSON)
    sec_rel_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    div_spy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Snapshot de inputs (reproducibilidad perfecta)
    candles_snapshot_gzip: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True,
    )

    __table_args__ = (
        # Filtros típicos: "señales de QQQ ordenadas por tiempo de candle"
        Index("ix_signals_ticker_candle_ts", "ticker", "candle_timestamp"),
        # Filtro por slot (cockpit real-time)
        Index("ix_signals_slot_compute_ts", "slot_id", "compute_timestamp"),
        # Filtro temporal puro (histórico global)
        Index("ix_signals_compute_ts", "compute_timestamp"),
    )


class Heartbeat(Base):
    """Estado de cada motor cada 2 min. TTL 24h (limpieza externa)."""

    __tablename__ = "heartbeat"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[_dt.datetime] = mapped_column(
        ETDateTime(), default=now_et,
    )
    engine: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(8))  # green/yellow/red/offline
    memory_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        Index("ix_heartbeat_engine_ts", "engine", "ts"),
        Index("ix_heartbeat_ts", "ts"),
    )


class SystemLog(Base):
    """Eventos críticos del sistema. Retención 30 días (luego a archive)."""

    __tablename__ = "system_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[_dt.datetime] = mapped_column(
        ETDateTime(), default=now_et,
    )
    level: Mapped[str] = mapped_column(String(8))  # info/warning/error
    source: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(16), nullable=True)

    __table_args__ = (
        Index("ix_system_log_level_ts", "level", "ts"),
        Index("ix_system_log_ts", "ts"),
    )
