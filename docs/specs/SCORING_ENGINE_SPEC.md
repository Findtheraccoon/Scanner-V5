# SCORING_ENGINE_SPEC.md — Contrato del Scoring Engine v5

> **Propósito de este documento:** definir el contrato formal del motor de scoring como un componente plug-and-play. Establece qué recibe, qué devuelve, qué invariantes mantiene, y cómo se versiona. Es el source of truth para cualquier chat/developer que vaya a modificar el motor o a portarlo a otra plataforma (ej. scanner HTML).
>
> **Cuándo consultarlo:** antes de tocar `scanner/scoring.py`, `scanner/engine.py` o `scanner/patterns.py`. Antes de diseñar un nuevo caller (replay, live scanner, herramienta de calibración). Cuando haya duda sobre qué puede y qué no puede hacer el motor.
>
> **Cuándo NO consultarlo:** para armar una fixture de ticker (usar `FIXTURE_SPEC.md`). Para calibrar un ticker nuevo (usar `CALIBRATION_METHODOLOGY.md`). Para resolver un error en runtime (usar `FIXTURE_ERRORS.md`).

**Versión de este documento:** 1.0.0 · **Motor descrito:** 5.2.0

---

## 1 · Filosofía del motor

El motor implementa un **sistema de scoring por capas sobre señales de trading intraday**. Su diseño sigue tres principios rígidos:

**Principio 1 — Separación estructura/configuración.** El motor encapsula la *lógica* del scoring (cómo se aplican gates, cómo se combinan triggers y confirms, cómo se asigna la franja). Los *números* (pesos, umbrales, bandas) viven fuera del motor, en archivos de configuración llamados fixtures. El motor NUNCA tiene valores numéricos hardcoded que puedan variar por ticker.

**Principio 2 — Pureza funcional.** El motor es stateless. Cada invocación de `analyze()` es independiente: recibe inputs, devuelve output, no guarda nada entre llamadas. No hay caché interno, no hay memoria, no hay efectos laterales. Esto permite paralelización trivial y hace que los 6 slots del scanner sean instancias lógicas, no objetos vivos.

**Principio 3 — Outputs estructurados siempre.** El motor NUNCA lanza excepciones hacia el caller. Todos los casos de error se materializan como objetos de resultado con campos explícitos (`blocked`, `error_code`, `error_detail`). Esto garantiza que un slot en estado degradado no rompe el sistema.

---

## 2 · Interfaz pública

El motor expone una sola función de entrada: `analyze()`. Cualquier otro entry point es interno al paquete `scanner/` y no parte del contrato público.

### 2.1 Firma

```python
def analyze(
    ticker: str,
    candles_daily: list[dict],
    candles_1h: list[dict],
    candles_15m: list[dict],
    fixture: dict,
    spy_daily: list[dict] | None = None,
    sim_datetime: str | None = None,
    sim_date: str | None = None,
    bench_daily: list[dict] | None = None,
) -> dict
```

### 2.2 Inputs

| Parámetro | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `ticker` | str | Sí | Símbolo del activo (ej. "QQQ"). Se usa para logging y trazabilidad, no para lógica |
| `candles_daily` | list[dict] | Sí | Velas diarias del ticker, ordenadas antigua→reciente. Mínimo 40 para MAs |
| `candles_1h` | list[dict] | Sí | Velas 1H del ticker. Mínimo 25 para warmup |
| `candles_15m` | list[dict] | Sí | Velas 15M del ticker. Mínimo 25 para warmup |
| `fixture` | dict | Sí | Configuración validada del ticker. Schema en `FIXTURE_SPEC.md` |
| `spy_daily` | list[dict] | No | Velas diarias SPY. Requerido solo si el ticker usa DivSPY |
| `sim_datetime` | str | No | Timestamp simulado "YYYY-MM-DD HH:MM:SS" ET. Usado por ORB time gate |
| `sim_date` | str | No | Fecha simulada "YYYY-MM-DD". Usado para slicing sin look-ahead |
| `bench_daily` | list[dict] | No | Velas diarias del benchmark de este ticker. Requerido si la fixture define FzaRel con peso > 0 |

Formato de un dict de vela: `{"dt": "YYYY-MM-DD HH:MM:SS", "o": float, "h": float, "l": float, "c": float, "v": int}`.

