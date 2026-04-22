# tests/ — Tests del motor v5

Contiene tests que validan que el motor de scoring v5 preserva comportamiento a través de cambios de código. El test principal es el **parity check** contra el canonical QQQ.

## Archivos

| Archivo | Tamaño | Rol |
|---|---|---|
| `parity_qqq_canonical.py` | 15 KB | Script ejecutable del test |
| `fixtures/parity_qqq_sample.json` | 390 KB | Golden reference: 245 señales esperadas con todos sus campos |
| `fixtures/parity_qqq_candles.db` | 10.6 MB | Dataset OHLC portable para correr el test sin la DB completa del observatorio |

## Qué contiene el dataset de candles (`parity_qqq_candles.db`)

SQLite file autocontenido con las OHLC mínimas para regenerar las señales del sample:

| Tabla | Contenido | Filas |
|---|---|---|
| `qqq_1min` | Candles 1-minuto de QQQ (warmup + sesiones target) | 96,562 |
| `qqq_daily` | Candles diarios de QQQ del mismo período | 249 |
| `spy_daily` | Candles diarios de SPY (para FzaRel y DivSPY) | 249 |
| `metadata` | Info del dataset: rango, propósito, hash del canonical | 16 |

**Rango de fechas:** `2024-11-03` a `2025-11-01`
- `2024-11-03` a `2025-01-01` → **warmup** (60 días calendario, ≈ 40 sesiones de mercado para MA200 daily + BBs)
- `2025-01-02` a `2025-10-31` → **30 sesiones target** (las que el sample mide)

**Tamaño comparado:**
- Observatorio completo (`data/qqq_1min.json`): ~30 MB, 3 años
- Esta DB portable: 10.6 MB, ~1 año

### Consultar la DB

```python
import sqlite3
conn = sqlite3.connect("tests/fixtures/parity_qqq_candles.db")
cur = conn.cursor()

# Todas las candles 1min de una sesión
cur.execute("""
    SELECT dt, o, h, l, c, v FROM qqq_1min
    WHERE substr(dt, 1, 10) = '2025-01-02'
    ORDER BY dt
""")

# Daily previo a una sesión
cur.execute("""
    SELECT dt, o, h, l, c, v FROM qqq_daily
    WHERE dt < '2025-01-02' ORDER BY dt DESC LIMIT 40
""")
```

## Qué valida el parity check

El test compara bit-por-bit lo que el motor genera **hoy** contra lo que generó cuando se aprobó el canonical. Esto garantiza que ningún refactor del código rompe paridad con la fixture canonical QQQ.

Por cada una de las 245 señales del sample, verifica:

- Mismo `score` (con tolerancia de 0.01)
- Mismo `confidence` (franja)
- Mismo `direction` (CALL/PUT)
- Mismo `alignment` (n + dir)
- Mismos `trends` (t15m, t1h, tdaily)
- Mismo `structure.pass` y `structure.override`
- Mismo `trigger_count`, `trigger_sum`, `confirm_sum`
- Mismo `conflict_blocked`
- Mismos `components` detectados (category + description + weight)

También verifica que no haya señales extra en la DB generada que no estén en el reference, o ausentes.

## Cuándo correrlo

**Obligatorio antes de:**
- Aprobar cualquier PR que toque `scanner/engine.py`, `scanner/scoring.py`, `scanner/patterns.py`, o `scanner/indicators.py`
- Implementar el refactor plug-and-play (validar que externalizar pesos de confirms + umbrales + franjas no rompe paridad)
- Cualquier merge a la rama principal

**Recomendado:**
- Después de actualizar dependencias (cambios de versión de Python, librerías numéricas)
- Al migrar entre entornos (local → CI/CD)

**Innecesario:**
- En cambios puramente cosméticos (comentarios, renames sin cambio de lógica)
- En cambios a `analysis/` o `backtest/` que no tocan el motor

## Cómo correrlo

### Opción A — usar la DB completa del observatorio (comparación rápida)

Si ya tenés `observatory_v5_2.db` en la raíz del repo (típico si trabajás en el observatorio):

```bash
python3 tests/parity_qqq_canonical.py
```

