"""DataEngine orquestrador — coordina KeyPool + TwelveDataClient + cache DB.

Punto de entrada único del Data Engine para los consumers (scan loop,
tests, manual tools). Encapsula el flujo completo por ciclo:

    fetch del provider → verify integrity → persist en DB →
    retornar velas listas para `analyze()`

**Responsabilidades:**

- `warmup(tickers)` — al arranque, fetch paralelo de 210 daily + 80 1H
  + 50 15M por ticker (`asyncio.gather`). Cada resultado se persiste
  en `candles_{daily,1h,15m}`.
- `fetch_for_scan(ticker)` — en cada ciclo de scan AUTO: fetch fresco
  de los 3 timeframes + SPY daily, verificación de integridad y
  conversión al formato dict que consume `analyze()`. Retorna `None`
  si algún TF falla integrity (invariante I1 del motor — nunca se le
  pasan al Scoring velas con integridad no verificada).

**No implementado en DE.2 (scope futuro):**

- Optimización "consulta DB primero → fetch solo gap" (ADR-0003). Por
  ahora siempre se fetchea del provider — simplifica el flujo y mantiene
  tests determinísticos. La persistencia ya ocurre para habilitar la
  optimización cuando se implemente.
- Reset diario del pool al cierre ET — lo hará el scan loop (DE.3).
- Emisión de eventos `api_usage.tick` — scope DE.4.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import async_sessionmaker

from engines.data.api_keys import KeyPool
from engines.data.constants import (
    ET,
    RETRY_SHORT_DELAY_S,
    WARMUP_1H_N,
    WARMUP_15M_N,
    WARMUP_DAILY_N,
)
from engines.data.fetcher import TwelveDataClient
from engines.data.models import ApiKeyState, Candle, FetchResult, Timeframe
from modules.db import CandleTF, read_candles_window, write_candles_batch

# Mapeo local Timeframe (engines.data) → CandleTF (modules.db) para
# evitar dependencia circular entre capas.
_TF_TO_DB: dict[Timeframe, CandleTF] = {
    Timeframe.DAILY: "daily",
    Timeframe.H1: "1h",
    Timeframe.M15: "15m",
}

_DEFAULT_WARMUP_SIZES: dict[Timeframe, int] = {
    Timeframe.DAILY: WARMUP_DAILY_N,
    Timeframe.H1: WARMUP_1H_N,
    Timeframe.M15: WARMUP_15M_N,
}

# Ventanas de freshness para DB-first en warmup (ADR-0003).
# Si la última vela en DB es más vieja que `now - threshold`, se
# considera stale y se refetch.
_WARMUP_FRESHNESS: dict[Timeframe, timedelta] = {
    Timeframe.DAILY: timedelta(days=7),
    Timeframe.H1: timedelta(days=3),
    Timeframe.M15: timedelta(days=1),
}


class DataEngine:
    """Orquestrador del Data Engine.

    Composición:

    - `KeyPool` (shared) — gestiona round-robin + exhaustion de keys.
    - `TwelveDataClient` — cliente async del provider.
    - `session_factory` — factory de sesiones async de SQLAlchemy para
      persistir las velas fetcheadas.

    **Lifecycle:** el DataEngine NO es dueño del cliente ni del pool —
    los consume. El entrypoint (`main.py`) los construye y pasa.
    """

    def __init__(
        self,
        *,
        pool: KeyPool,
        client: TwelveDataClient,
        session_factory: async_sessionmaker,
        warmup_sizes: dict[Timeframe, int] | None = None,
    ) -> None:
        self._pool = pool
        self._client = client
        self._session_factory = session_factory
        self._warmup_sizes = dict(warmup_sizes or _DEFAULT_WARMUP_SIZES)

    # ─────────────────────────────────────────────────────────────────────
    # Warmup
    # ─────────────────────────────────────────────────────────────────────

    async def warmup(
        self,
        tickers: list[str],
    ) -> dict[str, dict[Timeframe, FetchResult]]:
        """Warmup por ticker x TF con DB-first (ADR-0003).

        Para cada `(ticker, TF)`:

        1. Consulta `read_candles_window` las últimas N velas en DB.
        2. Si hay ≥ N velas **y** la última está dentro del freshness
           window (daily 7d, 1H 3d, 15M 1d), se SKIPPEA el fetch —
           devuelve `FetchResult` sintético con `used_key_id=None`.
        3. Si no, fetch normal al provider + UPSERT.

        Los fetches que sí disparan corren en paralelo con
        `asyncio.gather()`. El caso cotidiano (scanner re-arrancado al
        día siguiente con la DB caliente) puede resultar en 0 fetches.

        Args:
            tickers: lista de símbolos. Idempotente.

        Returns:
            Dict anidado `{ticker: {TF: FetchResult}}`. `used_key_id`
            es `None` cuando el resultado salió de DB-cache.
        """
        logger.info(
            f"DataEngine warmup starting — tickers={tickers} "
            f"sizes={self._warmup_sizes}",
        )
        results: dict[str, dict[Timeframe, FetchResult]] = {
            t: {} for t in tickers
        }
        fetch_tasks: list[tuple[str, Timeframe, asyncio.Task]] = []

        # Fase 1: verificar DB por cada (ticker, TF). Los que están
        # frescos se resuelven localmente; los que faltan se agregan a
        # la lista de fetch.
        for ticker in tickers:
            for tf, count in self._warmup_sizes.items():
                cached = await self._load_from_db_if_fresh(ticker, tf, count)
                if cached is not None:
                    results[ticker][tf] = cached
                    logger.debug(
                        f"Warmup DB-hit — ticker={ticker} tf={tf.value} "
                        f"candles={len(cached.candles)}",
                    )
                    continue
                task = asyncio.create_task(
                    self._client.fetch_candles(ticker, tf, count),
                    name=f"warmup_{ticker}_{tf.value}",
                )
                fetch_tasks.append((ticker, tf, task))

        # Fase 2: gather de los fetches pendientes + persist.
        for ticker, tf, task in fetch_tasks:
            fetch = await task
            results[ticker][tf] = fetch
            if fetch.integrity_ok and fetch.candles:
                await self._persist(ticker, tf, fetch.candles)
            elif not fetch.integrity_ok:
                logger.warning(
                    f"Warmup fetch failed integrity: ticker={ticker} "
                    f"tf={tf.value} notes={fetch.integrity_notes}",
                )
        hit = sum(
            1 for ticker_results in results.values()
            for fr in ticker_results.values()
            if fr.used_key_id is None and fr.integrity_ok
        )
        fetched = len(fetch_tasks)
        logger.info(
            f"DataEngine warmup completed — db_hits={hit} "
            f"provider_fetches={fetched}",
        )
        return results

    async def _load_from_db_if_fresh(
        self,
        ticker: str,
        tf: Timeframe,
        count: int,
    ) -> FetchResult | None:
        """Devuelve un `FetchResult` sintético si la DB tiene >= count
        velas frescas. `None` si hay que refetch."""
        db_tf = _TF_TO_DB[tf]
        async with self._session_factory() as session:
            rows = await read_candles_window(
                session, timeframe=db_tf, ticker=ticker, limit=count,
            )
        if len(rows) < count:
            return None
        last_dt = rows[-1]["dt"]
        freshness = _WARMUP_FRESHNESS[tf]
        if datetime.now(tz=ET) - last_dt > freshness:
            return None
        candles = [
            Candle(
                dt=row["dt"],
                o=row["o"], h=row["h"], l=row["l"], c=row["c"],
                v=row["v"],
            )
            for row in rows
        ]
        return FetchResult(
            ticker=ticker,
            timeframe=tf,
            candles=candles,
            integrity_ok=True,
            integrity_notes=[f"db_cache_hit: {len(candles)} candles"],
            fetched_at=datetime.now(tz=ET),
            used_key_id=None,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Scan fetch
    # ─────────────────────────────────────────────────────────────────────

    async def fetch_for_scan(
        self,
        ticker: str,
        *,
        include_spy: bool = True,
        spy_ticker: str = "SPY",
    ) -> dict[str, Any] | None:
        """Obtiene las velas listas para un scan del `ticker`.

        Con retry nivel 1 (ADR-0004): si el primer intento falla
        integrity, espera `RETRY_SHORT_DELAY_S` (1s default) y
        reintenta una vez. Si el segundo también falla, retorna `None`
        y el scan_loop escala al nivel 2 (skip del ciclo + incrementa
        contador del slot).

        Args:
            ticker: símbolo del slot a escanear.
            include_spy: si `True`, también fetch SPY daily (necesario
                para confirms DivSPY/FzaRel).
            spy_ticker: override del benchmark (default "SPY").

        Returns:
            Dict `{candles_daily, candles_1h, candles_15m, spy_daily,
            fetched_at}` listo para pasar a `scan_and_emit()`. `None`
            si alguno de los fetches falló integrity incluso después
            del retry.
        """
        result = await self._fetch_for_scan_once(
            ticker, include_spy=include_spy, spy_ticker=spy_ticker,
        )
        if result is not None:
            return result
        # Retry nivel 1 (ADR-0004)
        logger.info(
            f"fetch_for_scan retry after {RETRY_SHORT_DELAY_S}s — "
            f"ticker={ticker}",
        )
        await asyncio.sleep(RETRY_SHORT_DELAY_S)
        return await self._fetch_for_scan_once(
            ticker, include_spy=include_spy, spy_ticker=spy_ticker,
        )

    async def _fetch_for_scan_once(
        self,
        ticker: str,
        *,
        include_spy: bool,
        spy_ticker: str,
    ) -> dict[str, Any] | None:
        """Single attempt (sin retry) — usado por `fetch_for_scan`."""
        coros = [
            self._client.fetch_candles(ticker, Timeframe.DAILY, self._warmup_sizes[Timeframe.DAILY]),
            self._client.fetch_candles(ticker, Timeframe.H1, self._warmup_sizes[Timeframe.H1]),
            self._client.fetch_candles(ticker, Timeframe.M15, self._warmup_sizes[Timeframe.M15]),
        ]
        if include_spy:
            coros.append(
                self._client.fetch_candles(
                    spy_ticker, Timeframe.DAILY,
                    self._warmup_sizes[Timeframe.DAILY],
                ),
            )
        results = await asyncio.gather(*coros, return_exceptions=False)

        fetch_daily, fetch_1h, fetch_15m = results[0], results[1], results[2]
        fetch_spy = results[3] if include_spy else None

        # Integrity gate — si alguno falla, retorna None
        for fetch in (fetch_daily, fetch_1h, fetch_15m):
            if not fetch.integrity_ok:
                logger.warning(
                    f"fetch_for_scan_once aborting — ticker={ticker} "
                    f"tf={fetch.timeframe.value} notes={fetch.integrity_notes}",
                )
                return None
        if fetch_spy is not None and not fetch_spy.integrity_ok:
            logger.warning(
                f"fetch_for_scan_once SPY failed — notes={fetch_spy.integrity_notes}",
            )
            return None

        # Persist
        await self._persist(ticker, Timeframe.DAILY, fetch_daily.candles)
        await self._persist(ticker, Timeframe.H1, fetch_1h.candles)
        await self._persist(ticker, Timeframe.M15, fetch_15m.candles)
        if fetch_spy is not None:
            await self._persist(spy_ticker, Timeframe.DAILY, fetch_spy.candles)

        return {
            "candles_daily": [_candle_to_scan_dict(c) for c in fetch_daily.candles],
            "candles_1h": [_candle_to_scan_dict(c) for c in fetch_1h.candles],
            "candles_15m": [_candle_to_scan_dict(c) for c in fetch_15m.candles],
            "spy_daily": (
                [_candle_to_scan_dict(c) for c in fetch_spy.candles]
                if fetch_spy is not None else None
            ),
            "fetched_at": fetch_daily.fetched_at,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Introspección del pool — para eventos api_usage.tick
    # ─────────────────────────────────────────────────────────────────────

    def pool_snapshot(self) -> list[ApiKeyState]:
        """Snapshot del estado de cada API key del pool.

        Delega al `KeyPool.snapshot()`. Usado por el scan loop para
        emitir `api_usage.tick` al final de cada ciclo (spec §5.3).
        """
        return self._pool.snapshot()

    # ─────────────────────────────────────────────────────────────────────
    # Internos
    # ─────────────────────────────────────────────────────────────────────

    async def _persist(
        self,
        ticker: str,
        timeframe: Timeframe,
        candles: list[Candle],
    ) -> None:
        """Persiste velas en la tabla correspondiente."""
        if not candles:
            return
        db_tf = _TF_TO_DB[timeframe]
        rows = [
            {
                "dt": c.dt,
                "o": c.o,
                "h": c.h,
                "l": c.l,
                "c": c.c,
                "v": c.v,
            }
            for c in candles
        ]
        async with self._session_factory() as session:
            await write_candles_batch(
                session, timeframe=db_tf, ticker=ticker, candles=rows,
            )


def _candle_to_scan_dict(c: Candle) -> dict[str, Any]:
    """Convierte un `Candle` al dict que espera `analyze()` del Scoring.

    El motor espera `dt` como string `"YYYY-MM-DD HH:MM:SS"` (sin tz).
    El `Candle` tiene `dt` tz-aware ET — formateamos sin tzinfo.
    """
    dt_value: datetime = c.dt
    return {
        "dt": dt_value.strftime("%Y-%m-%d %H:%M:%S"),
        "o": c.o,
        "h": c.h,
        "l": c.l,
        "c": c.c,
        "v": c.v,
    }