### 2.3 Outputs

La función **siempre** devuelve un dict con la siguiente estructura, sin importar si la señal fue generada, bloqueada o hubo error:

```python
{
    "ticker": str,                     # echo del input
    "engine_version": str,             # ej. "5.2.0"
    "fixture_id": str,                 # leído de fixture["fixture_id"]
    "fixture_version": str,            # leído de fixture["fixture_version"]
    "score": float,                    # 0.0 si bloqueado
    "conf": str,                       # franja: "S+", "S", "A+", "A", "B", "REVISAR", "—"
    "signal": str,                     # "SETUP", "REVISAR", "NEUTRAL"
    "dir": str | None,                 # "CALL", "PUT", None
    "blocked": str | None,             # None si pasó todos los gates, string con causa si se bloqueó
    "error": bool,                     # True solo si hubo error operativo (candles insuficientes, etc.)
    "error_code": str | None,          # Código ENG-XXX si error=True
    "layers": dict,                    # Detalle de qué calculó cada capa (para debug/auditoría)
    "ind": dict,                       # Indicadores calculados (precio, ATR, BBs, volumen, etc.)
    "patterns": list[dict],            # Patrones detectados
    "sec_rel": dict | None,            # Fuerza relativa vs benchmark si aplica
    "div_spy": dict | None,            # Divergencia SPY si aplica
}
```

---

## 3 · Invariantes del motor

Estos son los comportamientos garantizados por el motor. Cualquier implementación que los viole es un bug, no una variación legítima.

### I1 · No look-ahead

El motor jamás accede a datos posteriores a `sim_datetime`. Todas las velas usadas para cálculo deben tener timestamp `<= sim_datetime`. El caller es responsable de hacer el slicing antes de pasar las velas, pero el motor NO verifica esto (es confianza). Si el caller pasa datos futuros, el backtest queda invalidado silenciosamente.

### I2 · Determinismo

Para los mismos inputs, el motor devuelve exactamente el mismo output, bit por bit. Esto es requisito para:
- Reproducibilidad de backtests
- Paridad Python ↔ JS (scanner en vivo)
- Test de regresión del canonical

Implicación: no hay timestamps del wall clock, no hay randomness, no hay threading interno que cambie el orden de agregaciones.

### I3 · Sin excepciones hacia afuera

El motor nunca lanza excepciones que propaguen al caller. Todos los casos de fallo se traducen a `{"error": True, "error_code": "ENG-XXX", ...}`. Esto incluye:
- Candles insuficientes → `ENG-001`
- Fixture inválida o ausente de campos críticos → `ENG-010` (aunque esto debería haberse detectado en la carga)
- División por cero en cálculo de indicador → `ENG-020`
- Cualquier otra condición inesperada → `ENG-099` (catch-all, con log)

Lista completa de códigos en `FIXTURE_ERRORS.md` sección `ENG-XXX`.

### I4 · Fixture es read-only

El motor jamás modifica el dict `fixture` que recibe. Lo trata como frozen. Si el motor necesita derivar valores a partir de la fixture (ej. cacheo de categorización de confirms), lo hace en variables locales.

### I5 · Structure gate siempre primero

El orden de los gates es fijo y no depende de la fixture:

1. **Alignment gate** (estructura) — `alignment_n >= 2` o catalyst override
2. **Trigger gate** — al menos un trigger en la dirección correcta
3. **Conflict gate** — si hay triggers en ambas direcciones, la diferencia de pesos debe ser ≥2
4. **ORB time gate** — ORB triggers solo válidos ≤ 10:30 ET (informacional, ya filtrado en detección)
5. **Score + banda** — suma final y asignación de franja

Si cualquier gate 1-3 falla, `score=0` y `blocked` contiene la causa. Los gates 4 y 5 no son de rechazo, son de cálculo.

### I6 · Categorización de confirms es canónica

El mapeo de `description` de un confirm a su `category` (ej. "FzaRel +0.87% vs SPY" → categoría `FzaRel`) está definido en el motor y NO es configurable por fixture. La fixture solo asigna pesos a categorías ya conocidas. Si un confirm tiene una description que no matchea ninguna categoría conocida, se ignora (peso 0 efectivo). La lista de categorías válidas es parte del contrato del motor y cambia solo en MAJOR versions.

