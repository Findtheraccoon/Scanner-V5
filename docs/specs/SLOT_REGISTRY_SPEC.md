# SLOT_REGISTRY_SPEC.md — Schema del slot registry

> **Propósito de este documento:** definir el formato y las reglas del archivo `slot_registry.json`, que asigna los 6 slots del scanner v5 a tickers y fixtures. Es el único archivo de configuración que el scanner live lee al arrancar para saber qué corre en cada slot. Junto con las fixtures, define la "topología operativa" del sistema.
>
> **Cuándo consultarlo:** al diseñar la validación del registry en el backend. Al agregar, modificar o deshabilitar slots. Al debuggear un error de arranque relacionado con asignación de slots.
>
> **Cuándo NO consultarlo:** para entender una fixture específica (usar `FIXTURE_SPEC.md`). Para diagnosticar un error de carga (usar `FIXTURE_ERRORS.md`). Para entender qué hace el motor (usar `SCORING_ENGINE_SPEC.md`).

**Versión de este documento:** 1.0.0 · **Schema del registry descrito:** 1.0.0

---

## 1 · Rol del registry en el sistema

El `slot_registry.json` es **el único archivo que el scanner live lee al arrancar para decidir qué correr**. Sin el registry, el scanner no sabe:

- Qué tickers operar (los 6 configurados)
- Qué fixture corresponde a cada ticker (por slot)
- Qué benchmark corresponde a cada ticker
- Si su versión de motor es compatible con la topología configurada

El registry es la **frontera entre la infraestructura y la operación**. Lo que está dentro es runtime estable. Lo que está afuera (fixtures) es calibración mutable.

**Relación con los otros componentes:**

```
slot_registry.json
    ├── engine_version_required  →  valida contra Scoring Engine v5.X.Y
    ├── slot 1  →  ticker QQQ   →  fixture qqq_v5_2_0.json     →  canonical qqq_canonical_v1
    ├── slot 2  →  ticker SPY   →  fixture spy_v5_2_0.json     →  canonical spy_canonical_v1
    ├── ... (hasta slot 6)
    └── metadata (versión, fecha, firma opcional)
```

El registry NO contiene pesos, NO contiene umbrales, NO contiene lógica de scoring. Solo asigna.

---

## 2 · Ubicación y cardinalidad

### 2.1 Ubicación

El registry vive en la **raíz del repo** del scanner live:

```
/slot_registry.json
```

Esta es una decisión arquitectónica firme (Decisión A de la fase de diseño). NO se mueve a `scanner/config/` ni a ningún subdirectorio. Motivos:

- Es un archivo de despliegue, no un config de calibración
- Está al mismo nivel que `fixtures/`, que referencia
- Es el primer archivo que lee el backend al arrancar

### 2.2 Cardinalidad

**Exactamente 1 registry activo por deployment.** El scanner v5 NO soporta múltiples registries (ni versionado múltiple, ni modos de configuración). Si hay dos archivos que parecen registries, dispara `REG-001` o similar al arranque.

**Exactamente 6 slots por registry.** Este número es fijo en v5.x del scanner. Ver `SCANNER_V5_DEV_HANDOFF.md` sección 4.1.

---

## 3 · Ejemplo canónico completo

