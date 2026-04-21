"""Tests del `TwelveDataClient` usando `httpx.MockTransport`.

No hace network real — todo el HTTP pasa por un handler in-memory que
inspecciona las requests y devuelve respuestas canned.

Cubren:
  - Happy path (DAILY, H1, M15) con parseo correcto
  - Integración con KeyPool: acquire + release con credits/success
  - TD status=error con daily cap → mark_exhausted
  - TD status=error sin daily cap → NO mark_exhausted
  - HTTP 4xx/5xx + HTTP 429
  - JSON malformado / values vacío / candle malformado
  - Timeouts y network errors
  - KeyPool exhausted antes de fetch
  - Context manager / close idempotente
  - test_key happy + sad paths
"""

from __future__ import annotations

from datetime import datetime

import httpx

from engines.data.api_keys import KeyPool
from engines.data.constants import ET
from engines.data.fetcher import TwelveDataClient
from engines.data.models import ApiKeyConfig, Timeframe

# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _key(
    key_id: str = "k1",
    *,
    enabled: bool = True,
    cpm: int = 8,
    cpd: int = 800,
    secret: str | None = None,
) -> ApiKeyConfig:
    return ApiKeyConfig(
        key_id=key_id,
        secret=secret if secret is not None else f"secret-{key_id}",
        credits_per_minute=cpm,
        credits_per_day=cpd,
        enabled=enabled,
    )


def _ok_response(values: list[dict]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "meta": {"symbol": "QQQ", "interval": "1day"},
            "values": values,
            "status": "ok",
        },
    )


def _error_response(code: int, message: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": code, "message": message, "status": "error"},
    )


def _sample_daily(n: int = 3) -> list[dict]:
    base = [
        {
            "datetime": f"2025-01-{i + 1:02d}",
            "open": f"{100 + i}.00",
            "high": f"{101 + i}.00",
            "low": f"{99 + i}.00",
            "close": f"{100 + i}.50",
            "volume": f"{1000000 + i * 100}",
        }
        for i in range(n)
    ]
    return base


def _sample_intraday(n: int = 3) -> list[dict]:
    return [
        {
            "datetime": f"2025-01-02 {10 + i:02d}:00:00",
            "open": f"{510 + i}.00",
            "high": f"{511 + i}.00",
            "low": f"{509 + i}.00",
            "close": f"{510 + i}.50",
            "volume": f"{200000 + i * 100}",
        }
        for i in range(n)
    ]


def _transport_with(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def _make_client(
    pool: KeyPool,
    handler,
) -> TwelveDataClient:
    return TwelveDataClient(
        pool,
        base_url="https://mock.twelvedata.test",
        transport=_transport_with(handler),
    )


# ═══════════════════════════════════════════════════════════════════════════
# Happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestFetchHappyPath:
    async def test_daily_parses_correctly(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response(_sample_daily(3)))
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 3)
        assert result.integrity_ok is True
        assert len(result.candles) == 3
        assert result.used_key_id == "k1"
        assert result.candles[0].dt == datetime(2025, 1, 1, tzinfo=ET)
        assert result.candles[0].o == 100.0
        assert result.candles[0].v == 1000000

    async def test_intraday_parses_with_hm_format(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response(_sample_intraday(3)))
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.H1, 3)
        assert result.integrity_ok is True
        assert result.candles[0].dt == datetime(2025, 1, 2, 10, 0, tzinfo=ET)
        assert result.candles[-1].dt == datetime(2025, 1, 2, 12, 0, tzinfo=ET)

    async def test_request_includes_required_params(self) -> None:
        captured: dict = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["params"] = dict(req.url.params)
            return _ok_response(_sample_daily(1))

        pool = KeyPool([_key()])
        client = await _make_client(pool, handler)
        async with client:
            await client.fetch_candles("QQQ", Timeframe.M15, 50)

        assert captured["params"]["symbol"] == "QQQ"
        assert captured["params"]["interval"] == "15min"
        assert captured["params"]["outputsize"] == "50"
        assert captured["params"]["timezone"] == "America/New_York"
        assert captured["params"]["order"] == "ASC"
        assert captured["params"]["apikey"] == "secret-k1"

    async def test_success_releases_with_credits_and_success_flag(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response(_sample_daily(2)))
        async with client:
            await client.fetch_candles("QQQ", Timeframe.DAILY, 2)
        [state] = pool.snapshot()
        # 1 crédito facturado, last_call_ts actualizado
        assert state.used_daily == 1
        assert state.last_call_ts is not None


# ═══════════════════════════════════════════════════════════════════════════
# Respuestas de error de TD (status=error)
# ═══════════════════════════════════════════════════════════════════════════


