# METRICS_FILE_SPEC.md — Schema del archivo de métricas de fixture

> **Propósito de este documento:** definir el formato exacto del archivo `.metrics.json` que acompaña a cada fixture del sistema. Este archivo contiene **exclusivamente métricas de calibración** — la evidencia empírica que justifica los pesos y umbrales de esa fixture. Es consumido por el dashboard del scanner live (memento) para mostrar uniformemente el desempeño de cualquier fixture cargada.
>
> **Cuándo consultarlo:** al generar métricas para una fixture nueva o recalibrada. Al implementar el componente del dashboard que renderiza métricas. Al diagnosticar por qué el memento no muestra datos para un ticker.
>
> **Cuándo NO consultarlo:** para métricas runtime del scanner live (señales del día, WR en vivo). Esas pertenecen a otro módulo y tienen su propio formato. Este doc es solo para métricas de calibración.

**Versión de este documento:** 1.0.0 · **Schema del archivo descrito:** 1.0.0

---

## 1 · Rol del archivo en el sistema

Cada fixture del sistema (canonical, activa, experimental) tiene un archivo `.metrics.json` asociado que vive al lado en el filesystem:

```
fixtures/
  qqq_canonical_v1.json           ← configuración (leído por el motor)
  qqq_canonical_v1.sha256          ← hash
  qqq_canonical_v1.metrics.json    ← métricas (leído por el dashboard)
  qqq_canonical_v1.calibration.md  ← reporte humano
  qqq_v5_2_0.json                  ← activa
  qqq_v5_2_0.metrics.json          ← métricas de la activa
  ...

sandbox/
  nvda_canonical_v2_CANDIDATE.json
  nvda_canonical_v2_CANDIDATE.metrics.json
```

**Regla:** siempre que exista una fixture `{nombre}.json`, debe existir `{nombre}.metrics.json` asociado. La generación NO es opcional — es parte obligatoria del proceso de crear una fixture (ver `CALIBRATION_METHODOLOGY.md` sección actualizada).

### 1.1 Qué contiene y qué NO

**Contiene:**
- Métricas de la calibración (spread, WR por franja, MFE/MAE, coverage)
- Metadata de la calibración (período, dataset, warnings)
- Referencia al reporte humano `.calibration.md`

**NO contiene:**
- Métricas runtime del scanner live (señales del día, drawdown actual)
- Información de configuración (pesos, umbrales, franjas) — eso está en el `.json` de la fixture
- Time series de desempeño histórico — ese es trabajo de otro módulo

Separar estos dos tipos de métricas es deliberado. Las de calibración son **inmutables con la fixture**; las runtime son volátiles y viven en la DB operativa del scanner.

### 1.2 Inmutabilidad relativa

- Si la fixture asociada es **canonical**, el `.metrics.json` también es inmutable. Cambia solo cuando se genera un nuevo canonical.
- Si la fixture es **activa** o **experimental**, el `.metrics.json` puede regenerarse si se reprocesa la data con mejores replays. En la práctica se hace rara vez — típicamente el `.metrics.json` se genera una vez al crear la fixture y no se toca.

El `.metrics.json` **no se hashea**. Solo el `.json` de configuración tiene `.sha256` asociado.

---

## 2 · Ejemplo canónico completo

Este es el `.metrics.json` que correspondería al canonical QQQ actual:

