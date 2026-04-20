# Data Engine

**Tipo:** motor vivo (proceso con ciclo de vida propio).
**Estado:** pendiente de implementación (Capa 1 — siguiente paso del desarrollo).

## Rol

Responsable de la obtención, almacenamiento y distribución de datos de mercado. Es la frontera del sistema con el provider externo (Twelve Data).

## Responsabilidades

- Gestión de hasta 5 API keys con round-robin proporcional a créditos/min.
- Redistribución dinámica si una key agota cupo diario.
- Consulta a DB local antes de fetchear el provider (ADR-0003).
- Fetch de velas daily/1H/15M + benchmarks + SPY daily.
- Verificación de integridad pre-señal (velas completas, timestamps coherentes, sin corrupción).
- Emisión de señal al Scoring Engine cuando los datos están listos.
- Retry policy con DEGRADED escalonado ante fallos (ADR-0004).
- Reset del contador diario al cierre de mercado ET.
- Wipe de API keys en RAM y DB al apagar el backend.

## Contratos con otros componentes

- **Consume:** nada externo al proceso.
- **Provee:** velas + flag de integridad al Scoring Engine vía llamada directa intra-proceso.
- **Escribe:** tabla `candles_*` del DB module. Tabla `heartbeat` con su propio estado cada 2 min.
- **Emite eventos WebSocket:** `api_usage.tick`, `engine.status`, `slot.status` (cuando el motor determina DEGRADED).

## Invariantes

1. Nunca pasa velas con integridad no verificada al Scoring Engine.
2. Nunca escribe API keys al disco en plano.
3. Nunca bloquea el event loop con fetches síncronos (todo async con `asyncio.gather()` o `httpx.AsyncClient`).
4. Respeta el cupo/min declarado por key (no lo excede ni aunque haya urgencia).

## Decisiones arquitectónicas relevantes

- ADR-0002: timestamps en ET tz-aware.
- ADR-0003: warmup paralelo con consulta DB local previa.
- ADR-0004: retry policy con `ENG-060`.

## Pendientes de resolver al implementar

- Valores default de ring buffers de candles por timeframe.
- Umbral exacto de `ENG-060` (tentativo 3 ciclos).
- Detección precisa de gaps en la DB tras periodos offline (feriados, half-days).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.1 (Data Engine completo).
- `docs/specs/SCORING_ENGINE_SPEC.md` §2.2 (contrato de velas que el motor espera recibir).
- `scanner_v4_2_1.html` — referencia conceptual del round-robin (3 años en producción).
