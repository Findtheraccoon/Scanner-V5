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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_session
from modules.db import (
    DEFAULT_PAGE_LIMIT,
    ET_TZ,
    MAX_PAGE_LIMIT,
    read_signal_by_id,
    read_signals_history,
    read_signals_latest,
)

router = APIRouter(prefix="/signals", tags=["signals"])


def _ensure_et(ts: _dt.datetime | None) -> _dt.datetime | None:
    """Normaliza un datetime a ET tz-aware (ADR-0002)."""
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ET_TZ)
    return ts.astimezone(ET_TZ)


@router.get("/latest")
async def signals_latest(
    slot_id: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> list[dict]:
    """Última señal por slot (o de un slot específico)."""
    return await read_signals_latest(session, slot_id=slot_id)


@router.get("/history")
async def signals_history(
    slot_id: int | None = Query(None, ge=1),
    from_ts: _dt.datetime | None = Query(None, alias="from"),
    to_ts: _dt.datetime | None = Query(None, alias="to"),
    cursor: int | None = Query(None, ge=1),
    limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Histórico paginado cursor-based.

    Response shape:
        {
          "items": [signal_dict, ...],
          "next_cursor": int | null
        }
    """
    items, next_cursor = await read_signals_history(
        session,
        slot_id=slot_id,
        from_ts=_ensure_et(from_ts),
        to_ts=_ensure_et(to_ts),
        cursor=cursor,
        limit=limit,
    )
    return {"items": items, "next_cursor": next_cursor}


@router.get("/{signal_id}")
async def signal_by_id(
    signal_id: int,
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Señal completa con snapshot de inputs opcional (base64).

    404 si el `id` no existe.
    """
    sig = await read_signal_by_id(session, signal_id, include_snapshot=True)
    if sig is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    # El snapshot en bytes no es JSON-friendly — lo encodeamos en base64.
    snapshot = sig.pop("candles_snapshot_gzip", None)
    if snapshot is not None:
        sig["candles_snapshot_gzip_b64"] = base64.b64encode(snapshot).decode("ascii")
    else:
        sig["candles_snapshot_gzip_b64"] = None
    return sig