### I7 · Deduplicación por categoría

Si un scan detecta dos confirms de la misma categoría (ej. "BB inf 1H ($480.5)" y "BB inf 1H ($481.2)" — muy raro pero posible), solo uno suma al score. El motor deduplica silenciosamente quedándose con el primero. No es configurable.

---

## 4 · Versionado del motor (semver)

El motor sigue versionado semántico estricto: `MAJOR.MINOR.PATCH`.

### 4.1 Qué constituye cada tipo de cambio

**MAJOR** (ej. 5.x.x → 6.0.0): cambio que rompe la compatibilidad con fixtures existentes. Ejemplos:

- Cambiar la firma de `analyze()` — agregar parámetro obligatorio, cambiar tipo de uno existente
- Agregar una categoría nueva de confirm que las fixtures viejas no declaran en `confirm_weights`
- Cambiar el orden o número de gates (I5)
- Cambiar el formato del output — agregar campo obligatorio, renombrar uno
- Cambiar el algoritmo de categorización (I6) de forma que las mismas descripciones mapeen a categorías distintas
- Cambiar la semántica de la deduplicación (I7)
- Promover un parámetro de Nivel 3 (hoy hardcoded) a Nivel 2 (leído de fixture)

**MINOR** (ej. 5.2.0 → 5.3.0): funcionalidad nueva retrocompatible. Ejemplos:

- Agregar campo opcional nuevo al output (fixtures y callers viejos lo ignoran)
- Agregar categoría nueva de trigger/confirm **opcional** (con default 0 si no está en la fixture)
- Nuevo gate opcional controlado por un campo nuevo en fixture (ausente → gate desactivado)
- Mejora de performance que no cambia resultados (cache interno, optimización de loops)
- Nuevos códigos `ENG-XXX` para condiciones previamente catch-all

**PATCH** (ej. 5.2.0 → 5.2.1): bug fix que no cambia el contrato. Ejemplos:

- Corrección de cálculo de indicador que estaba mal (esto invalida DBs viejas pero no rompe fixtures)
- Fix de edge case donde el motor devolvía error en entrada legítima
- Mejoras de logging, mensajes de error más claros
- Fix de violación de invariante (ej. no-determinismo descubierto)

### 4.2 Compatibility range

El motor declara en su código qué versiones de fixture acepta mediante un rango semver estilo npm:

```python
# En scanner/engine.py
ENGINE_VERSION = "5.2.0"
FIXTURE_COMPAT_RANGE = ">=5.0.0,<6.0.0"
```

- `ENGINE_VERSION` es la versión actual del motor
- `FIXTURE_COMPAT_RANGE` es el rango de versiones de **schema de fixture** que este motor entiende

Las fixtures arrancan en `5.0.0` para que el número matchee visualmente con la familia del motor (`5.x.x`). Esto no implica que versión de motor y de fixture estén acopladas — siguen siendo números independientes. Cuando el motor pase a `6.0.0` (un MAJOR con cambios rompientes), las fixtures también pasarán a `6.0.0`, pero en el intermedio las minors y patches de cada uno evolucionan por separado.

### 4.3 Release aprobado

Un nuevo MAJOR o MINOR del motor requiere:

1. Actualización de este documento
2. Replay de paridad sobre QQQ canonical: si MAJOR, la paridad puede romperse intencionalmente (y el canonical debe regenerarse); si MINOR, la paridad debe mantenerse.
3. Update de `FIXTURE_COMPAT_RANGE` en el registry si el nuevo MAJOR rompe fixtures viejas
4. Sign-off explícito del trader

PATCH no requiere sign-off pero sí requiere que los tests de paridad sigan pasando.

---

## 5 · Lista canónica de categorías

Esta es la lista completa de categorías que el motor reconoce en la versión 5.2.0. Hay dos grupos con tratamiento distinto:

- **Triggers** (5.1): pesos hardcoded en `scanner/patterns.py`. No se externalizan en v5.x.x.
- **Confirms** (5.2): pesos declarados en la fixture. Toda fixture v5.x.x debe declarar pesos para estas 10 categorías.

