"""KeyPool — gestor de hasta 5 API keys con round-robin proporcional.

Implementa la estrategia validada en producción por el scanner v4.2.1
durante 3 años (ver referencia conceptual en `scanner_v4.2.1.html`):

- **Round-robin proporcional** a `credits_per_minute` declarado por key:
  una key con cupo 8/min sirve el doble de llamadas que una con cupo 4/min
  en el mismo intervalo.
- **Redistribución dinámica** si una key agota cupo diario: el tráfico se
  reparte proporcionalmente entre las restantes hasta el próximo reset.
- **Reset diario al cierre de mercado ET** (no medianoche UTC), por decisión
  de producto en FEATURE_DECISIONS §3.1.
- **Wipe de secretos en memoria al shutdown** (wipe obligatorio por política
  de seguridad).

Este módulo es un stub: define la interfaz pública y la estructura interna,
pero los métodos lanzan `NotImplementedError` hasta que se implemente la
lógica real en la Fase 1 del Data Engine.
"""

from __future__ import annotations

from engines.data.models import ApiKeyConfig, ApiKeyState


class KeyPool:
    """Pool de API keys con round-robin proporcional y reset diario ET.

    Lifecycle:
        pool = KeyPool(keys)
        async with pool.acquire() as key:   # cede una key disponible
            ...                              # usar key.secret contra provider
        # pool.release() implícito al salir del context
        pool.shutdown()                      # wipe de secretos en memoria

    Thread safety:
        El pool es async-safe (usa locks/semaphores internos). No es
        thread-safe; asume single event loop (consistente con Uvicorn
        single-worker declarado en el stack).
    """

    def __init__(self, keys: list[ApiKeyConfig]) -> None:
        """Inicializa el pool con hasta 5 keys configuradas.

        Args:
            keys: lista de configs de keys (ya desencriptadas del Config
                del usuario). Longitud ≤ MAX_API_KEYS. Keys con
                `enabled=False` quedan fuera del round-robin pero se
                conservan para poder reactivarlas sin reinicio.

        Raises:
            ValueError: si `keys` está vacía, si hay `key_id` duplicado,
                o si se exceden MAX_API_KEYS keys habilitadas.
        """
        raise NotImplementedError

    async def acquire(self) -> ApiKeyConfig:
        """Cede la próxima key del round-robin proporcional.

        Bloquea (async) si todas las keys habilitadas están a tope de
        cupo/minuto hasta que una se libere (o hasta que pase el minuto
        calendario y se resetee el contador).

        Returns:
            La `ApiKeyConfig` a usar para la próxima llamada al provider.

        Raises:
            KeyPoolExhaustedError: si todas las keys habilitadas agotaron
                cupo diario. El caller debe propagar como ENG-060 si el
                fallo persiste N ciclos.
        """
        raise NotImplementedError

    def release(self, key_id: str, credits_used: int = 1, *, success: bool = True) -> None:
        """Registra el consumo tras una llamada al provider.

        Llamado por el TwelveDataClient cuando una request completa
        (exitosa o no). Actualiza `used_minute`, `used_daily` y, si
        `success=True`, `last_call_ts`.

        Args:
            key_id: identificador de la key usada.
            credits_used: costo real de la llamada en créditos.
            success: si False, la llamada falló — no se contabiliza
                `last_call_ts` pero sí se descuentan los créditos (el
                provider ya los cobró).
        """
        raise NotImplementedError

    def mark_exhausted(self, key_id: str) -> None:
        """Marca una key como agotada para cupo diario.

        Típicamente invocado cuando el provider devuelve 429 o un error
        específico de cupo. Dispara `redistribute_on_exhaustion()`.
        """
        raise NotImplementedError

    def redistribute_on_exhaustion(self) -> None:
        """Recalcula los pesos del round-robin entre las keys no agotadas.

        Estrategia: mantiene la proporcionalidad a `credits_per_minute`
        entre las restantes. Si una de cupo 8/min se agota y quedan dos
        de cupo 4/min, el tráfico queda 50/50 entre esas dos.
        """
        raise NotImplementedError

    def reset_daily(self) -> None:
        """Resetea `used_daily` y `exhausted` de todas las keys.

        Llamado por un job interno del Data Engine al cierre de mercado ET
        (no medianoche UTC). Ver FEATURE_DECISIONS §3.1.
        """
        raise NotImplementedError

    def snapshot(self) -> list[ApiKeyState]:
        """Estado actual de todas las keys para el evento `api_usage.tick`.

        Devuelve una copia inmutable — no expone estructura interna.
        """
        raise NotImplementedError

    def shutdown(self) -> None:
        """Wipe de secretos en memoria.

        Sobrescribe los `secret` de cada `ApiKeyConfig` interno con una
        string de ceros de la misma longitud antes de liberar la
        referencia. Idempotente.
        """
        raise NotImplementedError


class KeyPoolExhaustedError(Exception):
    """Todas las keys habilitadas agotaron cupo diario.

    Solo se lanza desde `KeyPool.acquire()`. El caller debe manejarlo en
    su retry loop y, si persiste, elevar `ENG-060` al slot afectado.
    """
