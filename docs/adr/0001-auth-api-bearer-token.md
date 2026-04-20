# ADR-0001: Autenticación API mediante bearer token autogenerado y encriptado en Config

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

El Scanner v5 expone dos superficies de red: REST HTTP (`/api/v1/*`) y WebSocket. Ambas sirven al frontend local y, eventualmente, a clientes externos (una Chrome extension futura, scripts de automatización del trader, etc.). La decisión original del proyecto era exponer el backend en `127.0.0.1` sin autenticación, asumiendo que el único consumidor sería el frontend empaquetado junto al backend.

Ese modelo tenía dos problemas:

1. El producto se distribuye mediante `.exe` Windows con Inno Setup, instalable en máquinas que el trader comparte con otras personas (oficina, casa). Sin auth, cualquier proceso corriendo en la misma máquina puede tumbar el scanner o leer señales.
2. Cierra la puerta a integraciones futuras que el propio Álvaro ya mencionó (consumidores externos al frontend principal).

Los 3 docs operativos vivos del proyecto (`FEATURE_DECISIONS.md`, `FRONTEND_FOR_DESIGNER.md`, `HANDOFF_CURRENT.md`) no tenían decisión explícita sobre autenticación hasta esta sesión. Se resuelve acá como parte del barrido de backend del 20-abril.

## Decisión

El backend del Scanner v5 implementa **autenticación obligatoria mediante API Key tipo bearer token** en todas las superficies de red públicas:

1. **REST:** header `Authorization: Bearer sk-...` en cada request. Ausencia o mismatch → HTTP 401.
2. **WebSocket:** query param `?token=sk-...` en el handshake inicial. Ausencia o mismatch → close code 4001.

El token se **autogenera al primer arranque** del backend (random secure, formato `sk-{32-40 caracteres hex}`) y se muestra una sola vez al trader en la UI de Configuración al completar el Paso 4 (arranque de motores), con botón "Copiar".

**Persistencia:** el token se guarda **encriptado dentro del Config del usuario**, junto con API keys del provider y credenciales S3 (mismo mecanismo de encripción).

**Rotación:** botón "Rotar token" en el Dashboard genera un nuevo token, invalida el anterior inmediatamente y fuerza al frontend a re-autenticarse (recarga).

**Cardinalidad:** un solo token activo por deployment en v5 (producto single-user por diseño).

## Consecuencias

### Positivas

- El producto es seguro fuera de la caja, sin requerir configuración manual del trader.
- Adelanta integraciones externas futuras (Chrome extension, scripts) sin cambio de arquitectura.
- Rotación simple cuando el trader comparte la máquina o sospecha compromiso.
- Consistente con el resto de credenciales (API keys provider, S3) que ya viven encriptadas en Config.

### Negativas / trade-offs

- Un paso extra en el primer setup (el trader debe anotar el token). Mitigado con botón "Copiar" y mensaje claro en la UI.
- Si el trader pierde el Config y no recuerda el token, necesita reinstalar (acción destructiva: wipe de DB + Config). Aceptable porque el Config también tiene otras credenciales críticas.
- Alembic / scripts CLI que quieran conectar al backend necesitan el token.

### Neutras

- Implementación: FastAPI dependency injection resuelve auth en una función global; bajo esfuerzo.

## Alternativas consideradas

### Alternativa A: Token fijo en archivo `secret.key` creado al instalar, sin UI

Inno Setup generaría el token al instalar, lo escribiría a un archivo junto al binario. Sin UI, sin rotación.
**Por qué no:** peor UX (el trader no sabe dónde está el archivo), rotación requiere edición manual y reinicio, cualquier proceso con acceso de lectura al disco lo lee. Menor esfuerzo pero peor superficie de ataque.

### Alternativa B: Sin auth, backend solo en `127.0.0.1`

Asumir que la máquina del trader es un entorno de confianza.
**Por qué no:** máquinas compartidas son la norma, no la excepción. Rompe cualquier integración externa futura (Chrome extension, CLI). Deuda técnica asegurada.

### Alternativa C: OAuth2 / JWT con refresh

Token de corta duración + refresh; credenciales del trader en un flujo OAuth.
**Por qué no:** over-engineering brutal para single-user local. No hay identity provider, no hay multi-tenant, no hay ciclo de sesiones largas. Agrega complejidad sin beneficio.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §4.12 (Autenticación API) y §5.3 (Auth en protocolo).
- Esta decisión se tomó como parte del barrido backend del 20-abril; junto con ADR-0002 a ADR-0006 cierra los gaps de capa transversal antes de arrancar Capa 1.
