# DB Module

**Tipo:** capa de persistencia (biblioteca de funciones).
**Estado:** pendiente de implementación.

## Rol

Biblioteca de acceso a la DB que otros motores importan y llaman directamente. **NO es el Database Engine** — ese supervisa rotación y backup, este solo lee/escribe.

## Responsabilidades

- Modelos SQLAlchemy 2.0 async (`models.py`).
- Funciones de lectura/escritura (`db.write_signal()`, `db.read_candles()`, `db.write_candle_batch()`, etc.).
- Gestión de conexión y sesiones.
- Migraciones vía Alembic (config en `alembic.ini`, versiones en `alembic/versions/`).

## Tablas

- `signals` — señales emitidas. Schema híbrido 3 (columnas planas + blobs JSON + `candles_snapshot_gzip`). ~3 KB/señal.
- `candles_daily`, `candles_1h`, `candles_15m` — velas con retenciones distintas.
- `heartbeat` — estado de motores cada 2 min, TTL 24h.
- `system_log` — eventos críticos, retención 30 días.

## Dos DBs físicas

- **DB operativa** — `data/scanner.db` (archivos vivos del día a día).
- **DB archive** — `data/archive/scanner_archive.db` (histórico rotado, sin límite de tamaño).

## Migraciones

Ver ADR-0006: arranque híbrido con `create_all()` + `alembic stamp head`. Primera migración real se llama `0001_<descripción>` y modifica, no crea.

## Invariantes

1. Nunca expone objetos SQLAlchemy crudos al caller — devuelve dicts o dataclasses.
2. Timestamps siempre tz-aware en ET (ADR-0002).
3. Las consultas a archive son transparentes al caller (el archive se resuelve internamente según rango de fechas).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.7 (Persistencia completa).
- `docs/operational/FEATURE_DECISIONS.md` §5.7 (Migraciones DB híbrido).
- ADR-0006.
