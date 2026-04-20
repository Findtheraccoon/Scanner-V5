# Database Engine

**Tipo:** motor supervisor (módulo intra-proceso con ciclo de vida).
**Estado:** pendiente de implementación.

## Rol

Supervisor de salud y mantenimiento de la DB operativa. No es la capa de acceso a datos — eso lo hace `modules/db/`. El Database Engine corre tareas de mantenimiento programadas y bajo demanda.

## Responsabilidades

- Rotación de filas vencidas: mover de DB operativa a DB archive según políticas de retención.
- Ejecución de `VACUUM INTO` para backups atómicos sin detener el backend.
- Compresión + upload del backup a S3 (o compatible) cuando el trader lo dispara.
- Monitoreo de tamaño de DB y fragmentación.
- Reporte de su propio estado al heartbeat cada 2 min.
- Botón manual "Correr limpieza ahora" en Dashboard dispara rotación inmediata.

## Políticas de retención

| Tabla | DB operativa | Después |
|---|---|---|
| signals | 1 año | Archive |
| heartbeat | 24h | Borrado |
| system_log | 30 días | Archive |
| candles_daily | 3 años | Archive |
| candles_1h | 6 meses | Archive |
| candles_15m | 3 meses | Archive |

## Contratos con otros componentes

- **Consume:** funciones de `modules/db/`.
- **Provee:** nada directo al ciclo AUTO. Disparador de tareas de fondo.
- **Emite eventos WebSocket:** `engine.status` con cambios de estado.

## Invariantes

1. Operaciones pesadas (VACUUM, backup S3) corren en `asyncio.to_thread()` para no bloquear el event loop.
2. La rotación jamás borra filas sin copiarlas al archive primero.
3. Si un backup S3 falla, la DB operativa no se ve afectada (el backup es idempotente y atómico).

## Decisiones arquitectónicas relevantes

- ADR-0006: migraciones en modo híbrido (`create_all()` + `alembic stamp head`).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.7 (Persistencia completa).