```json
{
  "schema_version": "1.0.0",
  "fixture_ref": {
    "fixture_id": "qqq_canonical_v1",
    "fixture_version": "5.2.0",
    "fixture_type": "canonical",
    "file_hash_sha256": "3f2a7b8c9e4d1a2b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b"
  },
  "calibration_status": "final",
  "generated_at": "2026-04-18T00:00:00Z",
  "generated_by": "Signal Observatory Fase 2 Paso 4 + Paso 5",

  "dataset": {
    "ticker": "QQQ",
    "benchmark": "SPY",
    "training_start": "2023-03-15",
    "training_end": "2025-03-14",
    "training_months": 24,
    "training_sessions": 515,
    "training_signals_total": 4383,
    "oos_start": "2025-03-15",
    "oos_end": "2026-03-14",
    "oos_months": 12,
    "oos_sessions": 258,
    "oos_signals_total": 2136
  },

  "metrics_training": {
    "spread_b_to_splus_pp": 24.2,
    "progression_monotonic": true,
    "by_band": {
      "REVISAR": { "n": 1082, "wr_pct": 50.9, "mfe_mae": 0.80 },
      "B":       { "n": 1621, "wr_pct": 48.5, "mfe_mae": 0.86 },
      "A":       { "n": 1182, "wr_pct": 54.9, "mfe_mae": 1.19 },
      "A_plus":  { "n":  453, "wr_pct": 59.5, "mfe_mae": 1.39 },
      "S":       { "n":   34, "wr_pct": 60.8, "mfe_mae": 1.51 },
      "S_plus":  { "n":   11, "wr_pct": 72.7, "mfe_mae": 1.38 }
    },
    "confirms": {
      "FzaRel":   { "coverage_pct": 21.3, "uplift_pp": 12.0 },
      "BBinf_1H": { "coverage_pct": 15.8, "uplift_pp":  5.3 },
      "VolHigh":  { "coverage_pct": 28.4, "uplift_pp":  3.2 },
      "Gap":      { "coverage_pct":  8.2, "uplift_pp":  1.3 },
      "BBsup_1H": { "coverage_pct": 14.1, "uplift_pp":  0.7 },
      "BBinf_D":  { "coverage_pct":  4.3, "uplift_pp":  0.6 },
      "BBsup_D":  { "coverage_pct":  3.9, "uplift_pp":  0.0 },
      "DivSPY":   { "coverage_pct":  2.1, "uplift_pp":  0.0 },
      "VolSeq":   { "coverage_pct": 18.6, "uplift_pp": -1.8 },
      "SqExp":    { "coverage_pct":  6.5, "uplift_pp": -4.3 }
    }
  },

  "metrics_oos": {
    "spread_b_to_splus_pp": 21.8,
    "progression_monotonic": true,
    "by_band": {
      "REVISAR": { "n": 529, "wr_pct": 49.3, "mfe_mae": 0.78 },
      "B":       { "n": 792, "wr_pct": 47.1, "mfe_mae": 0.84 },
      "A":       { "n": 577, "wr_pct": 53.2, "mfe_mae": 1.15 },
      "A_plus":  { "n": 221, "wr_pct": 57.9, "mfe_mae": 1.33 },
      "S":       { "n":  17, "wr_pct": 58.8, "mfe_mae": 1.44 },
      "S_plus":  { "n":   0, "wr_pct": null, "mfe_mae": null }
    },
    "confirms": {
      "FzaRel":   { "coverage_pct": 22.1, "uplift_pp": 10.8 },
      "BBinf_1H": { "coverage_pct": 16.2, "uplift_pp":  4.7 },
      "VolHigh":  { "coverage_pct": 27.9, "uplift_pp":  2.9 },
      "Gap":      { "coverage_pct":  7.8, "uplift_pp":  1.1 },
      "BBsup_1H": { "coverage_pct": 13.6, "uplift_pp":  0.4 },
      "BBinf_D":  { "coverage_pct":  4.1, "uplift_pp":  0.3 },
      "BBsup_D":  { "coverage_pct":  3.7, "uplift_pp": -0.2 },
      "DivSPY":   { "coverage_pct":  1.9, "uplift_pp":  0.1 },
      "VolSeq":   { "coverage_pct": 19.0, "uplift_pp": -2.0 },
      "SqExp":    { "coverage_pct":  6.1, "uplift_pp": -3.9 }
    }
  },

  "thresholds_check": {
    "spread_min_met": true,
    "wr_a_min_met": true,
    "wr_a_plus_min_met": true,
    "wr_s_min_met": true,
    "wr_s_plus_min_met": true,
    "progression_monotonic_met": true,
    "n_a_plus_min_met": true,
    "n_s_splus_min_met": true,
    "all_mandatory_met": true
  },

  "calibration_process": {
    "iterations_count": 7,
    "warnings_raised": [],
    "force_promoted": false,
    "report_md_path": "fixtures/qqq_canonical_v1.calibration.md"
  }
}
```

