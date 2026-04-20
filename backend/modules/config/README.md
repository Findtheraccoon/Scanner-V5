# Config Module

**Tipo:** módulo de carga/guardado de configuración del usuario.
**Estado:** pendiente de implementación.

## Rol

Manejo del archivo `config_*.json` del usuario. Serializa y deserializa todo el estado configurable del scanner.

## Qué contiene el Config

- API keys del provider (5 slots, encriptadas).
- Credenciales S3 (encriptadas).
- API bearer token del propio scanner (encriptado, ver ADR-0001).
- Fixtures activas por slot (serializadas dentro del Config — desvío #7).
- Path del último Config cargado (`last_config_path.txt` separado).
- Preferencias de UI.
- Estado del auto-arranque.

## Operaciones

- **Cargar / Guardar / Guardar como / LAST** (botones del Paso 1 de Configuración).
- **Auto-LAST al arrancar:** si existe LAST + está completo, el backend arranca motores hasta "operativo" saltando Paso 4.
- **Wipe de secretos en RAM** al shutdown.

## Peso estimado

- Fixture sola: ~1.5 KB por slot.
- 6 slots con fixtures: ~7-9 KB.
- Secrets encriptados: ~1.1 KB.
- Preferencias y metadata: ~800 bytes.
- **Total:** ~9-11 KB sin métricas, ~16-20 KB si el usuario serializa fixtures con sibling `.metrics.json`.

## Invariantes

1. Secretos (API keys provider, S3, bearer token) siempre encriptados inline.
2. El Config NO guarda la DB ni las velas — solo configuración.
3. Al abrir un Config inválido, el backend no arranca y devuelve error claro al frontend.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.5 (Fixtures + Config).
- `docs/operational/FEATURE_DECISIONS.md` §4.4 (Persistencia privada).
- `docs/operational/FEATURE_DECISIONS.md` §4.8 (Configuración — archivo JSON).