El script lee directamente de `observatory_v5_2.db` las señales actuales y las compara con el sample. **No regenera señales** — asume que la DB ya tiene el output del motor a testear.

### Opción B — regenerar señales desde el dataset portable (test completo del refactor)

Si refactoreaste el motor y querés verificar paridad end-to-end, necesitás:

1. Leer candles desde `tests/fixtures/parity_qqq_candles.db`
2. Correr tu motor refactoreado sobre cada sesión target
3. Guardar las señales generadas en una DB con el schema de observatory (`signals` + `signal_components`)
4. Correr el parity check apuntando a tu nueva DB:

```bash
python3 tests/parity_qqq_canonical.py --db tu_nueva_db.db
```

Este es el caso de uso principal cuando el chat del scanner v5 implementa el motor desde cero.

### Exit codes

| Code | Significado |
|---|---|
| 0 | PARITY OK — 0 diferencias. El motor matchea el reference |
| 1 | PARITY FAIL — hay diferencias. El script imprime el diff detallado |
| 2 | Error de setup — DB no encontrada, sample corrupto, hash inválido |

## Qué hacer si el test falla

**Si acabás de refactorear el motor y falla:**
El refactor rompió paridad. Leer el diff detallado. Opciones:
1. **Corregir el refactor** para que no cambie comportamiento — la opción correcta cuando el objetivo era preservar paridad
2. **Aceptar el cambio** si fue intencional (ej. bug fix real que el canonical tenía). En ese caso, hay que:
   - Regenerar el canonical con el proceso formal de `CANONICAL_MANAGER_SPEC.md`
   - Nuevo sign-off
   - Regenerar el sample con el nuevo baseline
   - Bumpear versión del motor (MINOR si es backward compatible, MAJOR si no)

**Si falla sin haber tocado el motor:**
Algo cambió que no debía. Chequear:
- ¿Se modificó alguna fixture sin regenerar hash?
- ¿Se actualizó una librería que alteró cálculos de floats?
- ¿Cambió `observatory_v5_2.db` de posición o contenido?
- ¿El sample `.json` fue modificado accidentalmente (git log del file)?

## Cómo regenerar el reference

Solo regenerar cuando el canonical cambia formalmente (nuevo `qqq_canonical_v2.json`). El proceso:

1. Correr replay completo con el nuevo canonical → genera nueva DB
2. Correr el script generador del sample (embebido en las notas del Observatory)
3. Actualizar `tests/fixtures/parity_qqq_sample.json` con el nuevo content
4. Actualizar `tests/fixtures/parity_qqq_candles.db` si cambió el rango de sesiones
5. Actualizar el campo `canonical_hash` y `engine_version` del sample
6. Commitear junto con el nuevo canonical

## Diseño del sample

El sample contiene **30 sesiones de QQQ en 2025** (2-3 sesiones por mes, seleccionadas con seed fijo = 42 para reproducibilidad). Esto produjo 245 señales con distribución:

| Franja | Cantidad |
|---|---|
| REVISAR | 65 |
| B | 86 |
| A | 63 |
| A+ | 27 |
| S | 3 |
| S+ | 1 |

**Por qué 30 sesiones y no más:**
- Suficiente para cubrir las 6 franjas (incluyendo S+ que es raro)
- Representa ~12% del año operativo (250 sesiones), cubriendo cada mes
- Dataset portable fits en ~11 MB (vs 30 MB del dataset completo del observatorio)
- Corre en < 1 segundo contra DB pre-calculada, en < 30s si hay que regenerar señales desde candles

**Por qué 2025 y no 2024 o 2023:**
- 2025 es el período más reciente con data completa en `observatory_v5_2.db`
- Datos más recientes reducen la posibilidad de que edge cases antiguos se oculten

## Interpretación de la tolerancia

El parámetro `--tolerance` controla qué cuenta como "iguales" para valores float (score, trigger_sum, confirm_sum). Default es 0.01, suficientemente estricto para detectar cambios reales pero tolerante a diferencias de punto flotante por orden de operaciones.

**No tolera:** diferencias en campos enteros (alignment.n, trigger_count), strings (confidence, direction), booleans (conflict_blocked), o presencia/ausencia de componentes. Esas siempre deben matchear exactamente.