---

## 3 · Descripción de campos

### 3.1 Bloque raíz

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `schema_version` | string | Sí | Semver del schema del `.metrics.json`. Hoy `"1.0.0"` |
| `fixture_ref` | object | Sí | Identifica la fixture a la cual pertenecen estas métricas (sección 3.2) |
| `calibration_status` | string | Sí | `"final"`, `"partial"`, `"placeholder"` (sección 3.3) |
| `generated_at` | string ISO 8601 | Sí | Timestamp UTC de generación |
| `generated_by` | string | No | Qué proceso o persona generó las métricas |
| `dataset` | object | Sí | Descripción del dataset usado (sección 3.4) |
| `metrics_training` | object | Sí | Métricas sobre período training (sección 3.5) |
| `metrics_oos` | object \| null | Sí | Métricas sobre out-of-sample. `null` si la fixture es `partial` |
| `thresholds_check` | object | Sí | Resultado de chequeo contra thresholds mínimos (sección 3.6) |
| `calibration_process` | object | Sí | Metadata del proceso (sección 3.7) |

### 3.2 Bloque `fixture_ref`

| Campo | Tipo | Descripción |
|---|---|---|
| `fixture_id` | string | Mismo `fixture_id` del metadata de la fixture asociada |
| `fixture_version` | string | Mismo `fixture_version` |
| `fixture_type` | string | `"canonical"`, `"active"`, `"experimental"`, `"candidate"` |
| `file_hash_sha256` | string | Hash del archivo `.json` de la fixture al momento de generar las métricas. Permite detectar desincronización si la fixture se modifica y las métricas quedaron viejas |

### 3.3 Campo `calibration_status`

Tres valores posibles:

- **`"final"`** — métricas completas con validación out-of-sample. `metrics_oos` no es null. Típico de canonicals aprobados
- **`"partial"`** — solo métricas training, sin validación out-of-sample. `metrics_oos` es null. Típico de experimentales durante iteración
- **`"placeholder"`** — métricas heredadas de otra fixture (ej. una activa nueva que todavía no fue calibrada sobre su propio ticker). Ambos bloques de métricas son null o contienen valores importados con nota

El dashboard muestra un badge distinto según el status, para que el trader sepa qué tan confiables son las métricas.

### 3.4 Bloque `dataset`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ticker` | string | Sí | Ticker de las métricas |
| `benchmark` | string \| null | Sí | Benchmark usado en la calibración |
| `training_start` | string YYYY-MM-DD | Sí | Primer día de training |
| `training_end` | string YYYY-MM-DD | Sí | Último día de training |
| `training_months` | integer | Sí | Número aproximado de meses de training |
| `training_sessions` | integer | Sí | Número de sesiones de mercado en training |
| `training_signals_total` | integer | Sí | Número total de señales generadas en training |
| `oos_start` | string \| null | Sí | Primer día de out-of-sample. Null si status `partial` |
| `oos_end` | string \| null | Sí | Último día de out-of-sample |
| `oos_months` | integer \| null | Sí | Meses de out-of-sample |
| `oos_sessions` | integer \| null | Sí | Sesiones en out-of-sample |
| `oos_signals_total` | integer \| null | Sí | Señales totales en out-of-sample |

### 3.5 Bloques `metrics_training` y `metrics_oos`

