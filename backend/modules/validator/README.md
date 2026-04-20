# Validator Module

**Tipo:** módulo invocado (sin ciclo de vida propio).
**Estado:** pendiente de implementación.

## Rol

Orquestador de validación del sistema. No es motor — se invoca bajo demanda y ejecuta contratos de healthcheck/test que cada motor expone.

## Cuándo corre

1. **Al arrancar el sistema**, después de que los motores están activos (Paso 4 de Configuración).
2. **A demanda desde el Dashboard:**
   - Botón "Revalidar sistema completo".
   - Botón "Revalidar slot N" (automático tras hot-reload de fixture/ticker).
   - Botón "Test conectividad API".
3. **Tras hot-reload** de fixture o ticker, se ejecuta automáticamente sobre el slot afectado.

## Batería de 7 tests (orden D → A → B → C → E → F → G)

- **D — Diagnóstico de infraestructura** (DB accesible, filesystem escribible, motores vivos).
- **A — Validación de fixtures** (schema, campos obligatorios, rangos). Códigos `FIX-*`.
- **B — Validación de canonicals** (hash SHA-256). Código `REG-020`.
- **C — Validación del Slot Registry** (schema, consistencia). Códigos `REG-*`.
- **E — Test end-to-end** (usa flag `is_validator_test: true`, no contamina DB).
- **F — Parity test** contra canonical QQQ. Código `ENG-050` si difiere.
- **G — Healthcheck de conectividad externa** (Twelve Data, S3 si configurado).

## Severidades

- **Fatal:** sistema no puede operar; todos los slots afectados.
- **DEGRADED:** un slot específico no puede operar; los otros siguen.
- **Warning:** operable pero con advertencia.

## Contratos con otros componentes

- **Consume:** funciones expuestas por cada motor (healthcheck endpoints internos).
- **Provee:** reporte JSON al frontend (vía evento WebSocket `validator.progress`).
- **Escribe:** log TXT a `/LOG/` con retención de 5 días.

## Pendientes de resolver al implementar

- Dataset parity exhaustivo concreto (ventana QQQ específica — bloqueante).
- Formato del snapshot de referencia (`parity_reference/` — recomendación JSONL).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.2 (Validator Module completo).
- `docs/operational/FEATURE_DECISIONS.md` §9.2 (pendientes bloqueantes).
