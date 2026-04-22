"""Scan loop AUTO — detecta cierre de vela 15M + dispara scans por slot.

Reemplaza el `auto_scheduler_worker` stub de D.3 con la lógica real del
spec §3.1:

    detectar cierre 15M → delay 3s → para cada slot operativo:
        DataEngine.fetch_for_scan() → scan_and_emit()

**Orquestación:**

- Un único loop que se levanta 1 vez por cierre de vela 15M (9:45,
  10:00, ..., 16:00 ET).
- Por ciclo, `asyncio.gather` paralelo por slot — un fetch lento no
  bloquea a los otros. Fallos individuales no rompen el loop.
- Al cerrar el mercado, el loop entra en modo espera (sleep largo,
  reanuda cuando abre).

**Testing:** `test_interval_s` bypasea la lógica de market calendar —
dispara cada N segundos para que tests determinísticos puedan
verificar el ciclo sin esperar al reloj.
"""

from __future__ import annotations

import asyncio
import datetime as _dt

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from api.broadcaster import Broadcaster
from api.events import EVENT_API_USAGE_TICK, EVENT_ENGINE_STATUS
from engines.data.engine import DataEngine
from engines.data.market_calendar import is_market_open
from modules.db import now_et
from modules.signal_pipeline import scan_and_emit

DEFAULT_DELAY_AFTER_CLOSE_S: float = 3.0
DEFAULT_MARKET_CLOSED_SLEEP_S: float = 60.0


async def auto_scan_loop(
    *,
    data_engine: DataEngine,
    session_factory: async_sessionmaker,
    broadcaster: Broadcaster,
    slot_tickers: list[str],
    fixture: dict,
    delay_after_close_s: float = DEFAULT_DELAY_AFTER_CLOSE_S,
    test_interval_s: float | None = None,
) -> None:
    """Loop infinito: detecta cierre 15M y dispara scan por cada slot.

    Args:
        data_engine: orquestrador del Data Engine.
        session_factory: factory de sesiones DB.
        broadcaster: broadcaster para emitir `signal.new` y
            `engine.status`.
        slot_tickers: tickers de los slots operativos en orden. El slot
            con `slot_id=1` es el primero, `2` el segundo, etc.
        fixture: dict del fixture canonical usado por todos los slots
            (MVP — en fase Slot Registry cada slot tiene su fixture).
        delay_after_close_s: segundos de espera post-cierre para que
            el provider consolide (spec §3.1, default 3s).
        test_interval_s: si se pasa, bypasea market calendar — dispara
            un ciclo cada `test_interval_s` segundos. Útil para tests.
    """
    logger.info(
        f"Auto-scan loop started — slots={slot_tickers} "
        f"delay_after_close={delay_after_close_s}s "
        f"mode={'TEST' if test_interval_s is not None else 'PRODUCTION'}",
    )
    try:
        while True:
            if test_interval_s is not None:
                await asyncio.sleep(test_interval_s)
                candle_ts = now_et()
            else:
                candle_ts = await _wait_for_next_close(delay_after_close_s)
                if candle_ts is None:
                    # Mercado cerrado — sleep corto y reintenta
                    await asyncio.sleep(DEFAULT_MARKET_CLOSED_SLEEP_S)
                    continue

            try:
                await _run_scan_cycle(
                    data_engine=data_engine,
                    session_factory=session_factory,
                    broadcaster=broadcaster,
                    slot_tickers=slot_tickers,
                    fixture=fixture,
                    candle_timestamp=candle_ts,
                )
            except Exception:
                logger.exception("Scan cycle failed unexpectedly")
    except asyncio.CancelledError:
        logger.info("Auto-scan loop cancelled")
        raise


async def _wait_for_next_close(delay_after_close_s: float) -> _dt.datetime | None:
    """Sleeps hasta el próximo cierre de 15M + delay. Retorna el
    timestamp del cierre.

    Retorna `None` si el mercado está cerrado — el caller decide (sleep
    corto y reintenta).
    """
    now = now_et()
    if not is_market_open(now):
        return None
    next_close = _next_15m_boundary(now)
    delta = (next_close - now).total_seconds() + delay_after_close_s
    if delta > 0:
        await asyncio.sleep(delta)
    return next_close


