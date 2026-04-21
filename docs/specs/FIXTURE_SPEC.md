# FIXTURE_SPEC.md — Schema de una fixture de ticker

> **Propósito de este documento:** definir el formato exacto de una fixture JSON. Una fixture es el archivo de configuración que le dice al motor qué pesos, umbrales y franjas usar para un ticker específico. Este doc es el source of truth para armar una fixture a mano o programáticamente — cualquier divergencia entre este doc y lo que acepta el loader es un bug.
>
> **Cuándo consultarlo:** para armar una fixture nueva. Para entender qué significa cada campo. Para interpretar un error de validación del loader.
>
> **Cuándo NO consultarlo:** para saber qué hace el motor con los valores (usar `SCORING_ENGINE_SPEC.md`). Para decidir qué valores poner en una fixture de un ticker nuevo (usar `CALIBRATION_METHODOLOGY.md`). Para resolver errores específicos al cargar (usar `FIXTURE_ERRORS.md`).

**Versión de este documento:** 1.0.0 · **Schema de fixture descrito:** 5.0.0

---

## 1 · Anatomía de una fixture

Una fixture es un archivo JSON con 5 bloques de alto nivel:

```
fixture.json
├── metadata      (identidad, versionado, compatibilidad)
├── ticker_info   (qué ticker y benchmark aplica)
├── confirm_weights     (10 categorías — todas obligatorias)
├── detection_thresholds (umbrales de detección externalizados)
└── score_bands         (franjas de confianza)
```

El orden en el archivo no es significativo — el loader normaliza. Pero por convención se escriben en el orden listado arriba.

> **Nota sobre pesos de triggers:** esta versión del schema (5.0.0) NO externaliza los pesos de triggers. Los valores de los 14 patrones de trigger viven en `scanner/patterns.py` y son tratados por el motor como pesos crudos sin categorización. La decisión y su fundamento están en `SCORING_ENGINE_SPEC.md` sección 5.1. Cuando Fase 5+ justifique externalizar los triggers, será un MAJOR del motor (v6.0.0) y del schema de fixture (6.0.0).

---

## 2 · Ejemplo canónico completo

Esta es la fixture del baseline QQQ (calibrada en Fase 2, usada como canonical). Es el único archivo del tipo que está marcado como inmutable y que sirve como referencia para las demás:

```json
{
  "metadata": {
    "fixture_id": "qqq_v5_2_0",
    "fixture_version": "5.2.0",
    "engine_compat_range": ">=5.2.0,<6.0.0",
    "canonical_ref": "qqq_canonical_v1",
    "generated_at": "2026-04-18T00:00:00Z",
    "generated_from": "Fase 2 Paso 4 + Paso 5 (Sesion 4)",
    "description": "Baseline calibrado empíricamente sobre 6,519 señales QQQ (3 años)",
    "author": "Signal Observatory",
    "notes": "Spread B→S+ de +24.2pp verificado. No modificar sin replay completo."
  },
  "ticker_info": {
    "ticker": "QQQ",
    "benchmark": "SPY",
    "requires_spy_daily": true,
    "requires_bench_daily": true
  },
  "confirm_weights": {
    "FzaRel":   4,
    "BBinf_1H": 3,
    "BBsup_1H": 1,
    "BBinf_D":  1,
    "BBsup_D":  1,
    "VolHigh":  2,
    "VolSeq":   0,
    "Gap":      1,
    "SqExp":    0,
    "DivSPY":   1
  },
  "detection_thresholds": {
    "fzarel_min_divergence_pct":   0.5,
    "divspy_asset_threshold_pct":  0.5,
    "divspy_spy_threshold_pct":    0.3,
    "volhigh_min_ratio":           1.2
  },
  "score_bands": [
    { "min": 16.0, "max": null, "label": "S+",      "signal": "SETUP"   },
    { "min": 14.0, "max": 16.0, "label": "S",       "signal": "SETUP"   },
    { "min": 10.0, "max": 14.0, "label": "A+",      "signal": "SETUP"   },
    { "min":  7.0, "max": 10.0, "label": "A",       "signal": "SETUP"   },
    { "min":  4.0, "max":  7.0, "label": "B",       "signal": "REVISAR" },
    { "min":  2.0, "max":  4.0, "label": "REVISAR", "signal": "REVISAR" }
  ]
}
```

