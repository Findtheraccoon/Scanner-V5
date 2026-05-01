"""Endpoints REST de signals (`/api/v1/signals/...`).

Endpoints:

- `GET /api/v1/signals/latest?slot_id=N?` — última señal por slot.
  Sin `slot_id` → lista con la última de cada slot. Con `slot_id` →
  lista de 0 o 1 elemento.
- `GET /api/v1/signals/history?slot_id&from&to&cursor&limit` —
  histórico paginado cursor-based. Default limit=100, max=500.
- `GET /api/v1/signals/{id}` — señal completa. Si tiene snapshot, se
  devuelve como `candles_snapshot_gzip_b64` (base64) para JSON-safe.

**Query params temporales (`from`, `to`):** ISO8601. Si viene naive
se asume ET. Si viene con offset, se normaliza a ET (ADR-0002).

**Auth:** todos requieren Bearer token via `require_auth`.
"""

from __future__ import annotations

import base64
import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_archive_session, get_session
from modules.db import (
    DEFAULT_PAGE_LIMIT,
    ET_TZ,
    MAX_PAGE_LIMIT,
    read_candles_window,
    read_signal_by_id,
    read_signals_history,
    read_signals_latest,
)
from modules.fixtures.metrics_lookup import get_band_wr_pct
from modules.signal_pipeline import build_chat_format

router = APIRouter(prefix="/signals", tags=["signals"])


async def _enrich_with_last_price(
    sig: dict,
    session: AsyncSession,
    archive_session: AsyncSession | None = None,
) -> None:
    """BUG-024 cierre real: cuando la signal está blocked/NEUTRAL, el
    bloque `ind` puede venir vacío y el chat_format pierde el precio.
    Para que el usuario pueda comparar contra su gráfico, leemos el
    último cierre 15m del ticker y lo inyectamos en `ind.price` si
    no estaba.
    """
    ind = sig.get("ind") or {}
    if isinstance(ind.get("price"), (int, float)):
        return
    ticker = sig.get("ticker")
    if not ticker:
        return
    try:
        rows = await read_candles_window(
            session,
            timeframe="15m",
            ticker=ticker,
            archive_session=archive_session,
            limit=1,
        )
    except Exception:
        return
    if not rows:
        return
    last = rows[-1]
    close = last.get("c")
    if isinstance(close, (int, float)):
        ind = dict(ind)
        ind["price"] = float(close)
        sig["ind"] = ind


def _augment_signal_sync(request: Request, sig: dict) -> dict:
    """Inyecta `wr_pct` y regenera `chat_format`. Versión sincrónica
    sin price enrichment — usada cuando ya tenemos `ind.price` o
    cuando no hay session disponible.
    """
    # WR pct lookup
    fixtures_dir = getattr(request.app.state, "fixtures_dir", None)
    fid = sig.get("fixture_id")
    band = sig.get("conf")
    if fixtures_dir is not None and fid:
        sig["wr_pct"] = get_band_wr_pct(fixtures_dir, fid, band)

    # chat_format regen
    candle_ts_str = sig.get("candle_timestamp")
    if candle_ts_str:
        try:
            ts = _dt.datetime.fromisoformat(candle_ts_str)
            sig["chat_format"] = build_chat_format(sig, candle_timestamp=ts)
        except (ValueError, TypeError):
            pass
    return sig


async def _augment_signal(
    request: Request,
    sig: dict,
    session: AsyncSession,
    archive_session: AsyncSession | None = None,
) -> dict:
    """Inyecta `wr_pct` + `last_price` (en ind.price si faltaba) +
    regenera `chat_format` desde los datos persistidos.

    BUG-023: WR del backtest training. Vive en `<fixture>.metrics.json`
    y no en la signal persistida.

    BUG-024: el `chat_format` solo se generaba para el broadcast WS
    `signal.new`, no se persistía. Para signals BLOCKED/NEUTRAL el
    bloque `ind` viene vacío — leemos la última 15m del ticker para
    que el usuario tenga un precio de referencia comparable contra
    su gráfico real.
    """
    await _enrich_with_last_price(sig, session, archive_session)
    return _augment_signal_sync(request, sig)


def _ensure_et(ts: _dt.datetime | None) -> _dt.datetime | None:
    """Normaliza un datetime a ET tz-aware (ADR-0002)."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ET_TZ)
    return ts.astimezone(ET_TZ)


@router.get("/latest")
async def signals_latest(
    request: Request,
    slot_id: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> list[dict]:
    """Última señal por slot (o de un slot específico)."""
    items = await read_signals_latest(session, slot_id=slot_id)
    return [
        await _augment_signal(request, s, session, archive_session)
        for s in items
    ]


@router.get("/history")
async def signals_history(
    request: Request,
    slot_id: int | None = Query(None, ge=1),
    from_ts: _dt.datetime | None = Query(None, alias="from"),
    to_ts: _dt.datetime | None = Query(None, alias="to"),
    cursor: int | None = Query(None, ge=1),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Histórico paginado cursor-based con lectura transparente del
    archive si está configurado (spec §3.7 Opción X).

    Response shape:
        {
          "items": [signal_dict, ...],
          "next_cursor": int | null
        }
    """
    items, next_cursor = await read_signals_history(
        session,
        archive_session=archive_session,
        slot_id=slot_id,
        from_ts=_ensure_et(from_ts),
        to_ts=_ensure_et(to_ts),
        cursor=cursor,
        limit=limit,
    )
    augmented = [
        await _augment_signal(request, s, session, archive_session)
        for s in items
    ]
    return {"items": augmented, "next_cursor": next_cursor}


@router.get("/{signal_id}")
async def signal_by_id(
    signal_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Señal completa con snapshot de inputs opcional (base64). Busca
    primero en op, luego en archive (transparent read).

    404 si el `id` no existe en ninguna.
    """
    sig = await read_signal_by_id(
        session, signal_id,
        archive_session=archive_session, include_snapshot=True,
    )
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    # El snapshot en bytes no es JSON-friendly — lo encodeamos en base64.
    snapshot = sig.pop("candles_snapshot_gzip", None)
    if snapshot is not None:
        sig["candles_snapshot_gzip_b64"] = base64.b64encode(snapshot).decode("ascii")
    else:
        sig["candles_snapshot_gzip_b64"] = None
    return await _augment_signal(request, sig, session, archive_session)