```json
{
  "registry_metadata": {
    "registry_version": "1.0.0",
    "engine_version_required": ">=5.2.0,<6.0.0",
    "generated_at": "2026-04-18T00:00:00Z",
    "generated_by": "Signal Observatory · setup inicial",
    "description": "Topología operativa del scanner v5 live",
    "notes": "Slot 6 reservado para uso futuro."
  },
  "slots": [
    {
      "slot":      1,
      "ticker":    "QQQ",
      "fixture":   "fixtures/qqq_v5_2_0.json",
      "benchmark": "SPY",
      "enabled":   true,
      "priority":  "primary",
      "notes":     "Baseline canonical. No modificar sin replay completo."
    },
    {
      "slot":      2,
      "ticker":    "SPY",
      "fixture":   "fixtures/spy_v5_2_0.json",
      "benchmark": "QQQ",
      "enabled":   true,
      "priority":  "secondary",
      "notes":     "Pendiente calibración Fase 4 (spread +12pp vs +24pp de QQQ)."
    },
    {
      "slot":      3,
      "ticker":    "IWM",
      "fixture":   "fixtures/iwm_v5_2_0.json",
      "benchmark": "DIA",
      "enabled":   true,
      "priority":  "secondary",
      "notes":     "Pendiente calibración Fase 4."
    },
    {
      "slot":      4,
      "ticker":    "AAPL",
      "fixture":   "fixtures/aapl_v5_2_0.json",
      "benchmark": "QQQ",
      "enabled":   true,
      "priority":  "secondary",
      "notes":     "Pendiente calibración Fase 4 (spread +26pp con fórmula QQQ, pero FzaRel no aporta)."
    },
    {
      "slot":      5,
      "ticker":    "NVDA",
      "fixture":   "fixtures/nvda_v5_2_0.json",
      "benchmark": "QQQ",
      "enabled":   true,
      "priority":  "secondary",
      "notes":     "Requiere calibración urgente. Spread invertido con fórmula QQQ (H-21)."
    },
    {
      "slot":      6,
      "ticker":    null,
      "fixture":   null,
      "benchmark": null,
      "enabled":   false,
      "priority":  null,
      "notes":     "Slot libre reservado para uso futuro."
    }
  ]
}
```

---

## 4 · Descripción de campos

### 4.1 Bloque `registry_metadata`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `registry_version` | string | Sí | Semver del schema del registry. Incrementa con cambios de formato, no con cambios de valores |
| `engine_version_required` | string | Sí | Rango semver del motor que este registry espera. Formato estilo npm: `">=5.2.0,<6.0.0"`. El backend valida al arranque (`REG-030`) |
| `generated_at` | string (ISO 8601) | Sí | Timestamp UTC de creación o última modificación significativa |
| `generated_by` | string | No | Quién o qué generó el registry (ej. "Álvaro 2026-05-10", "canonical_manager v1.0.3") |
| `description` | string | No | Descripción humana libre |
| `notes` | string | No | Observaciones adicionales |

**Nota sobre versionado:** el `registry_version` es independiente del `engine_version_required`. El registry tiene su propio ciclo:

- **MAJOR** del registry schema: cambios rompientes en el formato del JSON (agregar un bloque obligatorio, cambiar tipos, reorganizar estructura)
- **MINOR**: campos opcionales nuevos (backward compatible)
- **PATCH**: bug fixes del documento spec sin cambio de formato

Cambios en los **valores** (activar un slot, cambiar fixture, agregar ticker nuevo) NO son cambios de version del schema. Son modificaciones de contenido que se registran en `generated_at`.

### 4.2 Array `slots`

El registry tiene exactamente un campo `slots` que es un array de **exactamente 6 objetos**. Array con cardinalidad distinta produce `REG-003` al arranque.

### 4.3 Objeto slot

Cada objeto del array `slots` describe un slot. Los campos obligatorios dependen del valor de `enabled`:

**Si `enabled: true`** (slot activo):

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `slot` | integer | Sí | ID del slot entre 1 y 6. Único en el array |
| `ticker` | string | Sí | Símbolo del ticker en mayúsculas |
| `fixture` | string | Sí | Path relativo al repo de la fixture asignada |
| `benchmark` | string \| null | Sí | Símbolo del benchmark. Null solo si la fixture declara `requires_bench_daily: false` |
| `enabled` | boolean | Sí | Flag de activación |
| `priority` | string | No | `"primary"`, `"secondary"`, `"experimental"`. Solo informativo, no afecta motor |
| `notes` | string | No | Observaciones del operador |