Ese archivo, palabra por palabra, es `qqq_canonical_v1.json`. El canonical no cambia; cuando Fase 4 o posterior proponga modificar pesos/umbrales de QQQ, se genera `qqq_canonical_v2.json` con tu aprobación previa y el actual queda como referencia histórica.

---

## 3 · Descripción de campos

### 3.1 Bloque `metadata`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `fixture_id` | string | Sí | Identificador único de la fixture. Convención: `{ticker}_v{MAJOR}_{MINOR}_{PATCH}` en snake_case. Se registra en cada señal generada para trazabilidad |
| `fixture_version` | string | Sí | Semver `MAJOR.MINOR.PATCH`. Qué cambia con cada incremento se define en sección 4 |
| `engine_compat_range` | string | Sí | Rango semver del motor con el que esta fixture es compatible. Formato estilo npm: `">=5.2.0,<6.0.0"`. El registry valida al cargar |
| `canonical_ref` | string | No | ID de la fixture canonical de la que deriva. Solo relevante si esta fixture no es la canonical |
| `generated_at` | string (ISO 8601) | Sí | Timestamp de creación. UTC |
| `generated_from` | string | No | Descripción corta de qué proceso generó la fixture (ej. "Fase 4 bottom-up + sign-off 2026-05-10") |
| `description` | string | Sí | Descripción humana corta. 1 línea |
| `author` | string | No | Quién la generó |
| `notes` | string | No | Observaciones adicionales libres |

### 3.2 Bloque `ticker_info`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ticker` | string | Sí | Símbolo del ticker. Mayúsculas. Debe matchear el `ticker` del slot del registry |
| `benchmark` | string \| null | Sí | Símbolo del benchmark usado para FzaRel. `null` si el ticker no tiene benchmark |
| `requires_spy_daily` | boolean | Sí | Si true, el motor exige `spy_daily` en la llamada. Típicamente `true` salvo fixtures experimentales sin DivSPY |
| `requires_bench_daily` | boolean | Sí | Si true, el motor exige `bench_daily`. Debe ser true si `benchmark` no es null |

Regla de consistencia: si `benchmark` es null, entonces `requires_bench_daily` debe ser false. Si es string, debe ser true. Violar esto produce `FIX-011` en validación.

### 3.3 Bloque `confirm_weights`

Diccionario `{categoría: peso}`. Las 10 categorías de confirms del motor (ver `SCORING_ENGINE_SPEC.md` sección 5.2) deben estar **todas presentes**. Omitir una es `FIX-003`. Agregar una que no exista en el motor es `FIX-005`.

| Campo | Tipo | Rango válido |
|---|---|---|
| Cada categoría | integer o float | `0 ≤ valor ≤ 10` |

Peso 0 significa "detectar pero no contar al score" (para dejar registro del patrón pero neutralizar su efecto). Por convención usar integer salvo que la calibración exija fracción. Pesos > 10 producen `FIX-006` (protección contra escalas accidentalmente rotas).

Los pesos de confirms son los que aplica el motor **después** de categorizar y deduplicar. El peso crudo que aparece en `patterns.py`/`engine.py` durante la detección es irrelevante para el score — el motor lee de la fixture al sumar, no a la detección (I6 del spec del motor).

### 3.4 Bloque `detection_thresholds`

Umbrales de detección externalizados. Son los números que afectan qué se detecta (no qué peso tiene lo detectado).

