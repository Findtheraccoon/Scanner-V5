"""Endpoint manual de scan — `POST /api/v1/scan/manual`.

Dispara un scan ad-hoc del Scoring Engine. Útil para:

- Testing local del stack sin Data Engine real.
- Button "Ejecutar scan" del Cockpit (spec §3.1, ciclo MANUAL).
- Debugging post-hoc: re-correr una señal vieja con velas específicas.

**Auth:** Bearer token.

**Request body:** JSON con los mismos inputs que `analyze()`:

    {
      "ticker": "QQQ",
      "slot_id": 1,                        # opcional
      "fixture": { ... },                  # JSON del fixture completo
      "candles_daily": [ {dt,o,h,l,c,v}, ... ],
      "candles_1h":    [ ... ],
      "candles_15m":   [ ... ],
      "spy_daily":     [ ... ],            # opcional
      "bench_daily":   [ ... ],            # opcional
      "candle_timestamp": "2026-04-22T10:30:00-04:00",
      "sim_datetime": "2026-04-22 10:30:00", # opcional
      "sim_date":     "2026-04-22"           # opcional
    }

**Response:** output de `scan_and_emit()` — el output de `analyze()`
más la clave `id` del registro persistido en `signals`.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_session
from modules.db import ET_TZ
from modules.signal_pipeline import scan_and_emit

router = APIRouter(prefix="/scan", tags=["scan"])


class ScanManualRequest(BaseModel):
    """Inputs del scan manual — validados por Pydantic."""

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(..., min_length=1, max_length=10)
    slot_id: int | None = Field(default=None, ge=1)
    fixture: dict
    candles_daily: list[dict]
    candles_1h: list[dict]
    candles_15m: list[dict]
    candle_timestamp: _dt.datetime
    spy_daily: list[dict] | None = None
    bench_daily: list[dict] | None = None
    sim_datetime: str | None = None
    sim_date: str | None = None


def _ensure_et(ts: _dt.datetime) -> _dt.datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ET_TZ)
    return ts.astimezone(ET_TZ)


@router.post("/manual")
async def scan_manual(
    req: ScanManualRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Corre `scan_and_emit()` con los inputs del body.

    Retorna el output de `analyze()` enriquecido con `id` (del registro
    en `signals`). Incluso outputs NEUTRAL/error se persisten en DB para
    auditoría; solo los SETUP/REVISAR se emiten por el WebSocket.
    """
    broadcaster = request.app.state.broadcaster
    candle_ts = _ensure_et(req.candle_timestamp)
    return await scan_and_emit(
        session=session,
        broadcaster=broadcaster,
        candle_timestamp=candle_ts,
        slot_id=req.slot_id,
        ticker=req.ticker,
        candles_daily=req.candles_daily,
        candles_1h=req.candles_1h,
        candles_15m=req.candles_15m,
        fixture=req.fixture,
        spy_daily=req.spy_daily,
        bench_daily=req.bench_daily,
        sim_datetime=req.sim_datetime,
        sim_date=req.sim_date,
    )