Ambos tienen la misma estructura:

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `spread_b_to_splus_pp` | float | Sí | Spread de WR entre banda B y S+ en puntos porcentuales. Métrica de separación principal |
| `progression_monotonic` | boolean | Sí | True si WR es creciente estrictamente de B a S+ (sin inversiones entre bandas consecutivas) |
| `by_band` | object | Sí | Métricas por cada franja. Keys: `"REVISAR"`, `"B"`, `"A"`, `"A_plus"`, `"S"`, `"S_plus"` |
| `confirms` | object | Sí | Coverage y uplift de cada confirm |

**Objeto de cada banda en `by_band`:**

| Campo | Tipo | Descripción |
|---|---|---|
| `n` | integer | Número de señales que cayeron en esta banda |
| `wr_pct` | float \| null | Win rate a 30 minutos, en porcentaje. Null si `n` es 0 |
| `mfe_mae` | float \| null | Ratio MFE/MAE promedio. Null si `n` es 0 |

**Objeto de cada confirm en `confirms`:**

| Campo | Tipo | Descripción |
|---|---|---|
| `coverage_pct` | float | Porcentaje de señales operables que tienen este confirm presente |
| `uplift_pp` | float | Diferencia en puntos porcentuales de WR entre señales con y sin el confirm |

Las 10 categorías de confirm (del `FIXTURE_SPEC.md` sección 3.3) deben estar presentes siempre. Omitir una es `MET-003`.

### 3.6 Bloque `thresholds_check`

Chequeo automático contra los thresholds mínimos de `CALIBRATION_METHODOLOGY.md` sección 7:

| Campo | Tipo | Descripción |
|---|---|---|
| `spread_min_met` | boolean | Spread ≥ +10pp |
| `wr_a_min_met` | boolean | WR en A ≥ 52% |
| `wr_a_plus_min_met` | boolean | WR en A+ ≥ 55% |
| `wr_s_min_met` | boolean | WR en S ≥ 58% (null si N<20 en S) |
| `wr_s_plus_min_met` | boolean | WR en S+ ≥ 62% (null si N<5 en S+) |
| `progression_monotonic_met` | boolean | Progresión monótona en training y oos |
| `n_a_plus_min_met` | boolean | N en A+A+ ≥ 300 |
| `n_s_splus_min_met` | boolean | N en S+S+ ≥ 20 |
| `all_mandatory_met` | boolean | True solo si todos los obligatorios son true (incluye training y oos si status es `final`) |

El dashboard usa `all_mandatory_met` para el indicador principal de salud de la fixture.

### 3.7 Bloque `calibration_process`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `iterations_count` | integer | Sí | Número de iteraciones del ciclo de calibración |
| `warnings_raised` | array of string | Sí | Lista de códigos CAL-XXX warnings que se emitieron durante la calibración (CAL-002, CAL-100) |
| `force_promoted` | boolean | Sí | Si el canonical fue promovido con flag `force: true` (ignorando warnings críticos) |
| `report_md_path` | string \| null | Sí | Path al reporte humano `.calibration.md`. Null si no hay reporte (ej. placeholder) |

---

## 4 · Validación del archivo

El dashboard (y cualquier consumer del `.metrics.json`) valida el archivo al cargarlo. Los errores son de la familia `MET-XXX`:

### MET-001 · Archivo no encontrado
Cuando una fixture existe pero no tiene `.metrics.json` asociado.

### MET-002 · JSON inválido o schema roto
Campos obligatorios faltantes, tipos incorrectos.

### MET-003 · Confirms incompletos
Alguna de las 10 categorías de confirms no aparece en `confirms`.

### MET-004 · Status inconsistente
`calibration_status: "final"` pero `metrics_oos: null`, o combinaciones similares que violan la semántica.

### MET-005 · Hash desincronizado
`file_hash_sha256` en `fixture_ref` no matchea el hash actual del `.json` de la fixture. Indica que las métricas son viejas — la fixture fue modificada sin regenerar métricas. Warning, no crítico.

### MET-006 · Thresholds inválidos
`thresholds_check.all_mandatory_met: true` pero algún threshold individual es false. Inconsistencia interna del archivo.