| Campo | Tipo | Rango válido | Descripción |
|---|---|---|---|
| `fzarel_min_divergence_pct` | float | `0.0 < v ≤ 5.0` | Divergencia porcentual mínima entre ticker y benchmark para detectar FzaRel. Típico 0.5 para high-corr, hasta 1.5 para low-corr |
| `divspy_asset_threshold_pct` | float | `0.0 < v ≤ 5.0` | Movimiento mínimo del ticker del día para detectar DivSPY |
| `divspy_spy_threshold_pct` | float | `0.0 < v ≤ 5.0` | Movimiento mínimo de SPY del día para detectar DivSPY |
| `volhigh_min_ratio` | float | `1.0 < v ≤ 5.0` | Ratio de volumen vs promedio para contar como VolHigh |

Estos 4 son los únicos umbrales de Nivel 2 externalizados en v5.0.0 de schema. El resto de umbrales del motor (bandas de VolMult, gate horario de ORB, conflict diff, pesos de triggers) son Nivel 3 — viven en código y requieren nuevo MAJOR del motor para cambiar.

### 3.5 Bloque `score_bands`

Array ordenado de objetos que definen las franjas de confianza. Ordenado **de mayor a menor** por `min` (la primera banda es S+, la última es REVISAR). El motor itera de arriba abajo y asigna la primera banda cuyo `min` el score satisfaga.

| Campo del objeto | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `min` | float | Sí | Score mínimo inclusivo para caer en esta banda |
| `max` | float \| null | Sí | Score máximo exclusivo. `null` solo para la banda superior |
| `label` | string | Sí | Nombre de la franja. Se loguea en la DB y se muestra en UI |
| `signal` | string | Sí | Tipo de señal. Valores válidos: `"SETUP"`, `"REVISAR"`, `"NEUTRAL"` |

Reglas de consistencia:

- Las bandas deben ser **contiguas** — el `min` de una debe igualar el `max` de la siguiente. Gap entre bandas produce `FIX-020`
- No puede haber **overlap** entre bandas. Overlap produce `FIX-021`
- Solo la banda superior puede tener `max: null`. Cualquier otra con `max: null` produce `FIX-022`
- La banda inferior debe tener `min ≥ 0`. Negativo produce `FIX-023`
- Los `label` deben ser únicos dentro del array. Duplicados producen `FIX-024`

En la práctica, las 6 bandas estándar son las del ejemplo canónico. Se pueden redefinir para experimentar, pero la recomendación es mantener la nomenclatura A/A+/S/S+ por compatibilidad con UI y documentación.

---

## 4 · Versionado de fixtures

### 4.1 Esquema semver

Las fixtures siguen `MAJOR.MINOR.PATCH`, alineado con el motor en su componente MAJOR para evitar confusión visual.

**MAJOR** (ej. 5.x.x → 6.0.0): cambios que rompen compatibilidad con motores anteriores. Típicamente disparado por un MAJOR del motor. Ejemplos:

- Agregar o quitar una categoría de la lista canónica (sección 5 del spec del motor)
- Cambiar el formato de un bloque de alto nivel (ej. `score_bands` pasa de array a dict)
- Renombrar un bloque

Una fixture `6.0.0` NO se carga en un motor con `FIXTURE_COMPAT_RANGE = ">=5.0.0,<6.0.0"`.

**MINOR** (ej. 5.0.0 → 5.1.0): cambios retrocompatibles en el schema. Ejemplos:

- Agregar un campo opcional al bloque `metadata` (ej. `calibration_dataset_hash`)
- Agregar un umbral opcional nuevo a `detection_thresholds` con valor default razonable

Una fixture `5.0.0` sigue siendo válida en motor que acepta `5.1.0`; el loader completa los campos nuevos con defaults.

**PATCH** (ej. 5.0.0 → 5.0.1): cambios que no tocan el schema, solo los valores. Ejemplos:

