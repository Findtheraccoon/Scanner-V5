# Slot Registry Module

**Tipo:** módulo consultado por otros componentes.
**Estado:** pendiente de implementación.

## Rol

Contiene la topología operativa del sistema: los 6 slots con su ticker + fixture + benchmark. Es consultado por el Scoring Engine en cada ciclo AUTO para saber qué correr.

## Responsabilidades

- Cargar y validar `slot_registry.json` al arranque (codigos `REG-*`).
- Verificar hash SHA-256 de canonicals referenciados (`REG-020`).
- Exponer API de consulta (qué slots están operativos, qué ticker/fixture tiene cada uno).
- Aceptar hot-reload de slot individual sin reiniciar el backend.
- Emitir evento `slot.status` ante cambios de estado.

## Invariantes

1. **Exactamente 6 slots** — cardinalidad fija de producto.
2. **Mínimo 1 slot activo** — no se permite desactivar el último activo (validación frontend + backend).
3. **Consulta sin cache** — el Scoring Engine consulta el Registry en cada scan, fuente de verdad única (Opción A del spec).
4. **Atomicidad por slot** — un slot con fixture inválida queda DEGRADED; los otros 5 siguen. Cero slots válidos → abort fatal.

## Hot-reload (desvío del spec original)

El scanner v5 live **soporta hot-reload por slot**, contra el spec original que decía "no hay hot-reload en v5.x". Flujo en 5 pasos:

1. Trader introduce ticker + fixture en Paso 3 Config.
2. Slot Registry emite señal al Data Engine solicitando fetch.
3. Data Engine descarga warmup (consultando DB local primero — ADR-0003).
4. Slot queda en estado WARMUP mientras baja; otros 5 siguen operando.
5. Al completar descarga + validación → slot operativo.

## Contratos con otros componentes

- **Consume:** fixtures del módulo de filesystem (canonicals + activas del Config).
- **Provee:** lookup de slot → (ticker, fixture, benchmark) al Scoring Engine.
- **Emite eventos WebSocket:** `slot.status` con `warmup_progress` incluido.

## Referencias

- `docs/specs/SLOT_REGISTRY_SPEC.md` — schema y reglas de validación.
- `docs/operational/FEATURE_DECISIONS.md` §3.3 (Slot Registry en scanner live + hot-reload).
- `docs/operational/FEATURE_DECISIONS.md` §11 item 1 (hot-reload como desvío explícito).