Una fixture válida **solo** declara `confirm_weights` con estas 10 categorías. Si declara `trigger_weights` o cualquier otro bloque de pesos no reconocido, produce `FIX-007` en la carga.

### 5.1 Trigger categories (internas al motor en v5.x.x)

Estas 14 categorías son detectadas por `scanner/patterns.py` y combinadas por el motor con sus pesos definidos en código. **En v5.x.x los pesos de triggers NO se externalizan vía fixture** — viven en `patterns.py` y son tratados por el motor como pesos crudos sin categorización dentro del scoring.

| Categoría interna | Descripción del patrón | Peso actual (v5.2.0) |
|---|---|---|
| Doji BB sup | Doji en banda superior BB 15M | 2 |
| Doji BB inf | Doji en banda inferior BB 15M | 2 |
| Hammer | Martillo en zona de soporte | 2 |
| Shooting Star | Estrella fugaz en zona de resistencia | 2 |
| Envolvente alcista 1H | Engulfing bull 1H | 3 |
| Envolvente bajista 1H | Engulfing bear 1H | 3 |
| Doble techo | Doble techo 15M | 3 |
| Doble piso | Doble piso 15M | 3 |
| Cruce alcista MA20/40 1H | MA cross up | 2 |
| Cruce bajista MA20/40 1H | MA cross down | 2 |
| Rechazo sup | Wick superior en 60%+ del rango | 2 (con decay) |
| Rechazo inf | Wick inferior en 60%+ del rango | 2 (con decay) |
| ORB breakout | Opening Range Breakout (solo ≤10:30 ET) | 2 |
| ORB breakdown | Opening Range Breakdown (solo ≤10:30 ET) | 2 |

Si Fase 5+ produce evidencia empírica de que los pesos de triggers necesitan recalibración por ticker, entonces se externalizarán. Eso será un MAJOR del motor (v6.0.0) que agregue `trigger_weights` al schema de fixture. Hoy (v5.x.x) el contrato es que los pesos de triggers son parte del motor.

### 5.2 Confirm categories (externalizadas en fixture)

| Categoría | Descripción |
|---|---|
| `FzaRel` | Fuerza relativa vs benchmark. Requiere `bench_daily` |
| `BBinf_1H` | Precio en banda inferior 1H |
| `BBsup_1H` | Precio en banda superior 1H |
| `BBinf_D` | Precio en banda inferior diaria |
| `BBsup_D` | Precio en banda superior diaria |
| `VolHigh` | Volumen ≥ umbral × promedio |
| `VolSeq` | Secuencia creciente de volumen |
| `Gap` | Gap de apertura significativo |
| `SqExp` | BB squeeze → expansion |
| `DivSPY` | Divergencia de porcentaje vs SPY |

Cualquier peso de fixture que referencie una categoría fuera de estas listas produce error `FIX-005` en la carga.

---

## 6 · Qué NO es el motor

Para evitar ambigüedad, acá lo que el motor explícitamente NO hace:

- **No descarga datos.** La carga de candles y fixture es responsabilidad del caller
- **No mantiene historial.** No sabe qué señales generó antes
- **No decide acciones de trading.** Devuelve score + franja; el caller (backtest o scanner live) decide qué hacer con eso
- **No persiste en DB.** La persistencia es responsabilidad del caller (`backtest/db.py`)
- **No calibra fixtures.** Ese proceso está descrito en `CALIBRATION_METHODOLOGY.md` y lo hacen scripts separados
- **No valida fixtures profundamente.** Asume que la fixture que recibe ya fue validada por el loader. Si llega basura, protege con `ENG-010` pero no es su trabajo principal

---

## 7 · Referencias

- `FIXTURE_SPEC.md` — schema completo de la fixture que el motor consume
- `FIXTURE_ERRORS.md` — tabla de error codes (`ENG-XXX` definidos acá)
- `SLOT_REGISTRY_SPEC.md` — cómo los slots del scanner asignan fixture a ticker
- `CALIBRATION_METHODOLOGY.md` — método para calibrar una fixture nueva
- `SCANNER_V5_PORTING.md` — mapeo Python → JS para el scanner HTML

---

## 8 · Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0.0 | 2026-04-18 | Documento inicial. Motor 5.2.0. Publicado junto con refactor plug-and-play |