**Si `enabled: false`** (slot libre):

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `slot` | integer | Sí | ID del slot entre 1 y 6 |
| `ticker` | null \| string | Sí | Debe ser null (convención). Ver regla de sección 5.3 |
| `fixture` | null \| string | Sí | Debe ser null |
| `benchmark` | null | Sí | Debe ser null |
| `enabled` | boolean | Sí | false |
| `priority` | null \| string | No | Típicamente null |
| `notes` | string | No | Explicación de por qué está libre |

---

## 5 · Reglas de validación

El loader del registry aplica las siguientes reglas al arranque. Cualquier violación dispara un código `REG-XXX` (ver `FIXTURE_ERRORS.md` sección 4) y el scanner no arranca.

### 5.1 Integridad estructural

1. El archivo `slot_registry.json` debe existir en la raíz del repo → si no, `REG-001`
2. Debe ser JSON válido → si no, `REG-002`
3. Debe tener exactamente los bloques `registry_metadata` y `slots` → ni más ni menos
4. `slots` debe tener exactamente 6 elementos → si no, `REG-003`

### 5.2 IDs de slot únicos y contiguos

5. Cada slot debe tener `slot` entre 1 y 6
6. Los 6 valores deben ser únicos (no repetidos) → `REG-004`
7. Los 6 valores deben cubrir el rango 1 a 6 sin saltos (1,2,3,4,5,6 en cualquier orden)

### 5.3 Consistencia de slot deshabilitado

8. Si `enabled: false`, los campos `ticker`, `fixture`, `benchmark` idealmente son null
9. Si `enabled: false` pero hay campos con valores, emite `REG-101` (warning, no crítico). Los valores se ignoran

### 5.4 Consistencia de slot habilitado

10. Si `enabled: true`, los campos `ticker`, `fixture` son obligatorios y no-null
11. El archivo `fixture` debe existir en el path especificado → si no, `REG-010`
12. La fixture debe cargarse y pasar todas las validaciones de `FIXTURE_SPEC.md` → si no, `FIX-XXX` correspondiente
13. El `ticker` del slot debe matchear el `ticker_info.ticker` de la fixture → si no, `REG-012`
14. El `benchmark` del slot debe matchear el `ticker_info.benchmark` de la fixture → si no, `REG-013`

### 5.5 Unicidad entre slots habilitados

15. Entre los slots con `enabled: true`, cada `ticker` debe ser único → si hay duplicados, `REG-005`

Notar: los paths de `fixture` **NO** tienen restricción de unicidad. Una misma fixture puede estar asignada a múltiples slots activos simultáneamente — típicamente para correr comparativos A/B o para tener dos tickers distintos con calibraciones idénticas.

### 5.6 Compatibility del motor

16. `registry_metadata.engine_version_required` debe incluir la versión actual del motor → si no, `REG-030`
17. Para cada fixture habilitada, su `engine_compat_range` también debe incluir la versión actual del motor → si no, `REG-011`

### 5.7 Hash de canonicals referenciados

18. Por cada fixture habilitada que declare `canonical_ref`, el archivo `fixtures/{canonical_ref}.json` debe existir
19. Debe haber un archivo sibling `fixtures/{canonical_ref}.sha256` con el hash guardado
20. El hash actual del canonical JSON debe matchear el hash guardado → si no, `REG-020` (crítico)

**Importante:** esta verificación solo aplica a los **canonicals referenciados**. No aplica a las fixtures activas ni a las experimentales. Ver `FIXTURE_ERRORS.md` sección 1.1 para contexto.

---

## 6 · Ejemplos de registries inválidos

### 6.1 Número incorrecto de slots

```json
{
  "registry_metadata": { ... },
  "slots": [
    { "slot": 1, ... },
    { "slot": 2, ... },
    { "slot": 3, ... },
    { "slot": 4, ... },
    { "slot": 5, ... }
  ]
}
```
→ `REG-003: slot_registry must have exactly 6 slots. Found 5`

