# backend/fixtures/parity_reference/ — Parity reference del motor v5

Contiene el dataset golden reference que el Validator (test F) y el chat de desarrollo usan para validar que el motor de scoring v5 preserva comportamiento bit-a-bit a través de cambios de código. El test principal es el **parity check** contra el canonical QQQ.

**Este README es la fuente de verdad del sample:** formato y ventana declarados acá ganan sobre cualquier otra mención en docs operativos o specs.

## Archivos

| Archivo | Propósito |
|---|---|
| `parity_qqq_canonical.py` | Go/no-go: valida que el motor actual genera las mismas señales que el canonical aprobado |
| `fixtures/parity_qqq_sample.json` | Golden reference: 245 señales de 30 sesiones de QQQ 2025 con todos sus campos esperados |

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

También verifica que no haya señales extra en la DB que no estén en el reference, o ausentes.

## Cuándo correrlo

**Obligatorio antes de:**
- Aprobar cualquier PR que toque `backend/engines/scoring/` o `backend/fixtures/qqq_canonical_v1.json`
- Cualquier merge a la rama principal que toque el motor

**Recomendado:**
- Después de actualizar dependencias (cambios de versión de Python, librerías numéricas)
- Al migrar entre entornos (local → CI/CD)

**Innecesario:**
- En cambios puramente cosméticos (comentarios, renames sin cambio de lógica)
- En cambios fuera de `backend/engines/scoring/` que no tocan el motor

## Cómo correrlo

```bash
# Desde la raíz del repo
python3 backend/fixtures/parity_reference/parity_qqq_canonical.py

# Con tolerancia custom para floats
python3 backend/fixtures/parity_reference/parity_qqq_canonical.py --tolerance 0.001

# Contra una DB específica (default: data/scanner.db)
python3 backend/fixtures/parity_reference/parity_qqq_canonical.py --db data/scanner_refactored.db
```

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
- ¿La DB del scanner (`data/scanner.db`) fue regenerada o borrada?
- ¿El sample `.json` fue modificado accidentalmente (`git log` del file)?

## Cómo regenerar el reference

Solo regenerar cuando el canonical cambia formalmente (nuevo `qqq_canonical_v2.json`). El proceso:

1. Correr replay completo con el nuevo canonical en el Observatory → genera nueva DB allá
2. Correr el script generador del sample (embebido en las notas del Observatory)
3. Copiar el output a `backend/fixtures/parity_reference/fixtures/parity_qqq_sample.json`
4. Actualizar el campo `canonical_hash` y `engine_version` del sample
5. Commitear junto con el nuevo canonical

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
- Sample completo fits en ~400KB de JSON
- Corre en < 1 segundo

**Por qué 2025 y no 2024 o 2023:**
- 2025 es el período más reciente con data completa en `observatory_v5_2.db`
- Datos más recientes reducen la posibilidad de que edge cases antiguos se oculten

## Interpretación de la tolerancia

El parámetro `--tolerance` controla qué cuenta como "iguales" para valores float (score, trigger_sum, confirm_sum). Default es 0.01, suficientemente estricto para detectar cambios reales pero tolerante a diferencias de punto flotante por orden de operaciones.

**No tolera:** diferencias en campos enteros (alignment.n, trigger_count), strings (confidence, direction), booleans (conflict_blocked), o presencia/ausencia de componentes. Esas siempre deben matchear exactamente.