def _next_15m_boundary(now: _dt.datetime) -> _dt.datetime:
    """Próximo múltiplo de 15 min (00, 15, 30, 45) desde `now`.

    Ej: `now=10:23:15` → `10:30:00`. Si `now=10:30:00` exacto, retorna
    el próximo bucket (`10:45:00`).
    """
    minute = now.minute
    next_minute = ((minute // 15) + 1) * 15
    if next_minute >= 60:
        next_close = now.replace(
            minute=0, second=0, microsecond=0,
        ) + _dt.timedelta(hours=1)
    else:
        next_close = now.replace(
            minute=next_minute, second=0, microsecond=0,
        )
    return next_close


async def _run_scan_cycle(
    *,
    data_engine: DataEngine,
    session_factory: async_sessionmaker,
    broadcaster: Broadcaster,
    slot_tickers: list[str],
    fixture: dict,
    candle_timestamp: _dt.datetime,
) -> None:
    """Dispara el scan paralelo por cada slot operativo."""
    logger.info(
        f"Scan cycle starting at {candle_timestamp.isoformat()} "
        f"— slots={slot_tickers}",
    )
    await broadcaster.broadcast(
        EVENT_ENGINE_STATUS,
        {"engine": "data", "status": "green", "message": "cycle start"},
    )

    tasks = [
        asyncio.create_task(
            _scan_slot(
                data_engine=data_engine,
                session_factory=session_factory,
                broadcaster=broadcaster,
                slot_id=idx,
                ticker=ticker,
                fixture=fixture,
                candle_timestamp=candle_timestamp,
            ),
            name=f"scan_slot_{idx}_{ticker}",
        )
        for idx, ticker in enumerate(slot_tickers, start=1)
    ]
    # Fallos individuales no rompen el loop — return_exceptions=True
    await asyncio.gather(*tasks, return_exceptions=True)

    # Post-ciclo: emitir snapshot del KeyPool al WebSocket para que el
    # banner de 5 barras del Cockpit (spec §5.5) refleje el uso actual.
    await _broadcast_api_usage(broadcaster, data_engine)
    logger.info(f"Scan cycle done at {candle_timestamp.isoformat()}")


async def _broadcast_api_usage(
    broadcaster: Broadcaster,
    data_engine: DataEngine,
) -> None:
    """Emite un envelope `api_usage.tick` por cada key del pool.

    Spec §5.3: el evento `api_usage.tick` lleva el estado de UNA key
    (`{key_id, used_minute, max_minute, used_daily, max_daily,
    last_call_ts}`). Se emite por cada key del pool una vez por ciclo
    para que el frontend mantenga actualizado el banner del Cockpit
    (5 barras, una por key).
    """
    try:
        snapshot = data_engine.pool_snapshot()
    except Exception:
        logger.exception("pool_snapshot failed")
        return
    for state in snapshot:
        payload = {
            "key_id": state.key_id,
            "used_minute": state.used_minute,
            "max_minute": state.max_minute,
            "used_daily": state.used_daily,
            "max_daily": state.max_daily,
            "last_call_ts": (
                state.last_call_ts.isoformat()
                if state.last_call_ts is not None else None
            ),
            "exhausted": state.exhausted,
        }
        try:
            await broadcaster.broadcast(EVENT_API_USAGE_TICK, payload)
        except Exception:
            logger.exception(f"api_usage.tick broadcast failed key={state.key_id}")


async def _scan_slot(
    *,
    data_engine: DataEngine,
    session_factory: async_sessionmaker,
    broadcaster: Broadcaster,
    slot_id: int,
    ticker: str,
    fixture: dict,
    candle_timestamp: _dt.datetime,
) -> None:
    """Scan de un slot: fetch → integrity gate → scan_and_emit."""
    try:
        inputs = await data_engine.fetch_for_scan(ticker)
    except Exception:
        logger.exception(f"fetch_for_scan failed — slot={slot_id} ticker={ticker}")
        return

    if inputs is None:
        logger.warning(
            f"Slot {slot_id} ({ticker}): integrity gate failed, skipping scan",
        )
        return

    try:
        sim_dt = candle_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        sim_date = candle_timestamp.strftime("%Y-%m-%d")
        async with session_factory() as session:
            await scan_and_emit(
                session=session,
                broadcaster=broadcaster,
                candle_timestamp=candle_timestamp,
                slot_id=slot_id,
                ticker=ticker,
                candles_daily=inputs["candles_daily"],
                candles_1h=inputs["candles_1h"],
                candles_15m=inputs["candles_15m"],
                fixture=fixture,
                spy_daily=inputs["spy_daily"],
                bench_daily=inputs["spy_daily"],  # MVP: bench = SPY
                sim_datetime=sim_dt,
                sim_date=sim_date,
            )
    except Exception:
        logger.exception(
            f"scan_and_emit failed — slot={slot_id} ticker={ticker}",
        )