class TestTDErrors:
    async def test_daily_cap_exhaustion_marks_key_exhausted(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: _error_response(
                429, "You have reached the daily API credit limit for your plan."
            ),
        )
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("daily_cap" in n for n in result.integrity_notes)
        [state] = pool.snapshot()
        assert state.exhausted is True

    async def test_per_minute_rate_limit_does_not_mark_exhausted(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: _error_response(
                429, "You have reached the limit of API per minute for your plan."
            ),
        )
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("api_error" in n for n in result.integrity_notes)
        [state] = pool.snapshot()
        # La key NO fue marcada como exhausted — el error es transitorio.
        assert state.exhausted is False

    async def test_generic_td_error_does_not_mark_exhausted(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool, lambda req: _error_response(400, "Symbol not found: FAKEXYZ")
        )
        async with client:
            result = await client.fetch_candles("FAKEXYZ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        [state] = pool.snapshot()
        assert state.exhausted is False


# ═══════════════════════════════════════════════════════════════════════════
# HTTP-level errors
# ═══════════════════════════════════════════════════════════════════════════


class TestHTTPErrors:
    async def test_http_500_returned_as_failed_fetch(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: httpx.Response(500))
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("http_error" in n and "500" in n for n in result.integrity_notes)
        [state] = pool.snapshot()
        # Llamada fallida → no se factura al cupo diario.
        assert state.used_daily == 0

    async def test_http_429_marks_key_exhausted(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: httpx.Response(429))
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("daily_cap_http429" in n for n in result.integrity_notes)
        [state] = pool.snapshot()
        assert state.exhausted is True

    async def test_timeout_returns_failed_result(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("simulated timeout")

        pool = KeyPool([_key()])
        client = await _make_client(pool, handler)
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("http_timeout" in n for n in result.integrity_notes)

    async def test_network_error_returns_failed_result(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("simulated DNS fail")

        pool = KeyPool([_key()])
        client = await _make_client(pool, handler)
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("network_error" in n for n in result.integrity_notes)


# ═══════════════════════════════════════════════════════════════════════════
# Respuestas malformadas / vacías
# ═══════════════════════════════════════════════════════════════════════════


class TestMalformedResponses:
    async def test_empty_values_array(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response([]))
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("empty_values" in n for n in result.integrity_notes)
        [state] = pool.snapshot()
        # La request sí se facturó (recibimos 200 con status=ok).
        assert state.used_daily == 1

    async def test_candle_with_missing_field_reports_malformed(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            bad = _sample_daily(2)
            del bad[0]["high"]
            return _ok_response(bad)

        pool = KeyPool([_key()])
        client = await _make_client(pool, handler)
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("malformed_candle" in n for n in result.integrity_notes)

    async def test_non_json_body(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: httpx.Response(
                200, content=b"not-json", headers={"content-type": "application/json"}
            ),
        )
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert any("malformed_json" in n for n in result.integrity_notes)


# ═══════════════════════════════════════════════════════════════════════════
# Pool interaction edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestPoolInteraction:
    async def test_pool_exhausted_returns_failed_without_calling_provider(self) -> None:
        call_count = 0

        def handler(req: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return _ok_response(_sample_daily(1))

        pool = KeyPool([_key()])
        pool.mark_exhausted("k1")
        client = await _make_client(pool, handler)
        async with client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 10)
        assert result.integrity_ok is False
        assert result.used_key_id is None
        assert any("key_pool_exhausted" in n for n in result.integrity_notes)
        assert call_count == 0  # nunca llegó al provider


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestLifecycle:
    async def test_close_is_idempotent(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response(_sample_daily(1)))
        await client.close()
        await client.close()  # no debe lanzar

    async def test_context_manager_closes_underlying_client(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: _ok_response(_sample_daily(1)))
        async with client:
            pass
        # tras el with, el cliente interno quedó cerrado
        assert client._closed is True


# ═══════════════════════════════════════════════════════════════════════════
# test_key
# ═══════════════════════════════════════════════════════════════════════════


class TestTestKey:
    async def test_returns_true_on_200_ok(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: httpx.Response(200, json={"status": "ok", "price": "510.00"}),
        )
        async with client:
            ok = await client.test_key(_key("probe"))
        assert ok is True

    async def test_returns_false_when_td_status_is_error(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: httpx.Response(
                200, json={"status": "error", "code": 401, "message": "Invalid api key"}
            ),
        )
        async with client:
            ok = await client.test_key(_key("probe"))
        assert ok is False

    async def test_returns_false_on_http_error(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(pool, lambda req: httpx.Response(500))
        async with client:
            ok = await client.test_key(_key("probe"))
        assert ok is False

    async def test_returns_false_on_timeout(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("boom")

        pool = KeyPool([_key()])
        client = await _make_client(pool, handler)
        async with client:
            ok = await client.test_key(_key("probe"))
        assert ok is False

    async def test_returns_false_on_malformed_json(self) -> None:
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: httpx.Response(
                200, content=b"<html>", headers={"content-type": "text/html"}
            ),
        )
        async with client:
            ok = await client.test_key(_key("probe"))
        assert ok is False

    async def test_test_key_does_not_consume_pool(self) -> None:
        """El test_key bypassa el pool — usado para validar keys antes de enrollearlas."""
        pool = KeyPool([_key()])
        client = await _make_client(
            pool,
            lambda req: httpx.Response(200, json={"status": "ok", "price": "510"}),
        )
        async with client:
            await client.test_key(_key("probe", secret="other-secret"))
        [state] = pool.snapshot()
        assert state.used_daily == 0
        assert state.used_minute == 0
