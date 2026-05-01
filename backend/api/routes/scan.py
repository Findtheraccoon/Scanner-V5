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

import asyncio
import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_session
from engines.data.scan_loop import broadcast_api_usage
from modules.db import ET_TZ
from modules.signal_pipeline import scan_and_emit

router = APIRouter(prefix="/scan", tags=["scan"])


def _get_running_event(request: Request) -> asyncio.Event:
    """Recupera el `auto_scan_running` event desde `app.state`.

    Si el app no tiene scan loop activo (e.g. arrancado sin keys de
    TwelveData), retorna 503 — no hay nada que pausar/resumir.
    """
    running = getattr(request.app.state, "auto_scan_running", None)
    if running is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auto-scan loop no está activo (data engine no inicializado)",
        )
    return running


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


@router.post("/slot/{slot_id}")
async def scan_slot(
    slot_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _token: str = Depends(require_auth),
) -> dict:
    """One-shot scan de un slot operativo del registry.

    BUG-015: el botón "scan" del Cockpit antes pegaba `/scan/manual`
    con body vacío y siempre fallaba 422 (ese endpoint exige ticker +
    fixture + 3 series de candles). Acá el backend resuelve todo:

    1. Lee el slot del `registry_runtime` (404 si no existe; 409 si
       no está OPERATIVE — disabled o degraded no scanean).
    2. Toma la fixture parseada del slot (fuente de verdad — la misma
       que usa el auto_scan_loop).
    3. Pide al `DataEngine` un fetch fresco de candles (DB-first,
       provider fallback, retry nivel 1 — ADR-0004).
    4. Corre `scan_and_emit` con timestamp = ahora ET. La señal se
       persiste y se broadcast por WS igual que en el ciclo automático.

    Pre-requisitos: scan_loop=real al startup (data_engine cableado),
    o KeyPool+TDClient bootstrapeados via `PUT /config/twelvedata_keys`
    + slot operativo asignado via `PATCH /slots/{id}`.
    """
    runtime = getattr(request.app.state, "registry_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registry runtime no inicializado",
        )
    slot_dict = await runtime.get_slot(slot_id)
    if slot_dict is None:
        raise HTTPException(404, f"Slot {slot_id} not found")
    if slot_dict["status"] not in ("active", "warming_up"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Slot {slot_id} no está scaneable (status="
                f"{slot_dict['status']!r}). Habilítalo desde Box 4."
            ),
        )

    data_engine = getattr(request.app.state, "data_engine", None)
    if data_engine is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Data Engine no inicializado. El scan manual requiere TD "
                "keys cargadas (Box 3 o env var SCANNER_TWELVEDATA_KEYS)."
            ),
        )

    fixture_dict = await runtime.get_fixture_dict(slot_id)
    if fixture_dict is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Slot {slot_id} no tiene fixture parseada disponible "
                "(¿degraded?)."
            ),
        )

    ticker: str = slot_dict["ticker"]
    inputs = await data_engine.fetch_for_scan(ticker)
    if inputs is None:
        # BUG-021: aunque el fetch falle, los intentos hechos consumieron
        # credits del KeyPool (ej. 429 rate limit, fail integrity). Emitimos
        # api_usage.tick antes de devolver el 502 para que la UI muestre
        # el consumo y el usuario entienda por qué falló.
        try:
            await broadcast_api_usage(request.app.state.broadcaster, data_engine)
        except Exception:
            logger.exception("broadcast_api_usage failed in error path")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"fetch_for_scan({ticker!r}) falló integrity tras retry. "
                "Reintentá en unos segundos o revisá las TD keys."
            ),
        )

    candle_ts = _ensure_et(_dt.datetime.now())
    sim_dt = candle_ts.strftime("%Y-%m-%d %H:%M:%S")
    sim_date = candle_ts.strftime("%Y-%m-%d")
    broadcaster = request.app.state.broadcaster
    out = await scan_and_emit(
        session=session,
        broadcaster=broadcaster,
        candle_timestamp=candle_ts,
        slot_id=slot_id,
        ticker=ticker,
        candles_daily=inputs["candles_daily"],
        candles_1h=inputs["candles_1h"],
        candles_15m=inputs["candles_15m"],
        fixture=fixture_dict,
        spy_daily=inputs.get("spy_daily"),
        bench_daily=inputs.get("spy_daily"),  # MVP: bench = SPY (mismo trato que scan_loop)
        sim_datetime=sim_dt,
        sim_date=sim_date,
    )
    # BUG-021: tras un scan manual emitimos api_usage.tick por cada key
    # del pool — el banner de 5 barras del Cockpit se actualiza con los
    # créditos consumidos (igual que tras un ciclo del auto_scan_loop).
    # Sin esto, el usuario no ve evidencia visual de que el scan haya
    # pegado a TwelveData.
    await broadcast_api_usage(broadcaster, data_engine)
    # Adjuntamos un resumen de la fetch al output para que la UI muestre
    # cuántas velas trajo + timestamp del último candle.
    fetched_at = inputs.get("fetched_at")
    out["fetch_meta"] = {
        "fetched_at": (
            fetched_at.isoformat()
            if hasattr(fetched_at, "isoformat") else str(fetched_at)
        ),
        "candles_daily_n": len(inputs["candles_daily"]),
        "candles_1h_n": len(inputs["candles_1h"]),
        "candles_15m_n": len(inputs["candles_15m"]),
    }
    return out


@router.get("/auto/status")
async def auto_scan_status(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Retorna `{paused: bool}` con el estado del auto-scan loop.

    Útil para que el frontend sincronice el toggle AUTO al cargar la
    página, sin tener que esperar al primer `engine.status` por WS.
    """
    running = _get_running_event(request)
    return {"paused": not running.is_set()}


@router.post("/auto/pause")
async def auto_scan_pause(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Pausa el auto-scan loop. Idempotente — pausar dos veces no falla.

    El loop bloquea en su próximo `await running.wait()` y emite
    `engine.status={status: "paused"}` por WS para que el frontend
    refleje el cambio en otros clientes.
    """
    running = _get_running_event(request)
    running.clear()
    return {"paused": True}


@router.post("/auto/resume")
async def auto_scan_resume(
    request: Request,
    _token: str = Depends(require_auth),
) -> dict:
    """Reanuda el auto-scan loop. Idempotente."""
    running = _get_running_event(request)
    running.set()
    return {"paused": False}
