"""Helpers de lectura/escritura sobre la DB.

Esta es la **API pública** del módulo DB — los consumidores (motores
y endpoints de la API) solo importan desde acá. Nunca manipulan
objetos SQLAlchemy directamente (invariante #1 del README).

**Convenciones:**

- Todas las funciones son `async` y reciben un `AsyncSession` explícito
  como primer argumento. No hay global session factory — el owner de la
  sesión decide el ciclo de vida.
- Los writes hacen `session.add()` + `commit()` + devuelven el `id`
  autogenerado. El caller puede agrupar múltiples writes en una sola
  transacción si pasa la misma sesión abierta.
- Los reads devuelven **dicts** (no objetos ORM). Los blobs JSON se
  desempaquetan como claves del dict (`layers`, `ind`, `patterns`,
  etc.), y los timestamps como ISO8601 tz-aware ET.
- Pagination cursor-based: `read_signals_history` toma `cursor` = id
  del último item de la página anterior; devuelve `(items, next_cursor)`.

**Uso típico:**

    factory = make_session_factory(engine)
    async with factory() as session:
        sig_id = await write_signal(session, analyze_output=out, ...)
        latest = await read_signals_latest(session, slot_id=1)
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal

from sqlalchemy import asc, desc, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from modules.db.models import (
    CandleDaily,
    CandleH1,
    CandleM15,
    Heartbeat,
    Signal,
    SystemLog,
    ValidatorReportRecord,
)

ValidatorTrigger = Literal["startup", "manual", "hot_reload", "connectivity"]

DEFAULT_PAGE_LIMIT: int = 100
MAX_PAGE_LIMIT: int = 500

# Literal string para timeframes — evita dependencia circular con
# `engines.data.models.Timeframe`. El caller (Data Engine) hace el mapeo.
CandleTF = Literal["daily", "1h", "15m"]

_CANDLE_MODELS = {
    "daily": CandleDaily,
    "1h": CandleH1,
    "15m": CandleM15,
}


# ═══════════════════════════════════════════════════════════════════════════
# Writes
# ═══════════════════════════════════════════════════════════════════════════


async def write_signal(
    session: AsyncSession,
    *,
    analyze_output: dict,
    candle_timestamp: _dt.datetime,
    slot_id: int | None = None,
    candles_snapshot_gzip: bytes | None = None,
) -> int:
    """Persiste el output de `analyze()` como una `Signal`.

    Mapea las claves del spec §2.3 de `SCORING_ENGINE_SPEC.md` al schema
    híbrido 3 del spec §3.6 de `SCANNER_V5_FEATURE_DECISIONS.md`.

    Args:
        session: sesión async abierta.
        analyze_output: dict retornado por `engines.scoring.analyze()`.
        candle_timestamp: timestamp del candle 15M que disparó el scan
            (tz-aware ET).
        slot_id: id del slot operacional (opcional — puede ser None
            durante tests o scans ad-hoc).
        candles_snapshot_gzip: bytes comprimidos con las velas pasadas
            al motor. Opcional — si se omite queda `None` en DB.

    Returns:
        El `id` autogenerado de la nueva señal.
    """
    sig = Signal(
        candle_timestamp=candle_timestamp,
        engine_version=analyze_output["engine_version"],
        fixture_id=analyze_output["fixture_id"],
        fixture_version=analyze_output["fixture_version"],
        slot_id=slot_id,
        ticker=analyze_output["ticker"],
        score=analyze_output["score"],
        conf=analyze_output["conf"],
        signal=analyze_output["signal"] != "NEUTRAL",
        dir=analyze_output["dir"],
        blocked=bool(analyze_output.get("blocked")),
        error=bool(analyze_output["error"]),
        error_code=analyze_output.get("error_code"),
        layers_json=analyze_output.get("layers", {}),
        ind_json=analyze_output.get("ind", {}),
        patterns_json=analyze_output.get("patterns", []),
        sec_rel_json=analyze_output.get("sec_rel"),
        div_spy_json=analyze_output.get("div_spy"),
        candles_snapshot_gzip=candles_snapshot_gzip,
    )
    session.add(sig)
    await session.commit()
    await session.refresh(sig)
    return sig.id


async def write_heartbeat(
    session: AsyncSession,
    *,
    engine: str,
    status: str,
    memory_pct: float | None = None,
    error_code: str | None = None,
) -> int:
    """Persiste un latido de motor (data/scoring/database/validator).

    Args:
        session: sesión async abierta.
        engine: nombre del motor (`"data"`, `"scoring"`, `"database"`, ...).
        status: `"green"`, `"yellow"`, `"red"` o `"offline"`.
        memory_pct: porcentaje de uso de memoria relativo al límite del
            motor (0-100). `None` si no se reporta.
        error_code: código si el estado es red/offline (ENG-XXX, FIX-XXX).
    """
    hb = Heartbeat(
        engine=engine,
        status=status,
        memory_pct=memory_pct,
        error_code=error_code,
    )
    session.add(hb)
    await session.commit()
    await session.refresh(hb)
    return hb.id


async def write_system_log(
    session: AsyncSession,
    *,
    level: str,
    source: str,
    message: str,
    error_code: str | None = None,
) -> int:
    """Persiste una entrada del log del sistema.

    Args:
        level: `"info"`, `"warning"` o `"error"`.
        source: nombre del módulo que emite (`"scoring_engine"`, ...).
        message: texto libre del evento.
        error_code: código asociado si aplica.
    """
    log = SystemLog(
        level=level,
        source=source,
        message=message,
        error_code=error_code,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    return log.id


async def write_validator_report(
    session: AsyncSession,
    *,
    report: Any,  # modules.validator.ValidatorReport (Pydantic — evito import circular)
    trigger: ValidatorTrigger,
) -> int:
    """Persiste un `ValidatorReport` del módulo validator como row.

    El Pydantic se serializa a dict via `model_dump`; `tests` se
    guarda como lista de dicts en el campo JSON `tests_json`. El
    `overall_status` se lee del property derivado.

    Args:
        session: sesión async.
        report: instancia de `modules.validator.ValidatorReport`.
        trigger: qué disparó la corrida — usado por el Dashboard para
            filtrar ("solo startup", "solo hot-reload", etc.).
    """
    rec = ValidatorReportRecord(
        run_id=report.run_id,
        trigger=trigger,
        started_at=report.started_at,
        finished_at=report.finished_at,
        overall_status=report.overall_status,
        tests_json=[t.model_dump() for t in report.tests],
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec.id


# ═══════════════════════════════════════════════════════════════════════════
# Reads
# ═══════════════════════════════════════════════════════════════════════════


async def read_signals_latest(
    session: AsyncSession,
    *,
    slot_id: int | None = None,
) -> list[dict]:
    """Última señal por slot.

    - Si `slot_id` es `None`, devuelve la última señal emitida por
      **cada** slot (agrupado por `slot_id`). El resultado es una lista
      con 1 entrada por slot operativo.
    - Si `slot_id` se pasa, devuelve solo la última de ese slot (lista
      de 0 o 1 elemento).

    El orden de la lista es por `slot_id` ascendente para determinismo.

    Args:
        session: sesión async abierta.
        slot_id: filtro opcional.

    Returns:
        Lista de dicts en formato público (ver `_signal_to_dict`).
    """
    if slot_id is not None:
        stmt = (
            select(Signal)
            .where(Signal.slot_id == slot_id)
            .order_by(desc(Signal.compute_timestamp))
            .limit(1)
        )
        result = await session.execute(stmt)
        signals = result.scalars().all()
        return [_signal_to_dict(s) for s in signals]

    # Sin filtro: latest por cada slot_id distinto. Hacemos un subquery
    # con MAX(compute_timestamp) agrupado por slot_id.
    from sqlalchemy import func

    subq = (
        select(Signal.slot_id, func.max(Signal.compute_timestamp).label("max_ts"))
        .where(Signal.slot_id.is_not(None))
        .group_by(Signal.slot_id)
        .subquery()
    )
    stmt = (
        select(Signal)
        .join(
            subq,
            (Signal.slot_id == subq.c.slot_id)
            & (Signal.compute_timestamp == subq.c.max_ts),
        )
        .order_by(Signal.slot_id)
    )
    result = await session.execute(stmt)
    signals = result.scalars().all()
    return [_signal_to_dict(s) for s in signals]


async def read_signals_history(
    session: AsyncSession,
    *,
    archive_session: AsyncSession | None = None,
    slot_id: int | None = None,
    from_ts: _dt.datetime | None = None,
    to_ts: _dt.datetime | None = None,
    cursor: int | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[dict], int | None]:
    """Histórico paginado de señales. Pagination cursor-based.

    Orden: por `id` descendente (equivalente a `compute_timestamp` desc
    porque `id` es autoincremental). El cursor pagina por `id`.

    **Transparent reads (Opción X, spec §3.7):** si `archive_session`
    se pasa, la query se corre sobre ambas DBs y los resultados se
    mergean por `id` desc antes de paginar. El frontend no necesita
    saber dónde vive cada fila — solo consulta este endpoint.

    Args:
        session: sesión async sobre la DB operativa.
        archive_session: sesión async opcional sobre el archive. Si es
            `None`, solo se mira la DB operativa.
        slot_id: filtro opcional por slot.
        from_ts: filtro inclusivo por `compute_timestamp >= from_ts`.
        to_ts: filtro inclusivo por `compute_timestamp <= to_ts`.
        cursor: `id` del último item de la página anterior. Si se pasa,
            devuelve items con `id < cursor`.
        limit: cantidad máxima (default 100, max 500).

    Returns:
        `(items, next_cursor)`. `next_cursor` es el `id` del último item
        si hay más páginas, `None` si no.
    """
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)

    def _build_stmt():
        stmt = select(Signal)
        if slot_id is not None:
            stmt = stmt.where(Signal.slot_id == slot_id)
        if from_ts is not None:
            stmt = stmt.where(Signal.compute_timestamp >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(Signal.compute_timestamp <= to_ts)
        if cursor is not None:
            stmt = stmt.where(Signal.id < cursor)
        return stmt.order_by(desc(Signal.id)).limit(limit + 1)

    op_rows = list((await session.execute(_build_stmt())).scalars().all())

    if archive_session is None:
        all_rows = op_rows
    else:
        ar_rows = list(
            (await archive_session.execute(_build_stmt())).scalars().all(),
        )
        # Dedup defensivo por id (si la rotación dejó la misma fila en
        # ambas DBs transitoriamente). op gana sobre archive.
        seen: set[int] = set()
        merged: list[Signal] = []
        for r in sorted(op_rows + ar_rows, key=lambda s: s.id, reverse=True):
            if r.id in seen:
                continue
            seen.add(r.id)
            merged.append(r)
        all_rows = merged[: limit + 1]

    has_more = len(all_rows) > limit
    items = all_rows[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return [_signal_to_dict(s) for s in items], next_cursor


async def read_signal_by_id(
    session: AsyncSession,
    signal_id: int,
    *,
    archive_session: AsyncSession | None = None,
    include_snapshot: bool = True,
) -> dict | None:
    """Devuelve la señal con ese `id`, o `None` si no existe.

    **Transparent reads:** busca primero en `session` (operativa). Si
    no está y hay `archive_session`, busca en el archive.

    Args:
        session: sesión async sobre la DB operativa.
        signal_id: id autogenerado de la señal.
        archive_session: sesión sobre archive. Si `None` (o la fila ya
            está en op), no se consulta.
        include_snapshot: si `True` incluye `candles_snapshot_gzip`.
    """
    result = await session.execute(select(Signal).where(Signal.id == signal_id))
    sig = result.scalar_one_or_none()
    if sig is not None:
        return _signal_to_dict(sig, include_snapshot=include_snapshot)

    if archive_session is None:
        return None

    result = await archive_session.execute(
        select(Signal).where(Signal.id == signal_id),
    )
    sig = result.scalar_one_or_none()
    if sig is None:
        return None
    return _signal_to_dict(sig, include_snapshot=include_snapshot)


# ═══════════════════════════════════════════════════════════════════════════
# Serialización interna
# ═══════════════════════════════════════════════════════════════════════════


async def read_validator_reports_latest(
    session: AsyncSession,
    *,
    archive_session: AsyncSession | None = None,
) -> dict | None:
    """Último reporte del Validator (o `None` si no hay ninguno).

    Transparent read op + archive — el último generalmente vive en op,
    pero si la operativa se vació por rotación el fallback a archive
    garantiza que el Dashboard siga mostrando algo.
    """
    stmt = (
        select(ValidatorReportRecord)
        .order_by(desc(ValidatorReportRecord.started_at))
        .limit(1)
    )
    op_row = (await session.execute(stmt)).scalar_one_or_none()
    if op_row is not None:
        return _validator_report_to_dict(op_row)
    if archive_session is None:
        return None
    ar_row = (await archive_session.execute(stmt)).scalar_one_or_none()
    if ar_row is None:
        return None
    return _validator_report_to_dict(ar_row)


async def read_validator_reports_history(
    session: AsyncSession,
    *,
    archive_session: AsyncSession | None = None,
    trigger: ValidatorTrigger | None = None,
    overall_status: str | None = None,
    cursor: int | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[dict], int | None]:
    """Histórico paginado de reportes. Cursor por `id` desc.

    Transparent read igual que `read_signals_history`.
    """
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)

    def _build_stmt():
        stmt = select(ValidatorReportRecord)
        if trigger is not None:
            stmt = stmt.where(ValidatorReportRecord.trigger == trigger)
        if overall_status is not None:
            stmt = stmt.where(
                ValidatorReportRecord.overall_status == overall_status,
            )
        if cursor is not None:
            stmt = stmt.where(ValidatorReportRecord.id < cursor)
        return stmt.order_by(desc(ValidatorReportRecord.id)).limit(limit + 1)

    op_rows = list((await session.execute(_build_stmt())).scalars().all())
    if archive_session is None:
        all_rows = op_rows
    else:
        ar_rows = list(
            (await archive_session.execute(_build_stmt())).scalars().all(),
        )
        seen: set[int] = set()
        merged = []
        for r in sorted(op_rows + ar_rows, key=lambda x: x.id, reverse=True):
            if r.id in seen:
                continue
            seen.add(r.id)
            merged.append(r)
        all_rows = merged[: limit + 1]

    has_more = len(all_rows) > limit
    items = all_rows[:limit]
    next_cursor = items[-1].id if has_more and items else None
    return [_validator_report_to_dict(r) for r in items], next_cursor


async def read_validator_report_by_id(
    session: AsyncSession,
    report_id: int,
    *,
    archive_session: AsyncSession | None = None,
) -> dict | None:
    """Reporte completo por id. Transparent read (op → archive)."""
    result = await session.execute(
        select(ValidatorReportRecord).where(ValidatorReportRecord.id == report_id),
    )
    rec = result.scalar_one_or_none()
    if rec is not None:
        return _validator_report_to_dict(rec)
    if archive_session is None:
        return None
    result = await archive_session.execute(
        select(ValidatorReportRecord).where(ValidatorReportRecord.id == report_id),
    )
    rec = result.scalar_one_or_none()
    if rec is None:
        return None
    return _validator_report_to_dict(rec)


def _validator_report_to_dict(rec: ValidatorReportRecord) -> dict[str, Any]:
    return {
        "id": rec.id,
        "run_id": rec.run_id,
        "trigger": rec.trigger,
        "started_at": rec.started_at.isoformat(),
        "finished_at": rec.finished_at.isoformat() if rec.finished_at else None,
        "overall_status": rec.overall_status,
        "tests": rec.tests_json,
    }


def _signal_to_dict(sig: Signal, *, include_snapshot: bool = False) -> dict[str, Any]:
    """Convierte un `Signal` ORM a dict serializable.

    Los timestamps se emiten como ISO8601 tz-aware ET (el caller los
    puede parsear con `datetime.fromisoformat()`). Los blobs JSON se
    renombran sin el sufijo `_json` para el formato público.
    """
    d: dict[str, Any] = {
        "id": sig.id,
        "candle_timestamp": sig.candle_timestamp.isoformat(),
        "compute_timestamp": sig.compute_timestamp.isoformat(),
        "engine_version": sig.engine_version,
        "fixture_id": sig.fixture_id,
        "fixture_version": sig.fixture_version,
        "slot_id": sig.slot_id,
        "ticker": sig.ticker,
        "score": sig.score,
        "conf": sig.conf,
        "signal": sig.signal,
        "dir": sig.dir,
        "blocked": sig.blocked,
        "error": sig.error,
        "error_code": sig.error_code,
        "layers": sig.layers_json,
        "ind": sig.ind_json,
        "patterns": sig.patterns_json,
        "sec_rel": sig.sec_rel_json,
        "div_spy": sig.div_spy_json,
    }
    if include_snapshot:
        d["candles_snapshot_gzip"] = sig.candles_snapshot_gzip
    return d


# ═══════════════════════════════════════════════════════════════════════════
# Candles — cache local de velas por timeframe
# ═══════════════════════════════════════════════════════════════════════════


async def write_candles_batch(
    session: AsyncSession,
    *,
    timeframe: CandleTF,
    ticker: str,
    candles: list[dict[str, Any]],
) -> int:
    """UPSERT de un batch de velas al TF correspondiente.

    Idempotente por PK `(ticker, dt)` — si una vela ya existe con el
    mismo `dt`, se sobrescribe con los valores nuevos (típicamente
    velas del día actual que todavía están cerrándose).

    Args:
        session: sesión async abierta.
        timeframe: `"daily"`, `"1h"` o `"15m"`.
        ticker: símbolo.
        candles: lista de dicts con `dt, o, h, l, c, v`. `dt` debe ser
            `datetime` tz-aware ET (ADR-0002) — el type decorator
            `ETDateTime` normaliza si viene en otra zona.

    Returns:
        Cantidad de filas procesadas (puede ser < len(candles) si hay
        duplicados exactos, pero típicamente = len(candles)).
    """
    if not candles:
        return 0

    model = _CANDLE_MODELS[timeframe]
    rows = [
        {
            "ticker": ticker,
            "dt": c["dt"],
            "o": c["o"],
            "h": c["h"],
            "l": c["l"],
            "c": c["c"],
            "v": c["v"],
        }
        for c in candles
    ]
    stmt = sqlite_insert(model).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[model.ticker, model.dt],
        set_={
            "o": stmt.excluded.o,
            "h": stmt.excluded.h,
            "l": stmt.excluded.l,
            "c": stmt.excluded.c,
            "v": stmt.excluded.v,
        },
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or len(rows)


async def read_candles_window(
    session: AsyncSession,
    *,
    timeframe: CandleTF,
    ticker: str,
    archive_session: AsyncSession | None = None,
    from_ts: _dt.datetime | None = None,
    to_ts: _dt.datetime | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Lee velas ordenadas por `dt` ascendente dentro del rango.

    **Transparent reads (Opción X):** si `archive_session` se pasa, la
    query se corre sobre ambas DBs y los resultados se mergean por
    `dt` asc (dedup por `dt` — op gana).

    Args:
        session: sesión async sobre la DB operativa.
        timeframe: `"daily"`, `"1h"` o `"15m"`.
        ticker: símbolo.
        archive_session: sesión sobre el archive. `None` = solo op.
        from_ts: inclusivo. `None` = sin límite inferior.
        to_ts: inclusivo. `None` = sin límite superior.
        limit: cantidad máxima desde el final (las más recientes).
            Si `None`, trae todo el rango.

    Returns:
        Lista de dicts `{dt, o, h, l, c, v}` ordenada por `dt` asc.
    """
    model = _CANDLE_MODELS[timeframe]

    def _build_stmt():
        stmt = select(model).where(model.ticker == ticker)
        if from_ts is not None:
            stmt = stmt.where(model.dt >= from_ts)
        if to_ts is not None:
            stmt = stmt.where(model.dt <= to_ts)
        if limit is not None:
            return stmt.order_by(desc(model.dt)).limit(limit)
        return stmt.order_by(asc(model.dt))

    op_rows = list((await session.execute(_build_stmt())).scalars().all())

    if archive_session is None:
        rows = op_rows
    else:
        ar_rows = list(
            (await archive_session.execute(_build_stmt())).scalars().all(),
        )
        # Dedup por (ticker, dt) — op gana sobre archive.
        seen: set[_dt.datetime] = set()
        merged = []
        for r in sorted(op_rows + ar_rows, key=lambda c: c.dt, reverse=True):
            if r.dt in seen:
                continue
            seen.add(r.dt)
            merged.append(r)
        rows = merged[:limit] if limit is not None else merged

    if limit is not None:
        # Los más recientes ya vienen ordenados desc — invertimos a asc.
        rows = sorted(rows, key=lambda c: c.dt)
    else:
        rows = sorted(rows, key=lambda c: c.dt)

    return [_candle_to_dict(r) for r in rows]


async def latest_candle_dt(
    session: AsyncSession,
    *,
    timeframe: CandleTF,
    ticker: str,
) -> _dt.datetime | None:
    """Devuelve el `dt` de la vela más reciente del TF, o `None`.

    Usado por el Data Engine para calcular el gap entre DB y provider
    (ADR-0003: consultar DB antes de fetch).
    """
    model = _CANDLE_MODELS[timeframe]
    stmt = select(func.max(model.dt)).where(model.ticker == ticker)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _candle_to_dict(row: Any) -> dict[str, Any]:
    """ORM → dict serializable. El `dt` queda tz-aware ET (del decorator)."""
    return {
        "dt": row.dt,
        "o": row.o,
        "h": row.h,
        "l": row.l,
        "c": row.c,
        "v": row.v,
    }
