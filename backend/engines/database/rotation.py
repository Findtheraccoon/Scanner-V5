"""Rotación de datos vencidos según políticas de retención (spec §3.7).

**Políticas del spec §3.7:**

| Tabla          | Retención operativa | Destino     |
|----------------|---------------------|-------------|
| `signals`      | 1 año               | archive     |
| `heartbeat`    | 24h                 | **borrar**  |
| `system_log`   | 30 días             | archive     |
| `candles_daily`| 3 años              | archive     |
| `candles_1h`   | 6 meses             | archive     |
| `candles_15m`  | 3 meses             | archive     |

**Modo:**

- `rotate_expired(session, policies)` — SOLO borra de la DB operativa.
  Se mantiene para compat con tests legacy y para corridas sin archive.
- `rotate_with_archive(op_session, archive_session, policies)` — copia
  a archive + borra de operativa (AR.1). `heartbeat` se borra sin
  archivar.

**Idempotencia:** el `INSERT` al archive usa `INSERT OR IGNORE` para
tolerar reintentos tras fallos parciales. La rotación compromete
primero el archive y después la operativa — si el segundo commit
falla, una re-corrida tratará de archivar las mismas filas (no-op por
el IGNORE) y borrarlas ahora sí.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from modules.db import (
    CandleDaily,
    CandleH1,
    CandleM15,
    Heartbeat,
    Signal,
    SystemLog,
    ValidatorReportRecord,
    now_et,
)
from modules.db.models import Base

# Default del spec §3.7 + AR.4 (validator_reports alineado con system_log)
DEFAULT_RETENTION_POLICIES: Mapping[str, _dt.timedelta] = {
    "signals": _dt.timedelta(days=365),
    "heartbeat": _dt.timedelta(hours=24),
    "system_log": _dt.timedelta(days=30),
    "candles_daily": _dt.timedelta(days=365 * 3),
    "candles_1h": _dt.timedelta(days=182),
    "candles_15m": _dt.timedelta(days=90),
    "validator_reports": _dt.timedelta(days=30),
}

# Mapeo tabla → (modelo, columna timestamp). Centralizado para evitar
# hardcodear nombres en cada función.
_TABLE_MODELS: dict[str, tuple[type[Base], str]] = {
    "signals": (Signal, "compute_timestamp"),
    "heartbeat": (Heartbeat, "ts"),
    "system_log": (SystemLog, "ts"),
    "candles_daily": (CandleDaily, "dt"),
    "candles_1h": (CandleH1, "dt"),
    "candles_15m": (CandleM15, "dt"),
    "validator_reports": (ValidatorReportRecord, "started_at"),
}

# Tablas que NO van al archive (spec §3.7 tabla de retenciones).
_NO_ARCHIVE_TABLES: frozenset[str] = frozenset({"heartbeat"})


async def rotate_expired(
    session: AsyncSession,
    policies: Mapping[str, _dt.timedelta] | None = None,
    *,
    now: _dt.datetime | None = None,
) -> dict[str, int]:
    """Modo legacy: SOLO borra filas vencidas de la DB operativa.

    Se mantiene para compat con tests y escenarios sin archive. Usar
    `rotate_with_archive` cuando haya archive configurado.

    Args:
        session: sesión async abierta (commit lo hace este helper).
        policies: mapping `tabla → timedelta`. Default: políticas del
            spec. Si una tabla no está en `_TABLE_MODELS`, se skippea.
        now: timestamp de referencia para calcular cutoffs. Default
            `now_et()`.

    Returns:
        Dict con la cantidad de filas eliminadas por tabla.
    """
    policies = policies or DEFAULT_RETENTION_POLICIES
    now = now or now_et()
    result: dict[str, int] = {}

    for table, retention in policies.items():
        if table not in _TABLE_MODELS:
            result[table] = 0
            continue
        model, ts_col = _TABLE_MODELS[table]
        cutoff = now - retention
        stmt = delete(model).where(getattr(model, ts_col) < cutoff)
        res = await session.execute(stmt)
        result[table] = res.rowcount or 0

    await session.commit()
    return result


async def rotate_with_archive(
    op_session: AsyncSession,
    archive_session: AsyncSession,
    policies: Mapping[str, _dt.timedelta] | None = None,
    *,
    now: _dt.datetime | None = None,
) -> dict[str, dict[str, int]]:
    """Copia filas vencidas al archive y las borra de operativa.

    Orden: archive INSERT OR IGNORE + commit → op DELETE + commit.
    Si el DELETE falla, una re-corrida re-archiva (no-op) y borra ahora
    sí — invariante: sin pérdida de filas, sin duplicados detectables.

    `heartbeat` se borra sin archivar (spec §3.7).

    Returns:
        `{table: {archived: int, deleted: int}}`. `archived=0` para
        tablas no-archive (heartbeat) y para tablas sin filas vencidas.
    """
    policies = policies or DEFAULT_RETENTION_POLICIES
    now = now or now_et()
    result: dict[str, dict[str, int]] = {}

    # Fase 1: copiar al archive (y commit de archive).
    for table, retention in policies.items():
        if table not in _TABLE_MODELS or table in _NO_ARCHIVE_TABLES:
            continue
        model, ts_col = _TABLE_MODELS[table]
        cutoff = now - retention

        select_stmt = select(model).where(getattr(model, ts_col) < cutoff)
        expired = (await op_session.execute(select_stmt)).scalars().all()

        if not expired:
            result[table] = {"archived": 0, "deleted": 0}
            continue

        rows_as_dicts = [_row_to_dict(model, row) for row in expired]
        insert_stmt = sqlite_insert(model).values(rows_as_dicts)
        insert_stmt = insert_stmt.on_conflict_do_nothing()
        await archive_session.execute(insert_stmt)

        result[table] = {"archived": len(expired), "deleted": 0}

    await archive_session.commit()

    # Fase 2: borrar de op (includes heartbeat).
    for table, retention in policies.items():
        if table not in _TABLE_MODELS:
            continue
        model, ts_col = _TABLE_MODELS[table]
        cutoff = now - retention

        delete_stmt = delete(model).where(getattr(model, ts_col) < cutoff)
        res = await op_session.execute(delete_stmt)
        deleted = res.rowcount or 0
        if table in _NO_ARCHIVE_TABLES:
            result[table] = {"archived": 0, "deleted": deleted}
        else:
            result.setdefault(table, {"archived": 0, "deleted": 0})
            result[table]["deleted"] = deleted

    await op_session.commit()
    return result


async def compute_stats(
    op_session: AsyncSession,
    archive_session: AsyncSession | None,
    policies: Mapping[str, _dt.timedelta] | None = None,
) -> dict[str, dict[str, Any]]:
    """Retorna `{table: {rows_operative, rows_archive, retention_seconds}}`.

    Si `archive_session` es `None`, `rows_archive` se omite (no hay
    archive configurado).
    """
    policies = policies or DEFAULT_RETENTION_POLICIES
    stats: dict[str, dict[str, Any]] = {}
    for table, retention in policies.items():
        if table not in _TABLE_MODELS:
            continue
        model, _ = _TABLE_MODELS[table]
        entry: dict[str, Any] = {
            "rows_operative": await _count_rows(op_session, model),
            "retention_seconds": int(retention.total_seconds()),
            "archives_to_disk": table not in _NO_ARCHIVE_TABLES,
        }
        if archive_session is not None and table not in _NO_ARCHIVE_TABLES:
            entry["rows_archive"] = await _count_rows(archive_session, model)
        else:
            entry["rows_archive"] = None
        stats[table] = entry
    return stats


def _row_to_dict(model: type[Base], row: Any) -> dict[str, Any]:
    """Extrae los valores de las columnas de `row` a un dict plano.

    Evita re-attachear el objeto ORM a otra sesión (mismo objeto no
    puede pertenecer a dos sesiones) — usamos un insert bulk con dicts.
    """
    return {c.key: getattr(row, c.key) for c in model.__table__.columns}


async def _count_rows(session: AsyncSession, model: type[Base]) -> int:
    """`SELECT COUNT(*) FROM <tabla>`."""
    stmt = select(func.count()).select_from(model)
    result = await session.execute(stmt)
    return int(result.scalar() or 0)
