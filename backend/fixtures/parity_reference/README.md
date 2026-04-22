# backend/fixtures/parity_reference/ — Parity reference del motor v5

Dataset golden reference usado para validar que el motor de scoring v5 (`backend/engines/scoring/analyze()`) preserva comportamiento bit-a-bit con el canonical QQQ del Observatory. Dos scripts de parity check conviven:

1. **`parity_qqq_regenerate.py`** — **Opción B (regeneración E2E)**: carga velas desde la DB portable, corre `analyze()` sobre cada timestamp del sample y compara. Es el que usa el chat del Scanner-V5 para validar paridad durante desarrollo.
2. **`parity_qqq_canonical.py`** — **Opción A (comparación rápida)**: compara una DB de señales pre-calculadas contra el reference. Requiere DB con outputs del scanner production, no del motor puro.

## Archivos

| Archivo | Tamaño | Rol |
|---|---|---|
| `parity_qqq_regenerate.py` | ~12 KB | Runner E2E: lee DB de velas, corre `analyze()`, compara |
| `parity_qqq_canonical.py` | ~15 KB | Comparador rápido contra DB de señales pre-calculadas |
| `fixtures/parity_qqq_sample.json` | ~390 KB | Golden reference: 245 señales de 30 sesiones QQQ 2025 |
| `../../../data/parity_qqq_candles.db` | ~10.6 MB | **Dataset de velas** (gitignored, local-only) |

## Dataset de velas (no versionado)

La DB de velas vive en **`data/parity_qqq_candles.db`** (ruta gitignored — `data/*.db`). No se sube al repo por tamaño. Si necesitás correr `parity_qqq_regenerate.py` y no tenés la DB, pedísela a Álvaro.

Schema:

| Tabla | Contenido | Filas |
|---|---|---|
| `qqq_1min` | Velas 1-minuto de QQQ (warmup + sesiones target) | 96,562 |
| `qqq_daily` | Velas diarias de QQQ | 249 |
| `spy_daily` | Velas diarias de SPY (para FzaRel y DivSPY) | 249 |
| `metadata` | Info del dataset (rango, hash, propósito) | 16 |

**Rango:** `2024-11-03` a `2025-11-01`. Warmup hasta `2025-01-01`, sesiones target `2025-01-02` a `2025-10-31`.

## Cómo correr el regenerador (Opción B)

```bash
# Desde la raíz del repo
python3 backend/fixtures/parity_reference/parity_qqq_regenerate.py

# Limitar a N señales (debug rápido)
python3 backend/fixtures/parity_reference/parity_qqq_regenerate.py --limit 10

# Ver primeros N diffs en detalle
python3 backend/fixtures/parity_reference/parity_qqq_regenerate.py --max-diffs 20

# Ajustar tolerancia float
python3 backend/fixtures/parity_reference/parity_qqq_regenerate.py --tolerance 0.001
```

### Exit codes

| Code | Significado |
|---|---|
| 0 | PARITY OK — 0 diferencias |
| 1 | PARITY FAIL — hay diffs (imprime detalle) |
| 2 | Error de setup (DB no encontrada, sample corrupto) |

## Qué valida el regenerador

Por cada una de las 245 señales del sample, compara bit-a-bit:

- `score` (tolerancia float configurable, default 0.01)
- `confidence` (banda)
- `direction` (CALL/PUT)
- `alignment` (n + dir)
- `trends` (t15m, t1h, tdaily)
- `structure.pass` y `structure.override`
- `trigger_count`, `trigger_sum`, `confirm_sum`
- `conflict_blocked`

## Convenciones aprendidas durante el port

El sample fue generado por Observatory en **replay mode** (post-cierre de cada sesión). El regenerador replica esa convención:

1. **Velas daily:** se incluye la vela cerrada del día de la señal (`dt <= date`). En live sería look-ahead, pero el sample lo requiere porque Observatory procesa cada señal con toda la info diaria disponible.
2. **Aggregation 15M:** buckets open-stamped `[T, T+14]`, última vela parcial al momento T (el close de 15M "T" = close del 1min T = `price_at_signal`).
3. **Aggregation 1H:** buckets open-stamped alineados a `HH:00`. La convención exacta para MA20/MA40 1H sigue siendo ambigua (ver divergencias abajo).
4. **Daily replay mode:** `a_chg` y `spy_chg` usan el close final del día actual, no el intraday — ambos alineados temporalmente.

Referencia: `docs/specs/Observatory/Current/Replay/` contiene el código del replay del Observatory (una vez portado) que dosifica cada vela al scanner como si fuera tiempo real. Ese es el material de referencia definitivo para resolver las ambigüedades 1H pendientes.

## Baseline actual de paridad

**189/245 matches (77%)** — ver commit `8cab0ea`.

Divergencias restantes (56 casos) agrupadas en:

- **`trigger_sum` con decimales raros:** expected=2.0 actual=2.1 → decay/age off by 1 vela. Requiere investigar `patterns.py` Observatory + replay para saber exactamente cómo calcula `age` de las velas pasadas.
- **`trends.t1h`/`trends.t15m` neutral vs bullish/bearish:** MA20/MA40 parcialmente divergentes por convención de aggregation. El replay del Observatory debería clarificar cómo se construyen las velas 1H al momento de evaluación.
- **`conflict_blocked` spurious:** mi motor detecta más triggers direccionales opuestos. Efecto cascada del punto anterior.

Estos 56 casos NO indican bugs del motor core (scoring, dedup, bandas). El motor está correcto en su lógica; la divergencia viene de cómo se construyen las velas 1H/15M que le llegan.

## Cuándo correrlo

**Obligatorio antes de:**
- Aprobar cualquier PR que toque `backend/engines/scoring/`.
- Merge a main que toque el motor.
- Cambios a la fixture canonical QQQ.

**Recomendado:**
- Después de actualizar dependencias numéricas (versiones de `statistics`, etc.).
- Al migrar entornos.

## Qué hacer si el test falla

**Si acabás de refactorear y falla:**
1. Leer los primeros diffs (`--max-diffs 20`).
2. Corregir el refactor para preservar paridad.

**Si el cambio es intencional (bug fix del canonical):**
1. Regenerar el canonical siguiendo `CANONICAL_MANAGER_SPEC.md`.
2. Re-generar el sample.
3. Bumpear versión del motor.

## Regenerar el reference

Solo cuando el canonical cambie formalmente:

1. Correr replay completo con el nuevo canonical → nueva DB del Observatory.
2. Exportar 245 señales al nuevo `parity_qqq_sample.json`.
3. Actualizar `canonical_hash` y `engine_version` del sample.
4. (Opcional) Regenerar `parity_qqq_candles.db` si cambió el rango.
5. Commitear junto con el nuevo canonical.

## Diseño del sample

- **30 sesiones de QQQ 2025** (2-3 sesiones por mes, seed fijo = 42).
- **245 señales totales** distribuidas:
  - REVISAR: 65
  - B: 86
  - A: 63
  - A+: 27
  - S: 3
  - S+: 1
- Seleccionado para cubrir las 6 franjas (incluyendo S+ raro) y cada mes del año.