- Recalibración de pesos producto de Fase 4 (mismo schema, números distintos)
- Ajuste de un umbral tras hallazgo empírico
- Corrección de un typo en `description`

Un cambio de pesos/umbrales/bandas de una fixture QQQ es siempre PATCH desde la perspectiva de compatibilidad. Desde la perspectiva del trader es una recalibración y requiere nueva aprobación + posible nuevo canonical (ver sección 5).

### 4.2 Naming convention

El nombre del archivo matchea el `fixture_id` del metadata:

- `fixtures/qqq_v5_2_0.json` ← fixture activa
- `fixtures/qqq_canonical_v1.json` ← canonical inmutable (ver sección 5)
- `fixtures/qqq_canonical_v1.sha256` ← hash del canonical

Prohibido tener dos archivos con el mismo `fixture_id` en el directorio `fixtures/`. El loader produce `FIX-030` si detecta colisión.

---

## 5 · Canonicalidad

Una fixture canonical es un archivo inmutable que sirve como **referencia de verdad** para un ticker en un release dado. No puede modificarse; si hay que cambiar algo, se genera una nueva canonical con el siguiente número de versión.

### 5.1 Reglas duras

- Un canonical se identifica con el prefijo `{ticker}_canonical_v{N}` donde N es un entero incremental por ticker
- Junto a cada canonical vive un archivo `.sha256` con el hash SHA-256 del JSON exacto (incluyendo whitespace)
- Al arrancar el scanner, el sistema verifica los hashes de todos los canonicals referenciados por las fixtures activas. Si un hash no matchea, `REG-020` y arranque abortado
- Para generar una nueva canonical se requiere:
  1. Corrida de replay completa comparando con la canonical vigente
  2. Presentación del diff pesos/franjas + delta métricas (spread, WR por franja, etc.)
  3. Sign-off explícito del trader
  4. Una vez firmado, se genera el nuevo archivo `{ticker}_canonical_v{N+1}.json` y su `.sha256`. La canonical anterior permanece en el repo con estado "superseded" en el INDEX pero accesible

### 5.2 Relación entre canonical y fixture activa

La fixture activa de un ticker (`{ticker}_v{version}.json`) puede coincidir con la canonical o diferir. El metadata `canonical_ref` permite rastrear de cuál deriva.

Uso típico:

- **Operación normal:** fixture activa = canonical. `canonical_ref` apunta al canonical vigente
- **Experimentación (Fase 4 WIP):** fixture activa es una variante (`qqq_v5_2_1_experimental.json`) con otros pesos. Se usa en replays de prueba, nunca en producción hasta que se promueva a canonical

### 5.3 Flujo de aprobación de nuevo canonical

```
1. Calibración propone pesos nuevos → guardar en {ticker}_v5_X_Y_experimental.json
2. Correr replay con esa fixture → nueva DB observatory_{ticker}_v5_X_Y_exp.db
3. Script diff_canonical.py compara la experimental con la canonical vigente:
   - Tabla de pesos cambiados con delta
   - Tabla de WR por franja cambiada con delta
   - Spread B→S+ antes y después
   - Cobertura y uplift FzaRel antes y después
4. Trader revisa el diff
5. Si aprueba: el experimental se renombra a nuevo canonical (v{N+1}) y se genera el hash
6. La canonical vieja queda en el repo con nota "superseded por vN+1 el YYYY-MM-DD"
```

El script `diff_canonical.py` se crea junto con el refactor como utilidad del proceso de calibración.

---

## 6 · Ejemplos de fixtures inválidas

Para que el chat de porting / desarrollo pueda predecir qué va a rechazar el loader, acá ejemplos concretos de cada tipo de error común. Los códigos completos están en `FIXTURE_ERRORS.md`.

### 6.1 Campo obligatorio ausente

