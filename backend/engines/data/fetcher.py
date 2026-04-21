"""TwelveDataClient — cliente async contra el provider Twelve Data.

Todas las llamadas HTTP pasan por el `KeyPool` (round-robin proporcional
con redistribución dinámica). El cliente traduce el formato de respuesta
de Twelve Data al tipo canónico `Candle` del motor y verifica integridad
estructural antes de devolver.

Invariantes (documentadas en `backend/engines/data/README.md`):

    I1 · Nunca devuelve velas con integridad no verificada. El caller
         recibe un `FetchResult` con `integrity_ok` explícito.
    I2 · Nunca escribe keys al disco en plano (responsabilidad del
         Config module; este cliente solo las consume en memoria).
    I3 · Nunca bloquea el event loop — todo I/O es async via httpx.
    I4 · Respeta el cupo/minuto del pool. Solo se llama al provider
         tras `pool.acquire()`.

Política de facturación contra el pool:

    - Éxito (HTTP 200 + status=ok): release(credits_used=1, success=True)
    - HTTP error, network error, timeout: release(credits_used=0,
      success=False). Twelve Data documenta que no cobra llamadas
      fallidas.
    - TD devuelve status=error con código de daily cap: release(0, False)
      + mark_exhausted(). La key queda fuera del pool hasta reset_daily.
    - TD devuelve otros status=error: release(0, False). No marca
      exhausted — típicamente es ticker inválido u otro problema que no
      justifica excluir la key.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from engines.data.api_keys import KeyPool, KeyPoolExhaustedError
from engines.data.constants import ET, TWELVE_DATA_BASE_URL
from engines.data.integrity import check_integrity
from engines.data.models import ApiKeyConfig, Candle, FetchResult, Timeframe

# Mapeo Timeframe → interval del query string de Twelve Data.
_INTERVAL_MAP: dict[Timeframe, str] = {
    Timeframe.DAILY: "1day",
    Timeframe.H1: "1h",
    Timeframe.M15: "15min",
}

# Códigos/mensajes que indican cupo diario agotado en la key.
# TD devuelve HTTP 429 o 200+status=error con code 429. El mensaje
# discrimina entre "credits per minute" (transitorio, no marcamos
# exhausted porque KeyPool lo evita) y "daily credits" / "API credits"
# (agotamiento diario, marcamos exhausted).
_DAILY_CAP_MARKERS = ("daily", "api credit", "credit limit")


class TwelveDataClient:
    """Cliente async de Twelve Data integrado con `KeyPool`.

    Lifecycle::

        async with TwelveDataClient(pool) as client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 210)

    Testeable vía `transport` kwarg que acepta un `httpx.AsyncBaseTransport`
    custom — típicamente `httpx.MockTransport` en unit tests.
    """

    def __init__(
        self,
        pool: KeyPool,
        *,
        timeout_s: float = 10.0,
        base_url: str = TWELVE_DATA_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Crea el cliente.

        Args:
            pool: pool de API keys. El cliente no es dueño — no lo cierra
                en `close()`.
            timeout_s: timeout por request (default 10s).
            base_url: endpoint base de Twelve Data. Override para tests.
            transport: transport de httpx. Permite inyectar `MockTransport`
                en tests. Si `None`, httpx usa el HTTP transport default.
        """
        self._pool = pool
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s),
            transport=transport,
        )
        self._closed = False

    async def __aenter__(self) -> TwelveDataClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Cierra el `httpx.AsyncClient` subyacente. Idempotente."""
        if self._closed:
            return
        await self._client.aclose()
        self._closed = True

    # ─────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────

    async def fetch_candles(
        self,
        ticker: str,
        timeframe: Timeframe,
        count: int,
    ) -> FetchResult:
        """Fetch de `count` velas de `ticker` en `timeframe` desde Twelve Data.

        Nunca lanza excepciones — todos los fallos se materializan como
        `FetchResult(integrity_ok=False, integrity_notes=[...])`.

        Args:
            ticker: símbolo en mayúsculas (ej. "QQQ").
            timeframe: uno de Timeframe.DAILY / H1 / M15.
            count: cantidad de velas más recientes a traer.

        Returns:
            `FetchResult` con las velas en orden antigua→reciente y flag
            de integridad.
        """
        fetched_at = datetime.now(tz=ET)
        notes: list[str] = []

        # 1. Acquire key. Si el pool está exhausted, no hay nada que hacer.
        try:
            key = await self._pool.acquire()
        except KeyPoolExhaustedError:
            notes.append("key_pool_exhausted: no hay keys con cupo diario disponible")
            return FetchResult(
                ticker=ticker,
                timeframe=timeframe,
                candles=[],
                integrity_ok=False,
                integrity_notes=notes,
                fetched_at=fetched_at,
                used_key_id=None,
            )

        # Contabilidad: cuánto le descontamos al pool en `release()`.
        credits_used = 0
        success = False
        candles: list[Candle] = []

        try:
            params: dict[str, Any] = {
                "symbol": ticker,
                "interval": _INTERVAL_MAP[timeframe],
                "outputsize": count,
                "apikey": key.secret,
                "timezone": "America/New_York",
                "order": "ASC",
            }
            try:
                response = await self._client.get("/time_series", params=params)
            except httpx.TimeoutException:
                notes.append("http_timeout: provider no respondió dentro del timeout")
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )
            except httpx.HTTPError as e:
                notes.append(f"network_error: {type(e).__name__}: {e}")
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            # 2. HTTP-level errors (típicamente TD responde 200 incluso para
            #    errores de negocio, pero defendemos ante 4xx/5xx reales).
            if response.status_code != 200:
                notes.append(f"http_error: status={response.status_code}")
                if response.status_code == 429:
                    # Daily cap: marcar la key como exhausted.
                    self._pool.mark_exhausted(key.key_id)
                    notes.append("daily_cap_http429: key marcada como exhausted")
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            # 3. Parse JSON response.
            try:
                payload = response.json()
            except ValueError as e:
                notes.append(f"malformed_json: {e}")
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            # 4. TD-level status=error.
            if payload.get("status") == "error":
                code = payload.get("code")
                message = str(payload.get("message", ""))
                notes.append(f"api_error: code={code} message={message!r}")
                if _is_daily_cap_error(code, message):
                    self._pool.mark_exhausted(key.key_id)
                    notes.append("daily_cap: key marcada como exhausted")
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            values = payload.get("values")
            if not isinstance(values, list) or not values:
                notes.append("empty_values: respuesta ok pero sin velas")
                # La request SÍ se facturó.
                credits_used = 1
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            # 5. Traducir dict → Candle.
            try:
                candles = [_parse_candle(v) for v in values]
            except (KeyError, ValueError) as e:
                notes.append(f"malformed_candle: {type(e).__name__}: {e}")
                credits_used = 1
                return FetchResult(
                    ticker=ticker,
                    timeframe=timeframe,
                    candles=[],
                    integrity_ok=False,
                    integrity_notes=notes,
                    fetched_at=fetched_at,
                    used_key_id=key.key_id,
                )

            # 6. Integridad estructural (sin imponer min_count — el caller
            #    decide si la cantidad recibida alcanza para sus propósitos).
            integrity = check_integrity(candles, timeframe, min_count=1)
            credits_used = 1
            success = integrity.ok
            return FetchResult(
                ticker=ticker,
                timeframe=timeframe,
                candles=candles,
                integrity_ok=integrity.ok,
                integrity_notes=integrity.notes,
                fetched_at=fetched_at,
                used_key_id=key.key_id,
            )
        finally:
            self._pool.release(key.key_id, credits_used=credits_used, success=success)

    async def test_key(self, key: ApiKeyConfig) -> bool:
        """Prueba de conectividad rápida de una key individual.

        Usa `/quote?symbol=SPY` — un endpoint barato que existe en todos
        los planes de Twelve Data. La llamada NO pasa por el pool — es
        una prueba directa típicamente disparada desde el botón "Test
        conectividad API" del Dashboard antes de activar la key.

        Args:
            key: key a testear.

        Returns:
            True si la key respondió 200 con `status: "ok"` dentro del
            timeout del cliente. False en cualquier otro caso (timeout,
            4xx/5xx, status=error, JSON malformado).
        """
        params = {"symbol": "SPY", "apikey": key.secret}
        try:
            response = await self._client.get("/quote", params=params)
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        # TD devuelve 200 con `status: "error"` cuando la key es inválida.
        return payload.get("status") != "error"


# ═══════════════════════════════════════════════════════════════════════════
# Parsing helpers
# ═══════════════════════════════════════════════════════════════════════════


def _parse_candle(raw: dict[str, Any]) -> Candle:
    """Traduce un dict del array `values` de Twelve Data a `Candle`.

    Twelve Data devuelve todos los campos numéricos como strings. La
    columna `datetime` puede ser "YYYY-MM-DD" (daily) o
    "YYYY-MM-DD HH:MM:SS" (intraday). Aplicamos ZoneInfo ET porque ese
    es el `timezone` que pedimos explícitamente en el query string.

    Raises:
        KeyError: falta un campo obligatorio.
        ValueError: un campo tiene formato inválido.
    """
    dt = _parse_td_datetime(raw["datetime"])
    return Candle(
        dt=dt,
        o=float(raw["open"]),
        h=float(raw["high"]),
        l=float(raw["low"]),
        c=float(raw["close"]),
        v=int(float(raw["volume"])),  # viene como string "1234567" o "1.23e6"
    )


def _parse_td_datetime(s: str) -> datetime:
    """Parsea "YYYY-MM-DD" o "YYYY-MM-DD HH:MM:SS" como tz-aware ET."""
    if " " in s:
        dt_naive = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    else:
        dt_naive = datetime.strptime(s, "%Y-%m-%d")
    return dt_naive.replace(tzinfo=ET)


def _is_daily_cap_error(code: Any, message: str) -> bool:
    """Heurística para detectar el error de cupo diario en la respuesta TD.

    TD usa code=429 tanto para per-minute como per-day. El mensaje
    distingue. Por seguridad, solo marcamos como daily cap si hay
    indicación explícita en el mensaje; per-minute se trata como
    transitorio (el caller puede reintentar).
    """
    if code != 429:
        return False
    lower = message.lower()
    return any(marker in lower for marker in _DAILY_CAP_MARKERS)


class TwelveDataError(Exception):
    """Error genérico de la capa de fetch contra Twelve Data.

    Los consumers normales no ven estas excepciones porque `fetch_candles`
    las captura y devuelve `FetchResult(integrity_ok=False)`. Se expone
    por compatibilidad con código externo que pueda querer distinguir
    tipos de fallo (poco usado hoy).
    """
