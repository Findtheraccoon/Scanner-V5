"""TwelveDataClient — cliente async contra el provider Twelve Data.

Todas las llamadas HTTP pasan por el `KeyPool` (round-robin proporcional
con redistribución dinámica). El cliente traduce el formato de respuesta
de Twelve Data al tipo canónico `Candle` del motor.

Este módulo es un stub: define la interfaz pública y las firmas de los
métodos, pero sin la lógica de HTTP real. La implementación usará
`httpx.AsyncClient` con connection pooling y timeout conservador.

Invariantes (ver `backend/engines/data/README.md`):
    I1 · Nunca devuelve velas con integridad no verificada. El caller
         recibe un `FetchResult` con `integrity_ok` explícito.
    I2 · Nunca escribe keys al disco en plano (responsabilidad del Config
         module; este cliente solo las consume en memoria).
    I3 · Nunca bloquea el event loop (todo async, usa asyncio.gather
         donde corresponda).
    I4 · Respeta el cupo/minuto del pool (no lo excede ni bajo urgencia).
"""

from __future__ import annotations

from engines.data.api_keys import KeyPool
from engines.data.models import ApiKeyConfig, FetchResult, Timeframe


class TwelveDataClient:
    """Cliente async de Twelve Data integrado con `KeyPool`.

    Lifecycle:
        async with TwelveDataClient(pool) as client:
            result = await client.fetch_candles("QQQ", Timeframe.DAILY, 210)
    """

    def __init__(self, pool: KeyPool) -> None:
        """Crea el cliente.

        Args:
            pool: pool de API keys. El cliente no lo posee (no lo cierra
                en `close()`) — solo lo consume.
        """
        raise NotImplementedError

    async def __aenter__(self) -> TwelveDataClient:
        raise NotImplementedError

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Cierra el `httpx.AsyncClient` subyacente. Idempotente."""
        raise NotImplementedError

    async def fetch_candles(
        self,
        ticker: str,
        timeframe: Timeframe,
        count: int,
    ) -> FetchResult:
        """Fetch de `count` velas de `ticker` en `timeframe` desde Twelve Data.

        Flujo:
            1. Pool.acquire() → obtiene key disponible
            2. HTTP GET al endpoint time_series con la key
            3. Pool.release() con el costo real devuelto en la respuesta
            4. Traducción del formato TD → list[Candle]
            5. Verificación de integridad inline
            6. Devuelve `FetchResult` con `integrity_ok` explícito

        Args:
            ticker: símbolo en mayúsculas (ej. "QQQ").
            timeframe: uno de Timeframe.DAILY / H1 / M15.
            count: cantidad de velas más recientes a traer.

        Returns:
            `FetchResult` con las velas ordenadas antigua→reciente (mismo
            orden que espera el Scoring Engine) y flag de integridad.

        Errors:
            No lanza excepciones. Fallos de red/provider se reflejan como
            `FetchResult(integrity_ok=False, integrity_notes=[...])`. El
            caller (DataEngine) decide escalar a ENG-060 tras N ciclos
            consecutivos fallidos (ADR-0004).
        """
        raise NotImplementedError

    async def test_key(self, key: ApiKeyConfig) -> bool:
        """Prueba de conectividad rápida de una key individual.

        Llama a un endpoint barato de Twelve Data (ej. /api_usage o
        /stocks?symbol=SPY) para validar que la key responde 2xx. Usado
        por el botón "Test conectividad API" del Dashboard.

        Args:
            key: key a testear. No pasa por el pool — prueba directa.

        Returns:
            True si la key respondió 2xx dentro del timeout, False en
            cualquier otro caso.
        """
        raise NotImplementedError


class TwelveDataError(Exception):
    """Error genérico de la capa de fetch contra Twelve Data.

    Los consumers normales no ven estas excepciones porque `fetch_candles`
    las captura y devuelve `FetchResult(integrity_ok=False)`. Se expone
    para logging/diagnóstico interno y para `test_key` que sí puede
    querer distinguir tipos de fallo.
    """