```json
{
  "metadata": {
    "fixture_version": "5.2.0"
    // falta fixture_id, engine_compat_range, description, generated_at
  },
  ...
}
```
→ `FIX-001: missing required field 'metadata.fixture_id'` (primer campo faltante detectado)

### 6.2 Categoría de confirm omitida

```json
{
  "confirm_weights": {
    "FzaRel": 4,
    "BBinf_1H": 3
    // faltan las otras 8 categorías
  },
  ...
}
```
→ `FIX-003: confirm_weights missing required category 'BBsup_1H' (and 7 more)`

### 6.3 Categoría desconocida

```json
{
  "confirm_weights": {
    "FzaRel": 4,
    "NuevoConfirmInventado": 2,
    ...
  }
}
```
→ `FIX-005: confirm_weights contains unknown category 'NuevoConfirmInventado'. Valid categories: [FzaRel, BBinf_1H, ...]`

### 6.4 Peso fuera de rango

```json
{
  "confirm_weights": {
    "FzaRel": 15,
    ...
  }
}
```
→ `FIX-006: confirm_weights.FzaRel value 15 out of range [0, 10]`

### 6.5 Score bands con gap

```json
{
  "score_bands": [
    { "min": 16, "max": null, "label": "S+", "signal": "SETUP" },
    { "min": 14, "max": 16,   "label": "S",  "signal": "SETUP" },
    { "min": 10, "max": 13,   "label": "A+", "signal": "SETUP" },
    { "min":  7, "max": 10,   "label": "A",  "signal": "SETUP" }
  ]
}
```
→ `FIX-020: score_bands are not contiguous. Gap between band 'S' (max=14) and band 'A+' (min=13, max=13)` *(esto ejemplifica tanto gap como overlap en un mismo caso)*

### 6.6 Bench flag inconsistente

```json
{
  "ticker_info": {
    "ticker": "SPY",
    "benchmark": null,
    "requires_bench_daily": true
  }
}
```
→ `FIX-011: ticker_info inconsistent. benchmark is null but requires_bench_daily is true`

---

## 7 · Plantilla para armar una fixture nueva

Para un ticker sin calibración propia, esta es la plantilla mínima. Los valores son los del canonical QQQ como starting point — la expectativa es que Fase 4+ los ajuste siguiendo el método de `CALIBRATION_METHODOLOGY.md`.

```json
{
  "metadata": {
    "fixture_id": "TICKER_v5_0_0",
    "fixture_version": "5.0.0",
    "engine_compat_range": ">=5.2.0,<6.0.0",
    "canonical_ref": null,
    "generated_at": "YYYY-MM-DDTHH:MM:SSZ",
    "generated_from": "plantilla inicial, pendiente calibración",
    "description": "Fixture placeholder para TICKER, usa valores de QQQ canonical",
    "author": "Signal Observatory",
    "notes": "Valores importados de qqq_canonical_v1. Requiere calibración propia antes de uso operativo."
  },
  "ticker_info": {
    "ticker": "TICKER",
    "benchmark": "BENCH_TICKER_OR_NULL",
    "requires_spy_daily": true,
    "requires_bench_daily": true
  },
  "confirm_weights": { "...": "copiar de qqq_canonical_v1.json" },
  "detection_thresholds": { "...": "copiar de qqq_canonical_v1.json" },
  "score_bands": [ "...": "copiar de qqq_canonical_v1.json" ]
}
```

---

## 8 · Referencias

- `SCORING_ENGINE_SPEC.md` — contrato del motor que consume la fixture (sección 5 define la lista canónica de categorías)
- `FIXTURE_ERRORS.md` — tabla completa de códigos de error al cargar una fixture
- `SLOT_REGISTRY_SPEC.md` — cómo el registry asigna fixtures a slots
- `CALIBRATION_METHODOLOGY.md` — método para determinar los valores de una fixture nueva

---

## 9 · Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0.0 | 2026-04-18 | Documento inicial. Schema de fixture v5.0.0 definido |