**Comportamiento:** errores `MET-001` a `MET-004` impiden que el dashboard muestre métricas (muestra estado "datos no disponibles"). `MET-005` se muestra como warning pero los datos se presentan igual.

Estos códigos se agregan al `FIXTURE_ERRORS.md` en su próxima actualización.

---

## 5 · Generación del archivo

El `.metrics.json` se genera automáticamente por el proceso de calibración. Nunca a mano.

### 5.1 Momento de generación

- Al completar una iteración de calibración → genera `.metrics.json` con `calibration_status: "partial"` (training-only)
- Al pasar la validación out-of-sample → regenera con `calibration_status: "final"` y `metrics_oos` completo
- Al hacer `propose` del canonical manager → copia las métricas de la experimental al candidato
- Al hacer `promote` del canonical manager → mueve el `.metrics.json` junto con el `.json` a `fixtures/`

### 5.2 Placeholder para fixtures heredadas

Si se crea una fixture activa copiando valores del canonical QQQ para un ticker que aún no tiene calibración propia (ej. placeholder inicial de AMZN), el `.metrics.json` asociado se crea con:

```json
{
  "schema_version": "1.0.0",
  "fixture_ref": { ... },
  "calibration_status": "placeholder",
  "generated_at": "2026-04-18T00:00:00Z",
  "generated_by": "placeholder — valores heredados de qqq_canonical_v1",
  "dataset": null,
  "metrics_training": null,
  "metrics_oos": null,
  "thresholds_check": { "all_mandatory_met": false, ... todos false ... },
  "calibration_process": {
    "iterations_count": 0,
    "warnings_raised": ["placeholder — sin calibración empírica"],
    "force_promoted": false,
    "report_md_path": null
  }
}
```

El dashboard muestra este estado como "sin calibración" y sugiere agendar Fase 4 para ese ticker.

---

## 6 · Consumo desde el dashboard (memento)

El dashboard lee el `.metrics.json` al cargar la vista del slot correspondiente. Renderiza:

- **Header:** nombre del ticker + status badge (final / partial / placeholder)
- **Spread principal:** spread_b_to_splus_pp de training
- **Tabla de franjas:** N, WR, MFE/MAE por cada banda, comparando training vs oos si está disponible
- **Lista de confirms:** ordenada por uplift descendente, destacando los de uplift negativo en rojo
- **Thresholds check:** lista de verificaciones con íconos de cumplimiento
- **Info de calibración:** iterations_count, warnings, link al reporte md si existe
- **Dataset info:** período, total de señales

El dashboard NO calcula ninguna métrica — solo renderiza las que están en el archivo. Si una métrica no está o es null, se muestra "—" o placeholder visual.

---

## 7 · Versionado del schema

El `.metrics.json` tiene su propio `schema_version` independiente de la fixture y del motor.

**MAJOR** del schema: cambio incompatible en la estructura. El dashboard tendrá que actualizar su parser.

**MINOR**: campo opcional nuevo. Dashboards viejos lo ignoran.

**PATCH**: bug fix del spec sin cambio estructural.

Cuando el scanner live arranca, si encuentra un `.metrics.json` con `schema_version` fuera del rango soportado, emite `MET-004` y trata la fixture como "métricas no disponibles" (pero la fixture en sí sigue funcionando — las métricas son solo para display).

---

## 8 · Referencias

- `FIXTURE_SPEC.md` — fixture a la que estas métricas pertenecen
- `CALIBRATION_METHODOLOGY.md` — proceso que genera las métricas. La sección de cierre de calibración se actualiza para incluir generación del `.metrics.json` como paso obligatorio
- `CANONICAL_MANAGER_SPEC.md` — mueve las métricas junto con el canonical durante `promote`
- `FIXTURE_ERRORS.md` — códigos `MET-XXX` documentados ahí

---

## 9 · Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0.0 | 2026-04-18 | Documento inicial. Schema v1.0.0 definido. Generación obligatoria para toda fixture. Métricas fijas estándar |