### 6.2 IDs duplicados

```json
{
  "slots": [
    { "slot": 1, "ticker": "QQQ", ... },
    { "slot": 2, "ticker": "SPY", ... },
    { "slot": 3, "ticker": "IWM", ... },
    { "slot": 3, "ticker": "AAPL", ... },
    { "slot": 5, "ticker": "NVDA", ... },
    { "slot": 6, "enabled": false, ... }
  ]
}
```
→ `REG-004: duplicate slot id 3 in slot_registry.json`

### 6.3 Ticker duplicado entre slots activos

```json
{
  "slots": [
    { "slot": 1, "ticker": "QQQ", "fixture": "fixtures/qqq_v5_2_0.json", "enabled": true, ... },
    { "slot": 2, "ticker": "QQQ", "fixture": "fixtures/qqq_experimental.json", "enabled": true, ... },
    ...
  ]
}
```
→ `REG-005: ticker 'QQQ' assigned to multiple active slots: [1, 2]`

### 6.4 Fixture no encontrada

```json
{
  "slots": [
    { "slot": 3, "ticker": "IWM", "fixture": "fixtures/iwm_v6_0_0.json", "enabled": true, ... }
  ]
}
```
→ `REG-010: slot 3 references fixture 'fixtures/iwm_v6_0_0.json' but file does not exist`

### 6.5 Ticker del slot no matchea el de la fixture

```json
// En el registry:
{ "slot": 4, "ticker": "AAPL", "fixture": "fixtures/nvda_v5_2_0.json", "enabled": true }

// En fixtures/nvda_v5_2_0.json:
{ "ticker_info": { "ticker": "NVDA", ... } }
```
→ `REG-012: slot 4 declares ticker 'AAPL' but referenced fixture nvda_v5_2_0 has ticker 'NVDA'`

### 6.6 Engine version required no incluye motor actual

```json
{
  "registry_metadata": {
    "engine_version_required": ">=6.0.0,<7.0.0",
    ...
  }
}
// Motor actual: 5.2.0
```
→ `REG-030: registry requires engine in range '>=6.0.0,<7.0.0' but engine is 5.2.0`

---

## 7 · Operaciones típicas sobre el registry

Las siguientes operaciones son las que típicamente se hacen sobre el registry. Todas requieren editar el JSON y reiniciar el scanner (no hay hot-reload en v5.x).

### 7.1 Activar un slot libre

Supongamos que slot 6 está libre y se quiere activar AMZN con una fixture recién calibrada:

1. Crear la fixture `fixtures/amzn_v5_0_0.json` siguiendo `FIXTURE_SPEC.md`
2. Editar el registry:
   - Cambiar `"enabled": false` a `"enabled": true` en slot 6
   - Poner `"ticker": "AMZN"`, `"fixture": "fixtures/amzn_v5_0_0.json"`, `"benchmark": "QQQ"` (o el que corresponda)
3. Actualizar `registry_metadata.generated_at` y opcionalmente `generated_by`
4. Reiniciar el scanner
5. Verificar en los logs que el arranque de los 6 slots fue exitoso

### 7.2 Deshabilitar un slot sin eliminar su config

Si el trader quiere "pausar" un ticker pero mantener la config para reactivar después:

1. Cambiar solo `"enabled": true` a `"enabled": false` en el slot
2. Mantener `ticker`, `fixture`, `benchmark` con sus valores
3. Agregar una nota en `notes` explicando por qué se pausó
4. Reiniciar el scanner

El backend emitirá `REG-101` (warning) porque hay campos populated en slot deshabilitado, pero arrancará. Es un trade-off deliberado entre prolijidad y conveniencia operativa.

### 7.3 Cambiar la fixture activa de un ticker

Flujo típico durante calibración de Fase 4:

1. Crear la nueva fixture experimental `fixtures/nvda_v5_0_1_experimental.json`
2. En el registry, cambiar el campo `fixture` del slot de NVDA al nuevo path
3. Reiniciar el scanner
4. Observar el comportamiento del slot

Para volver atrás: apuntar de nuevo a la fixture anterior y reiniciar.

### 7.4 Promover una experimental a canonical

Flujo formal cuando una fixture experimental converge:

1. El proceso de canonical approval (ver `CANONICAL_MANAGER_SPEC.md`) genera `fixtures/nvda_canonical_v2.json` + su `.sha256`
2. Se crea una fixture activa `fixtures/nvda_v5_2_1.json` que referencia el nuevo canonical en su `canonical_ref`
3. En el registry, cambiar el `fixture` del slot de NVDA al path de la nueva activa
4. Actualizar `registry_metadata.generated_at`
5. Reiniciar el scanner
6. Validar que el hash check pase (`REG-020` no se dispara si el canonical está bien firmado)

### 7.5 Actualizar el motor a una nueva versión

Si el motor sube de `5.2.0` a `5.3.0` (MINOR compatible):

1. Actualizar el código del motor
2. El `engine_version_required` del registry probablemente ya incluye `5.3.0` (si era `">=5.2.0,<6.0.0"`)
3. Validar que todas las fixtures tengan `engine_compat_range` que incluya `5.3.0`
4. Reiniciar el scanner

Si el motor sube MAJOR (ej. `5.2.0` a `6.0.0`):

1. Actualizar el código del motor
2. Actualizar `engine_version_required` del registry a `">=6.0.0,<7.0.0"`
3. Regenerar TODAS las fixtures (v6.0.0 del schema probablemente rompe v5.x.x)
4. Proceso de re-canonicalización completo
5. Reiniciar el scanner

---

## 8 · Atomicidad del arranque

El backend del scanner live arranca con la siguiente secuencia:

```
1. Leer slot_registry.json
   └── Si falla → abort con REG-001 o REG-002

2. Validar estructura (sección 5.1, 5.2)
   └── Si falla → abort con REG-00X

3. Validar compatibility del motor (5.6 regla 16)
   └── Si falla → abort con REG-030

4. Para cada slot enabled:
   a. Cargar la fixture
   b. Validar contra schema de fixture
   c. Si referencia canonical, verificar hash
   d. Validar consistencia con el slot (ticker matchea, etc.)
   e. Validar unicidad de ticker/fixture entre slots habilitados

   Si falla algún slot:
   - Marcar el slot como DEGRADED
   - Loguear el error específico
   - Continuar con los otros slots

5. Si al menos 1 slot quedó funcional → arrancar scanner
   Si 0 slots quedaron funcionales → abort con error fatal
```

El sistema **no es transaccional**: no "deshace" slots ya cargados si uno posterior falla. Cada slot se evalúa independientemente. Esto implementa la redundancia #4 (fallback graceful).

**Los errores de las secciones 5.1-5.3 y 5.6 regla 16 son fatales** (abort completo). Los de 5.4-5.5 y 5.6 regla 17 son por-slot (DEGRADED). `REG-020` (hash) también es fatal porque implica un canonical corrupto o modificado sin aprobación.

---

## 9 · Referencias

- `FIXTURE_SPEC.md` — schema de las fixtures que el registry referencia
- `FIXTURE_ERRORS.md` — catálogo de errores. `REG-XXX` documentados en sección 4, `FIX-XXX` en sección 2
- `SCORING_ENGINE_SPEC.md` — el motor cuya versión el registry declara
- `CANONICAL_MANAGER_SPEC.md` — proceso que genera los canonicals a los que el registry apunta indirectamente (vía `canonical_ref` de las fixtures)
- `SCANNER_V5_DEV_HANDOFF.md` — contexto general del sistema

---

## 10 · Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0.0 | 2026-04-18 | Documento inicial. Schema del registry v1.0.0 definido. 6 slots fijos, validación al arranque en 8 secciones |
