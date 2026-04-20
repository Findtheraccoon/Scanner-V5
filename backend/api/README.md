# API Layer

**Tipo:** frontera de red del backend.
**Estado:** pendiente de implementación.

## Rol

Exponer los motores + módulos al frontend (y a consumidores externos) vía REST HTTP y WebSocket. Es la única capa con I/O de red visible.

## Stack

- FastAPI para REST y WebSocket (Uvicorn single-worker).
- Autenticación: bearer token en header `Authorization` (REST) o query param `?token=` (WebSocket handshake).
- Versionado: todos los endpoints bajo `/api/v1/`.
- OpenAPI autogenerado por FastAPI en `/docs` y `/redoc`.

## Endpoints REST principales

- `GET /api/v1/signals/latest` — última señal por slot.
- `GET /api/v1/signals/history?slot_id=N&from=...&to=...&cursor=...` — histórico paginado.
- `GET /api/v1/signals/{id}` — señal completa con snapshot (bajo demanda).
- `GET /api/v1/engine/health` — estado del Scoring Engine.
- `POST /api/v1/auth/rotate` — rotar el bearer token.
- `POST /api/v1/slots/{id}/hot-reload` — gatillar hot-reload de un slot.
- `POST /api/v1/validator/run` — correr batería completa del Validator.
- `POST /api/v1/validator/slot/{id}` — revalidar un solo slot.
- `POST /api/v1/db/cleanup` — correr limpieza de DB manualmente.
- `POST /api/v1/config/backup` — disparar backup S3.

## WebSocket — catálogo de eventos (v1.1.0)

Envelope: `{event, timestamp: ISO8601 ET tz-aware, payload}`.

- `signal.new` — nueva señal emitida (incluye `chat_format` listo).
- `slot.status` — cambios de estado de slot (incluye `warmup_progress`).
- `engine.status` — cambios de estado de motor.
- `api_usage.tick` — actualización de créditos API.
- `validator.progress` — progreso de batería de tests.
- `system.log` — eventos críticos para Dashboard.

## Invariantes

1. Todos los endpoints públicos requieren auth — no hay excepciones.
2. Timestamps en respuestas siempre tz-aware ET.
3. Snapshots gzip de velas solo se sirven en `GET /signals/{id}` (bajo demanda), nunca en WebSocket.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.6 (Outputs Scoring — endpoints).
- `docs/operational/FEATURE_DECISIONS.md` §5.3 (Protocolo y catálogo WebSocket).
- ADR-0001 (auth), ADR-0005 (`chat_format`).
