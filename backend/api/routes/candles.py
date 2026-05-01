"""Endpoint de lectura de velas — `GET /api/v1/candles/{ticker}`.

Sirve las últimas N velas de un timeframe específico desde la DB
(operativa + archive merge si está configurado). Usado por el chart
del Cockpit para renderizar el OHLC del slot seleccionado.

**Auth:** Bearer token.

**Query params:**

- `tf`: `"daily" | "1h" | "15m"` (default `"15m"`).
- `n`: cantidad de velas más recientes a traer. 1..500 (default 50).

**Response shape:**

    {
      "ticker": "QQQ",
      "tf": "15m",
      "candles": [{"dt": "2026-...", "o": ..., "h": ..., "l": ..., "c": ..., "v": ...}, ...]
    }

Las velas vienen ordenadas por `dt` ascendente (más vieja primero —
listo para feedear a un chart de izquierda a derecha).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import require_auth
from api.deps import get_archive_session, get_session
from modules.db import read_candles_window

router = APIRouter(prefix="/candles", tags=["candles"])


@router.get("/{ticker}")
async def get_candles(
    ticker: str,
    tf: Literal["daily", "1h", "15m"] = Query("15m"),
    n: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
    archive_session: AsyncSession | None = Depends(get_archive_session),
    _token: str = Depends(require_auth),
) -> dict:
    """Últimas `n` velas del timeframe `tf` para `ticker`.

    Usa transparent reads sobre op + archive cuando archive_session
    está disponible. Devuelve dicts compatibles con el resto del
    pipeline (`{dt, o, h, l, c, v}`).
    """
    rows = await read_candles_window(
        session,
        timeframe=tf,
        ticker=ticker.upper(),
        archive_session=archive_session,
        limit=n,
    )
    # `read_candles_window` con `limit` aplica `ORDER BY dt DESC LIMIT n`
    # para tomar las más recientes — pero sin merge garantizado de orden.
    # El response final se ordena ASC para feedear al chart left-to-right.
    rows_sorted = sorted(rows, key=lambda r: r["dt"])
    return {"ticker": ticker.upper(), "tf": tf, "candles": rows_sorted}
