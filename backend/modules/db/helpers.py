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
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.db.models import Heartbeat, Signal, SystemLog

DEFAULT_PAGE_LIMIT: int = 100
MAX_PAGE_LIMIT: int = 500


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
    slot_id: int | None = None,
    from_ts: _dt.datetime | None = None,
    to_ts: _dt.datetime | None = None,
    cursor: int | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> tuple[list[dict], int | None]:
    """Histórico paginado de señales. Pagination cursor-based.

    Orden: por `compute_timestamp` descendente (más reciente primero),
    desempate por `id` descendente. El cursor pagina por `id` para
    evitar problemas con timestamps duplicados.

    Args:
        session: sesión async abierta.
        slot_id: filtro opcional por slot.
        from_ts: filtro inclusivo por `compute_timestamp >= from_ts`.
        to_ts: filtro inclusivo por `compute_timestamp <= to_ts`.
        cursor: `id` del último item de la página anterior. Si se pasa,
            devuelve items con `id < cursor`.
        limit: cantidad máxima (default 100, max 500).

    Returns:
        `(items, next_cursor)`. `next_cursor` es el `id` del último item
        de la página actual si hay más páginas, `None` si no.
    """
    limit = min(max(limit, 1), MAX_PAGE_LIMIT)

    stmt = select(Signal)
    if slot_id is not None:
        stmt = stmt.where(Signal.slot_id == slot_id)
    if from_ts is not None:
        stmt = stmt.where(Signal.compute_timestamp >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(Signal.compute_timestamp <= to_ts)
    if cursor is not None:
        stmt = stmt.where(Signal.id < cursor)

    stmt = stmt.order_by(desc(Signal.id)).limit(limit + 1)
    result = await session.execute(stmt)
    signals = list(result.scalars().all())

    has_more = len(signals) > limit
    items = signals[:limit]
    next_cursor = items[-1].id if has_more and items else None

    return [_signal_to_dict(s) for s in items], next_cursor


async def read_signal_by_id(
    session: AsyncSession,
    signal_id: int,
    *,
    include_snapshot: bool = True,
) -> dict | None:
    """Devuelve la señal con ese `id`, o `None` si no existe.

    Args:
        session: sesión async abierta.
        signal_id: id autogenerado de la señal.
        include_snapshot: si `True` incluye `candles_snapshot_gzip` en
            el dict de retorno (bytes). Default `True` — el endpoint
            público `/signals/{id}` expone el snapshot bajo demanda.
    """
    result = await session.execute(select(Signal).where(Signal.id == signal_id))
    sig = result.scalar_one_or_none()
    if sig is None:
        return None
    return _signal_to_dict(sig, include_snapshot=include_snapshot)


# ═══════════════════════════════════════════════════════════════════════════
# Serialización interna
# ═══════════════════════════════════════════════════════════════════════════


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
