# SCANNER_V5_FEATURE_DECISIONS.md

> **Propósito de este documento:** registro vivo de todas las decisiones de producto, arquitectura y UX tomadas para el Scanner v5 live durante la sesión de diseño con Álvaro. Es la fuente de verdad. Todo chat de desarrollo futuro debe leerlo antes de implementar nada. Los specs técnicos de referencia (`SCORING_ENGINE_SPEC.md`, `FIXTURE_SPEC.md`, `FIXTURE_ERRORS.md`, `SLOT_REGISTRY_SPEC.md`, `CANONICAL_MANAGER_SPEC.md`, `CALIBRATION_METHODOLOGY.md`, `SCANNER_V5_DEV_HANDOFF.md`) siguen siendo contrato, pero este documento **extiende y en algunos casos modifica** el alcance que ellos describen para el scanner live (ver sección "Desvíos explícitos de specs" más abajo).
>
> **Qué NO es:** no es spec técnico detallado (los specs siguen siendo la fuente para schemas, firmas, invariantes). No es guía de implementación paso a paso. No es documentación del Observatory.

**Versión del documento:** 1.1.0 · **Última actualización:** 2026-04-20 · **Sesiones de diseño:** 2026-04-19/20 (v1.0.0) + 2026-04-20 barrido backend + cierre Cockpit (v1.1.0)

---

## 0 · Cómo leer este documento

Cada bloque describe decisiones cerradas con el formato:

- **Qué se decidió** (la decisión concreta)
- **Por qué** (cuando aplica — rationale)
- **Implicación** (consecuencias operativas o para implementación)

Las secciones finales consolidan: specs a actualizar, códigos de error nuevos, preguntas abiertas, y reglas de operación para el próximo chat.

---

## 1 · Contexto del proyecto

### 1.1 Quién es el usuario

Álvaro — paper trader de opciones sobre TradingView. Habla español. Saludo habitual: "¡Qué bolá asere!". Workflow estricto: discusión completa → confirmación explícita ("ejecuta") → ejecución. No se toman decisiones unilaterales.

### 1.2 El ecosistema

Dos proyectos hermanos, separados:

- **Signal Observatory** (proyecto paralelo, offline, CLI Python, ~300K velas QQQ, 3 años de backtesting, SQLite ~6,519 señales) — laboratorio de calibración. Es **fuente de verdad empírica**. Ahí viven los procesos de calibración (`CALIBRATION_METHODOLOGY.md`) y aprobación de canonicals (`CANONICAL_MANAGER_SPEC.md`).
- **Scanner v5 live** (este proyecto, nuevo, greenfield) — consume los artefactos aprobados por el Observatory y opera sobre mercado en vivo con 6 slots de tickers paralelos.

**Principio rector:** el scanner **consume, no calibra ni aprueba**. Toda calibración y gobernanza de canonicals vive en el Observatory.

### 1.3 Qué reemplaza

El scanner v5 reemplaza al scanner v4.2.1 (HTML monolítico, ~5000 líneas, un ticker a la vez, scoring hardcoded, sin persistencia, sin admin). El v4.2.1 sigue siendo referencia conceptual pero no base de código.

### 1.4 Qué hace (en una oración)

Consume data de mercado en tiempo real → aplica Scoring Engine v5 plug-and-play (una fixture por slot) → persiste señales auditables → presenta cockpit operativo + dashboard admin al trader.

### 1.5 Restricción transversal

**Modularidad estricta.** Cada elemento (indicador, patrón, capa, generador de texto) puede tocarse sin arrastrar el resto. Condiciona estructura de carpetas, interfaces entre módulos y formato de configuración.

---

## 2 · Lo que NO se toca — contrato inmutable de specs

Decisiones previas al scanner v5 live, ya cerradas en los specs del Observatory. El chat de desarrollo las implementa fielmente sin debate.

### 2.1 Scoring Engine (de `SCORING_ENGINE_SPEC.md`)

- **Firma pública:** `analyze(ticker, candles_daily, candles_1h, candles_15m, fixture, spy_daily, sim_datetime, sim_date, bench_daily)`
- **Output estructurado fijo:** ticker, engine_version, fixture_id, fixture_version, score, conf, signal, dir, blocked, error, error_code, layers, ind, patterns, sec_rel, div_spy
- **5 invariantes:** stateless, puro, determinístico, no lanza excepciones hacia afuera, fixture read-only
- **Pipeline de 5 etapas en orden fijo:** alignment gate → trigger detection → confirm detection + dedup → ORB time gate + conflict check → score + franja
- **Fórmula final:** `raw = trigger_sum + new_confirm_sum`. Sin multiplicadores (ni hora, ni volumen), sin bonuses, sin risk penalties. Risks se detectan y muestran como warnings pero no restan score.
- **14 triggers con pesos hardcoded** en `patterns.py`: doji, hammer, shooting star, engulfings, dobles techo/piso, cruces MA, rechazos, ORB breakout/breakdown
- **10 confirms externalizados en fixture:** FzaRel, BBinf_1H, BBsup_1H, BBinf_D, BBsup_D, VolHigh, VolSeq, Gap, SqExp, DivSPY
- **Alignment gate + conflict check:** hardcoded inline en `layered_score()` en `scanner/scoring.py`. Nivel 3, no se externalizan
- **ORB time gate:** solo válido ≤10:30 ET
- **Versionado:** engine v5.2.0 al inicio, semver estricto, reglas MAJOR/MINOR/PATCH formales

### 2.2 Fixtures (de `FIXTURE_SPEC.md`)

- **Schema oficial:** 5 bloques top-level (metadata, ticker_info, confirm_weights, detection_thresholds, score_bands). El bloque `trigger_weights` NO existe en v5 (reservado para v6) — dispara FIX-007 si aparece.
- **Reglas duras:** pesos de confirms en `[0, 10]`, 10 categorías obligatorias, bands contiguas sin overlap ni gaps, solo la top band con `max:null`, benchmark consistente con flag
- **Canonicals:** `{ticker}_canonical_v{N}.json` + `{ticker}_canonical_v{N}.sha256` — inmutables, protegidas por hash (REG-020), creadas solo en Observatory
- **Versionado semver estricto** con `engine_compat_range` en metadata

### 2.3 Slot Registry (de `SLOT_REGISTRY_SPEC.md`)

- **Archivo `slot_registry.json` en raíz del repo** (Decisión A, firme, no se mueve)
- **Exactamente 6 slots** por registry (cardinalidad fija, decisión de producto)
- **Dos bloques:** `registry_metadata`, `slots` (array de 6 objetos)
- **Validaciones al arranque con códigos REG-XXX** (archivo existe, JSON válido, 6 slots, IDs únicos 1-6, paths de fixtures existen, compatibility, consistencia benchmark, hash SHA-256 de canonicals, engine_version_required compatible)
- **Atomicidad:** slot con fixture inválida → DEGRADED, otros siguen; 0 slots válidos → abort fatal

### 2.4 Códigos de error (de `FIXTURE_ERRORS.md`)

- **Prefijos:** FIX- (fixture loading), ENG- (engine runtime), REG- (registry), CAL- (calibration, solo Observatory)
- **Severidad por numeración:** 001-099 críticos, 100-199 warnings, 200-299 info
- **37 códigos documentados** al inicio + los nuevos que este documento agrega (ver sección 14)

### 2.5 Las 4 redundancias del sistema (de `SCANNER_V5_DEV_HANDOFF.md`)

Todas deben existir en la implementación, ninguna se elimina por simplicidad:

1. Validación al arranque (Capa 2 — loader)
2. Hash SHA-256 de canonicals (verificación al arranque)
3. Replay de paridad (suite de tests del backend)
4. Fallback graceful por slot (un slot DEGRADED no tumba a los otros 5)

### 2.6 Versionado independiente de componentes

- `engine v5.X.Y` — mejoras del motor
- `fixture v5.X.Y` — recalibraciones aprobadas
- `registry v1.X.Y` — cambios de asignación
- `canonical_manager v1.X.Y` — mejoras del flujo

Son independientes. No se pueden acoplar en un solo versionado.

---

## 3 · Arquitectura de 7 capas — decisiones cerradas

El scanner v5 está estructurado en 7 capas apiladas, flujo estrictamente descendente y unidireccional. Lo que sigue son **las decisiones del scanner live** que extienden/completan los specs.

---

### 3.1 Capa 1 — Data Engine

**Rol:** motor vivo, responsable de obtención, almacenamiento y distribución de datos de mercado.

#### Qué hace

- Gestión de API keys del provider
- Conexión al provider, fetch, retries, rate limiting, distribución multi-key
- Persistencia de velas (candles) en DB local
- Endpoint hacia otros motores y hacia servicios externos (es provider genérico de data, no acoplado al Scoring)

#### Decisiones operativas

- **Provider:** Twelve Data (confirmado; Alpaca evaluado y descartado en sesiones previas por delay de 15 min en plan gratuito)
- **API keys:** hasta **5 keys** configurables independientemente. Por cada una:
  - Valor de la key
  - Créditos por minuto (configurable; default 8 si plan gratuito)
  - Créditos diarios máximos (configurable; default 800 si plan gratuito)
- **Distribución multi-key:** round-robin con **proporcional a créditos/min** de cada key (keys con más créditos reciben más símbolos — patrón heredado de v4.2.1 validado en producción)
- **Redistribución dinámica:** si una key agota cupo diario → su carga se redistribuye entre las keys restantes automáticamente
- **Límite watchlist:** máximo 6 tickers (consistente con cardinalidad de slots)
- **Reset del contador diario:** al final del día de mercado (no a medianoche UTC)
- **Encriptación:** API keys viven encriptadas en DB durante operación, descifradas en RAM cuando se usan. Se borran de RAM y DB al apagar el backend (ver sección 4.4 — Persistencia privada)

#### Warmup (descarga histórica al activar un ticker)

Validado por 3 años de operación del v4.2.1 — son los tamaños que el motor necesita para que TODOS los indicadores funcionen al 100% (MA200, pivotes lookback 50, BB squeeze, cruces MA):

- **210 velas diarias** (cubre MA200 + margen)
- **80 velas 1H** (~11 días hábiles — cubre MA40, pivotes, squeeze)
- **50 velas 15M** (~2 días hábiles — cubre MA40, pivotes, squeeze, ORB)

**NOTA IMPORTANTE:** estos tamaños contradicen el mínimo del `SCORING_ENGINE_SPEC.md` sección 2.2 (40/25/25). Aclaración: 40/25/25 son los mínimos *para que el motor pueda correr sin crashear*, pero no alcanzan para que todos los indicadores estén definidos. El scanner v5 live descarga 210/80/50. Ver sección 13 (specs a actualizar).

**Duración real del warmup:** segundos (3 llamadas HTTP a Twelve Data, una por timeframe). Twelve Data los devuelve en una sola llamada con `outputsize=N`. No hay que esperar tiempo de mercado excepto para tickers recién salidos a bolsa (IPOs con menos de 200 días de historia, caso marginal).

#### Ciclos de scan

**MANUAL:**
- Botón en el **Cockpit** ejecuta la secuencia a demanda
- Útil para testing, verificación puntual, forzar scan sin esperar cierre de vela
- Flujo: botón → Data Engine fetchea → verifica integridad → emite señal al Scoring

**AUTO:**
- Toggle activable/desactivable en el **Cockpit**
- Cuando ON: el backend (con conocimiento de horario de mercado ET) detecta cierre de vela de 15M (9:45, 10:00, ... 16:00 ET)
- Secuencia: cierre de vela → **delay de 3 segundos** (garantiza consolidación del provider, evita datos parciales) → Data Engine fetchea → verifica integridad → emite señal al Scoring
- Cuando OFF: ciclo automático suspendido, datos existentes disponibles, scan manual sigue funcionando

#### Verificación de integridad pre-señal

Antes de emitir señal al Scoring, el Data Engine verifica:

- Velas completas de todos los tickers de slots habilitados
- Velas completas de todos los benchmarks declarados en fixtures activas
- SPY daily presente (lo requieren fixtures con `requires_spy_daily: true`)
- Sin campos vacíos o corruptos
- Timestamp de última vela coherente con la esperada

Si falla cualquier chequeo → NO emite señal al Scoring, reporta código de error.

#### Manejo de déficit de créditos

- Data Engine detecta déficit antes/durante descarga
- Activa **indicador de carga en el Cockpit** (banner de API keys, ver sección 5.5)
- Espera renovación de créditos (Twelve Data: cada minuto)
- Reintenta
- Al completar descarga → desactiva indicador → verifica integridad → emite señal
- **La señal al Scoring solo se emite cuando los datos están completos e íntegros,** sin importar cuánto tarde

#### Ring buffers en memoria

- Candles en RAM limitados por ring buffer configurable por timeframe
- Velas más viejas que el buffer salen de RAM pero **permanecen en DB**
- Si el motor las necesita después, se releen de DB (DB es infinita, RAM no)
- Valores por defecto de los buffers: **pendientes, se definen al implementar cada motor** (ver sección 9 — preguntas abiertas)

#### Consulta a DB local antes de fetch (v1.1.0)

El Data Engine **consulta la DB local antes de fetchear Twelve Data**. Si la vela requerida ya está en DB (dentro de la ventana de retención: daily 3 años, 1H 6 meses, 15M 3 meses), no se descarga. Solo se pide a Twelve Data el gap real.

**Impacto operativo:**

- **Arranque inicial con ticker virgen** → fetch completo 210/80/50 (peor caso).
- **Re-arranque cotidiano** (mismo ticker, cierre de mercado previo) → fetch mínimo (solo velas nuevas del día si las hubiera).
- **Hot-reload activando slot 6 con ticker ya usado antes** → probablemente cero fetch de daily/1H; solo velas 15M recientes. Mucho más rápido que el peor caso del diagrama 3.

**Sub-pregunta registrada para implementación de Capa 1:** detección precisa de gaps en la DB (ej. scanner apagado viernes, sábado, lunes feriado; abierto martes → cómo decide "hasta dónde rellenar"). Pendiente de resolver al programar el motor.

#### Arranque paralelo del warmup (v1.1.0)

El warmup inicial y el warmup de hot-reload se ejecutan **paralelo full con `asyncio.gather()`** sobre todas las peticiones necesarias después de consultar la DB. Razones:

- La consulta a DB reduce drásticamente el escenario pesimista (primer arranque con 6 tickers vírgenes). El caso cotidiano tiene pocas llamadas reales a Twelve Data.
- El round-robin proporcional entre las 5 API keys distribuye la carga naturalmente.
- Tiempo de arranque mínimo; los slots pasan de WARMUP a operativo casi simultáneamente.

#### Retry policy de Twelve Data (v1.1.0)

**Patrón:** retry corto + DEGRADED tras N fallos consecutivos.

**Secuencia por ticker dentro de un ciclo AUTO:**

1. Error (timeout, HTTP 500, datos faltantes) → 1 retry rápido (~1s).
2. Si el retry falla → el ticker se marca como "skipped en este ciclo" (los otros 5 slots sí emiten señal normalmente).
3. Si un mismo slot falla **3 ciclos consecutivos** (≈45 min de mercado) → slot pasa a estado DEGRADED (piloto amarillo) con código **`ENG-060`** ("ticker sin datos por N ciclos").
4. Se auto-recupera cuando el ticker vuelve a responder en algún ciclo (contador se resetea al primer éxito).

**Ortogonal a HTTP 429** (rate limit de Twelve Data): ese error lo maneja el propio Data Engine con espera de renovación de créditos (§3.1 arriba), no dispara este flujo de retry.

**Umbral exacto (3 ciclos) tentativo** — confirmar al programar Capa 1.

---

### 3.2 Capa 2 — Validator Module

**Rol:** módulo orquestador de validación. **NO es motor** (no proceso permanente, se invoca bajo demanda).

#### Dónde vive

`backend/modules/validator/` como módulo. Invoca contratos de healthcheck/test que cada motor expone — no mete lógica de dominio propia.

#### Cuándo corre

1. **Al arrancar el sistema** — después de que los motores están activos
2. **A demanda desde el Dashboard admin** — 3 botones:
   - **Revalidar sistema completo** — bater ía entera
   - **Revalidar slot N** — solo sobre un slot afectado (se dispara automáticamente tras hot-reload de fixture/ticker)
   - **Test conectividad API** — solo prueba conexión a providers
3. **Hot-reload de fixture/ticker** — se ejecuta automáticamente sobre el slot afectado (no sobre sistema completo)

#### Estructura de la batería de tests

7 categorías (A a G) ejecutadas en orden **D → A → B → C → E → F → G** (orden de dependencias resueltas):

- **D — Diagnóstico básico de infraestructura** (DB accesible, filesystem escribible, motores vivos)
- **A — Validación de fixtures** (schema, campos obligatorios, rangos; códigos FIX-XXX)
- **B — Validación de canonicals** (hash SHA-256 de cada canonical referenciado; código REG-020)
- **C — Validación del Slot Registry** (schema, consistencia, compatibility; códigos REG-XXX)
- **E — Test end-to-end** (usa un slot real con flag `is_validator_test: true` — no contamina la DB de producción)
- **F — Parity test contra canonical QQQ** (ver sección 3.4 — es la redundancia #3)
- **G — Healthcheck de conectividad externa** (Twelve Data responde, S3 alcanzable si configurado)

#### Severidades

- **Fatal** — sistema no puede operar, todos los slots quedan afectados
- **DEGRADED** — un slot específico no puede operar, los otros siguen
- **Warning** — operable pero con advertencia

#### Heartbeat vs parity exhaustivo

Son distintos:

- **Heartbeat continuo** (cada 2 min, ver sección 4.5): mini parity test con dataset sintético pequeño, ~100 ms, alimenta pilotos de estado
- **Parity exhaustivo** (Validator al arranque + a demanda): usa dataset real del Observatory (ventana concreta por definir), segundos a decenas de segundos

#### Dataset de parity

- **Embebido en el repo** bajo `/backend/fixtures/parity_reference/`
- **Formato:** JSON monolítico — `fixtures/parity_qqq_sample.json` con metadata + array `signals`
- **Generación:** en el Observatory, copia manual al scanner
- **Dataset concreto:** 30 sesiones de QQQ en 2025 (2-3 por mes, seed fijo=42), 245 señales totales, cubriendo las 6 franjas (ver `backend/fixtures/parity_reference/README.md` como fuente de verdad)

#### Reportes

- **JSON estructurado al frontend** (se muestra en Dashboard — Sección "Pruebas validación general")
- **TXT simple al `/LOG/` del scanner** con información suficiente para diagnóstico en chat de desarrollo si algo falla
- **Retención de logs:** 5 días, rotación automática al arrancar el backend (job verifica `/LOG/` y borra lo vencido)

---

### 3.3 Capa 3 — Slot Registry Module

**Rol:** módulo que contiene los 6 slots con ticker + fixture + benchmark. Consultado por el Scoring Engine en cada scan.

#### Puente entre topología y runtime

En cada scan, el Scoring Engine consulta al Slot Registry para saber:

- Qué slots están habilitados
- Qué ticker tiene cada uno
- Qué fixture usa
- Qué benchmark (lo declara la fixture; el Registry refleja la declaración)

**Decisión de consumo — Opción A:** el motor consulta al Registry en **cada scan** (fuente de verdad única, sin cache). Evita problemas de desincronización tras hot-reload. Latencia microsegundos (llamada directa intra-proceso, ver sección 4.1).

#### Edición desde el frontend

- UI vive en el **Paso 3 de Configuración** (ver sección 5.2)
- **Estilo visual: nodo-conexión tipo Runpod** — cada slot es un card/nodo con su ticker + fixture + benchmark + piloto de estado en tiempo real, conectados visualmente
- Cada slot muestra piloto que refleja su estado real (incluye verde/amarillo/rojo + estado WARMUP)

#### Activación/desactivación

- Cualquier slot (1 a 6) puede desactivarse, no solo el último
- **Restricción dura:** al menos 1 slot debe permanecer activo para correr scan
- El sistema impide desactivar el último slot activo (validación frontend + backend)

#### Hot-reload por slot

Desvío explícito del `SLOT_REGISTRY_SPEC.md` original que decía "no hay hot-reload en v5.x". **El scanner v5 live SÍ soporta hot-reload por slot** (los otros 5 siguen operando durante el swap).

**Tres escenarios que disparan el mismo flujo:**

1. Arranque con tickers nuevos
2. Cambio de ticker en slot existente (en caliente)
3. Activación de slot previamente libre

**Secuencia:**

1. Trader introduce ticker + fixture (la fixture declara su benchmark)
2. Slot Registry emite señal al Data Engine solicitando fetch del ticker + benchmark declarado
3. Data Engine descarga warmup (210 daily, 80 1H, 50 15M)
4. Durante la descarga, el slot queda en estado **"warming up"** (visible en Dashboard + Cockpit)
5. Cuando descarga termina y validación pasa → slot operativo, próximo ciclo del Scoring lo incluye

**Principios:**

- El warmup es asumible (se espera, no se evita) — típicamente segundos
- El Scoring Engine es puro/stateless, no maneja estado del slot — el ciclo de vida del warmup vive en el orquestador del backend
- La fixture declara el benchmark (consistencia exigida por REG-013); el trader no elige benchmark aparte

**Validación post-cambio:**

- Tras hot-reload, el Validator corre solo sobre el slot afectado (no sobre sistema completo)
- Bot ón "Revalidar sistema completo" sigue disponible en Dashboard si el trader lo pide manualmente

---

### 3.4 Capa 4 — Scoring Engine

**Rol:** motor stateless, puro. Contrato del spec intacto (ver sección 2.1). Las decisiones del scanner live son sobre **cómo se invoca**, no sobre qué hace internamente.

#### Dónde vive

`backend/engines/scoring/`. Código Python portado fielmente de la implementación de referencia del Observatory. Respeta todos los invariantes del spec.

#### Ciclo de scan — invocación

**MANUAL (botón Cockpit):**
1. Trader presiona botón de scan
2. Orquestador del Scoring invoca al Data Engine → fetch + integridad
3. Data Engine emite señal de "data lista"
4. Orquestador consulta Slot Registry → filtra slots operativos (excluye DEGRADED, excluye WARMUP)
5. Invoca `analyze()` **secuencialmente** sobre los slots operativos
6. Persiste outputs en DB + pushea al Cockpit vía WebSocket

**AUTO (delay 3s tras cierre 15M + señal del Data Engine):**
Mismo flujo desde el paso 3. El reloj de mercado del backend dispara el Data Engine → Data Engine confirma → orquestador corre scan.

#### Secuencialidad

**Decisión:** scan secuencial, no paralelo.

- Motor stateless → paralelizar sería seguro
- PERO: estimado total para 6 slots de forma secuencial = **0.3 a 0.8 segundos** completo (30-80 ms por `analyze()` + lectura DB + escritura DB + push WebSocket)
- Paralelizar en este rango no da beneficio operativo y complica debugging
- Secuencial → stack trace lineal, determinístico, ordenado

#### Slots DEGRADED o en WARMUP

**Decisión:** el orquestador **no invoca `analyze()`** sobre slots en estos estados.

- Razón: el motor es puro y no tiene que saber de estados de slot. El orquestador mantiene la lista de slots operables y solo llama al motor con ellos.
- Alternativa descartada: invocar igual y dejar que devuelva ENG-001. Es más uniforme pero más sucio.

#### Healthcheck continuo — cada 2 min

**Decisión:** mini parity test cada 2 minutos, unificado con el heartbeat general del sistema.

- **Fixture canonical QQQ** (ya en memoria desde arranque)
- **Dataset sintético pequeño** pre-generado en código (~50 velas 15M, ~50 1H, ~210 daily — mínimos para pasar todos los gates)
- **`sim_datetime` fijo** (ej. "2026-04-15 10:30:00" — hora conocida que pasa el ORB gate)
- **Output esperado:** determinístico, pre-calculado una vez y guardado como referencia en el código
- **Resultado:**
  - Output matchea esperado → **verde**
  - Output difiere → **amarillo** con código `ENG-050` (parity check fallido — código NUEVO, ver sección 14)
  - Motor lanza excepción (no debería por I3, defensivo) → **rojo** con código apropiado

**Costo computacional:** ~100 ms cada 2 min. Negligible frente al scan real (0.3-0.8 s cada 15 min).

**Doble propósito del test:** (a) monitoreo operativo continuo del motor; (b) cumple parcialmente la redundancia #3 del handoff en modo continuo — el Validator sigue corriendo parity exhaustivo al arranque y a demanda (ver tabla comparativa en 3.2).

#### Comparación healthcheck continuo vs parity exhaustivo del Validator

| Aspecto | Healthcheck continuo | Validator parity test |
|---|---|---|
| Cuándo corre | Cada 2 min automático | Arranque + a demanda |
| Scope del dataset | Sintético pequeño con sim_datetime fijo | Ventana real del canonical (muchas velas) |
| Duración | ~100 ms | Segundos a decenas de segundos |
| Propósito | Monitoreo operativo | Verificación exhaustiva vs Observatory |
| Código si falla | ENG-050 (mismo, menos detalle) | ENG-050 + log detallado con diffs |

#### Comunicación con otros motores

- **Intra-proceso** (ver sección 4.1) — llamadas directas en memoria
- **Trigger del ciclo:** Data Engine le avisa al Scoring cuando tiene data completa e íntegra (no es polling, es señal push intra-proceso)
- **Consumo del Slot Registry:** Opción A — consulta al Registry en cada scan, sin cache propio

#### Parámetros `sim_datetime` y `sim_date`

- Son opcionales en la firma `analyze()`, del spec
- En scanner live **son siempre None** — el motor usa reloj del sistema para ORB gate, sin slicing simulado
- Solo el Observatory los usa (en replays históricos)
- Están en la firma para compatibilidad entre ambos contextos (un solo código de motor ejecutado en dos modos)

---

### 3.5 Capa 5 — Fixtures

**Rol:** parámetros de scoring por slot. Producidas en Observatory, consumidas en scanner live.

#### Schema — decisión final

**5 bloques estándar** (definidos en `FIXTURE_SPEC.md`):

1. `metadata`
2. `ticker_info`
3. `confirm_weights`
4. `detection_thresholds`
5. `score_bands`

**+ archivo sibling `.metrics.json` separado** (decisión final, NO un sexto bloque).

El archivo sibling contiene las métricas de calibración (WR por franja en training + out-of-sample, spread B→S+, cobertura, N de señales, dataset period, bench, uplift marginal por confirm, fecha de calibración, hash de DB de replay, status: `draft`/`final`/etc.).

**Por qué sibling y no sexto bloque:**

- Mantiene la fixture limpia (scoring) separada de la auditoría empírica (métricas)
- Permite versionar y cachear fixtures canónicas sin que cambios de métricas las invaliden
- Facilita que MEMENTO del frontend lea solo el sibling sin parsear la fixture completa
- El `METRICS_FILE_SPEC.md` (a crear en el Observatory) formaliza el schema del sibling

#### Obligatoriedad del sibling

- **Obligatorio para canonicals con `status: final`** — una canonical final sin métricas es inválida (código `MET-003` o similar)
- **Opcional para fixtures activas**
- **Opcional para canonicals `status: draft`** (canonicals en proceso de aprobación, sin métricas consolidadas aún)

#### Canonicals — ciclo de vida

- **Embebidas en el repo del scanner** como parte del release
- **Inmutables** (hash SHA-256, protegidas por REG-020)
- **Múltiples canonicals por ticker pueden coexistir** (ej. `qqq_canonical_v1`, `qqq_canonical_v2`) mientras sean compatibles con el engine_version del motor
- **Se pueden agregar canonicals nuevas** al scanner cuando el Observatory aprueba una (via update del release O upload manual desde frontend — ambas vías permitidas)
- El trader elige qué canonical asignar a cada slot (dropdown en Paso 3 del POST)
- **Estado actual:** solo QQQ tiene canonical aprobado. Resto de tickers de la watchlist esperan calibración externa en Observatory.

#### Fixtures activas (no canonicals)

- **Viven dentro del archivo Config del usuario** (Lectura B de sesión — decisión firme)
- Al cargar un Config, las fixtures del Config se aplican a los slots según asignación
- Al guardar Config, las fixtures activas de cada slot se serializan adentro del Config
- Pueden ser copias exactas de un canonical o variantes experimentales derivadas

**Razón:** al vivir las fixtures en el Config del usuario, se evitan accidentes de compartir fixtures experimentales no intencionadas entre usuarios. El archivo Config es la unidad portable personal del trader.

#### Upload de fixture/canonical desde el frontend

- Formulario en Paso 3 del POST (o en Dashboard — por definir exacto en implementación)
- **Acepta:** archivo `.json` único + su `.metrics.json` sibling opcional. Alternativa: zip con ambos.
- Al subir: validación contra schema (FIX-XXX) + validación del sibling si aplica (MET-XXX nuevos, ver sección 14)
- Si pasa validación:
  - **Canonicals** → van al directorio `fixtures/` del repo (persistencia global, no en Config)
  - **Fixtures activas** → se cargan al slot indicado y quedan serializadas dentro del Config al guardar

#### Fixture predeterminada por slot

- Si un slot queda con ticker asignado pero sin fixture → se usa la **canonical del ticker** si existe
- Si el ticker no tiene canonical en el release → el slot **no se puede activar** (la UI rechaza la asignación con mensaje claro)

#### Hot-reload con validación

- Cambio de fixture en caliente pasa por validación completa del schema + sibling de métricas si aplica
- Si falla → slot queda DEGRADED con código FIX-XXX o MET-XXX apropiado
- Si pasa → slot se reinicia con nueva fixture, completa warmup si aplica, vuelve a operar

#### El scanner NO edita, NO aprueba, solo consume

- Sin editor de pesos, umbrales ni bandas en Dashboard
- Sin Canonical Manager dentro del scanner
- Sin proceso propose/review/promote dentro del scanner
- Todo cambio de canonicals se origina en Observatory con flujo formal

#### Peso del archivo Config

- Fixture sola: ~1.5 KB por slot
- 6 slots con fixtures: ~7-9 KB
- API keys (5) encriptadas + metadata: ~750 bytes
- Credenciales S3 encriptadas: ~400 bytes
- Preferencias UI, path LAST, timestamps, estado: ~800 bytes
- **Total Config: ~9-11 KB sin métricas, ~16-20 KB si el usuario serializa fixtures con métricas también**
- Trivial técnicamente, JSON plano sin encriptación en primera instancia

---

### 3.6 Capa 6 — Outputs de Scoring

**Rol:** persistencia y distribución de señales emitidas por el Scoring Engine.

#### Schema de la tabla `signals` — Opción híbrida 3

Decidido: **columnas planas + blobs JSON + candles_snapshot gzip**.

**Columnas obligatorias:**

- `engine_version` (terna spec)
- `fixture_id` (terna spec)
- `fixture_version` (terna spec)
- `slot_id` (spec)
- `candle_timestamp` — timestamp del candle de 15M analizado (hora ET del cierre)
- `compute_timestamp` — timestamp del momento del cálculo (wall clock del backend)
- `ticker`
- `score` (puede ser null si blocked/error)
- `conf` (banda: REVISAR/B/A/A+/S/S+)
- `signal` (boolean)
- `dir` (call/put/null)
- `blocked` (boolean)
- `error` (boolean)
- `error_code` (FIX-XXX/ENG-XXX/null)

**Blobs JSON (columnas):**

- `layers_json` — desglose completo (estructura, triggers, confirms, risks, dedup trail)
- `ind_json` — indicadores calculados
- `patterns_json` — patrones detectados con pesos y decay
- `sec_rel_json` — datos de fuerza sectorial
- `div_spy_json` — datos de divergencia SPY

**Snapshot de inputs (columna blob gzip):**

- `candles_snapshot_gzip` — todas las candles pasadas al motor (daily + 1H + 15M + spy_daily si aplicaba + bench_daily si aplicaba), comprimidas gzip

**Peso estimado:** ~3 KB por señal con snapshot comprimido. Con 6 slots × 26 scans/día = 156 señales/día → ~450 KB/día → ~160 MB/año. Trivial en SQLite.

#### Trazabilidad completa — Opción C

- Terna spec completa
- Timestamps dobles (candle vs cómputo) — diferencia revela delay de fetch/scan
- Snapshot completo de inputs

**Valor operativo:**

- Reproducibilidad perfecta (cualquier señal se re-ejecuta localmente con los mismos inputs)
- Detección de bugs post-hoc (motor actualizado vs señales viejas con el motor nuevo)
- Auditoría legal/formal

#### Evento `signal.updated` — descartado

No existe. Las señales son inmutables una vez escritas. Si el motor se actualiza, las señales viejas NO se re-procesan; quedan como histórico del estado en el momento del cálculo.

#### Canales de distribución

- **DB persistencia completa** — tabla `signals` (todo)
- **WebSocket push al Cockpit** — SIN el snapshot (demasiado pesado para push continuo); envía las columnas planas + layers + ind + patterns resumidos + **`chat_format` listo** (ver abajo). El snapshot se consulta bajo demanda vía REST si se necesita.
- **REST con paginación cursor** — para Memento y consultas históricas. Default 100, máximo 500 por página.

#### Campo `chat_format` en payload del WebSocket (v1.1.0)

Cada push de `signal.new` incluye un campo **`chat_format: string`** que contiene el texto multilinea ya armado para que el trader lo copie al chat con Claude. **El backend genera el texto**, el frontend solo lo pasa a `navigator.clipboard.writeText()` al presionar el botón.

**Razones:**

- Template centralizado en backend (cambios futuros en un solo lugar).
- UX instantánea (sin round-trip HTTP al presionar el botón).
- El peso extra (~800 bytes por push, 1 señal/15min/slot) es trivial.

**Template v1.1.0** — rediseñado respecto al `genCT` del v4.2.1, organizado en bloques semánticos (PRECIO · CONTEXTO · VOLUMEN · FUERZA RELATIVA · NIVELES · EVENTOS · PATRONES · SCORING · RESULTADO · Meta). Los bloques EVENTOS y FUERZA RELATIVA se eliden si no aplican. Referencia visual completa en `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` sección 7.

**Consecuencia arquitectónica:** el panel de detalle técnico del Cockpit **espeja los bloques de este template** — misma organización semántica en UI y en chat. El botón "Copiar al chat" toma ese mismo contenido y lo aplana a texto.

#### Endpoints REST (públicos, con auth)

- `GET /api/v1/signals/latest` — última señal por slot
- `GET /api/v1/signals/history?slot_id=N&from=...&to=...&cursor=...` — histórico paginado
- `GET /api/v1/signals/{id}` — señal completa con snapshot (bajo demanda)
- `GET /api/v1/engine/health` — estado del Scoring Engine (resultado del último healthcheck)

#### Tabla `heartbeat`

- Guarda estado de cada motor/servicio cada 2 min
- TTL 24h — se limpia al reiniciar el backend (no persiste entre sesiones)
- Permite al trader ver si un motor cayó en algún momento del día

#### Tabla `system_log`

- Logs críticos del sistema (arranques, shutdowns, errores fatales, cambios de registry/fixtures)
- Retención 30 días (ver sección 3.7)

---

### 3.7 Capa 7 — Persistencia

**Rol:** capa de almacenamiento. Módulo `db/` + Database Engine (proceso que supervisa rotación).

#### Tecnología

- **SQLite en primera instancia** (archivo único)
- **Arquitectura preparada desde día 1 para Postgres** — capa de abstracción (SQLAlchemy 2.0 async recomendado) aísla el motor de SQL concreto
- Motivo de preparación: distribución a amigos/clientes a mediano plazo

#### Dos DBs físicamente separadas

- **DB operativa** — `data/scanner.db` — datos vivos del día a día
- **DB archive** — `data/archive/scanner_archive.db` — histórico rotado, **sin límite de tamaño**

#### Rotación

- Shutdown graceful dispara la rotación (opcional configurable)
- Botón manual "Correr limpieza ahora" en Dashboard (ver sección 5.3)
- Rotación = mover filas vencidas de la DB operativa al archive según política de retención

#### Políticas de retención (DB operativa)

| Tabla | Retención operativa | Después |
|---|---|---|
| `signals` | 1 año | Archive |
| `heartbeat` | 24h | Se borra (no va a archive) |
| `system_log` | 30 días | Archive |
| `candles_daily` | 3 años | Archive |
| `candles_1h` | 6 meses | Archive |
| `candles_15m` | 3 meses | Archive |

El archive es transparente (Opción X) — las consultas históricas del frontend pueden ir tanto a operativa como a archive según rango de fechas, el backend resuelve.

#### Database Engine (motor supervisor)

- Motor separado del módulo `db/`
- Responsabilidad: supervisar salud del DB (tamaño, fragmentación), correr rotación, ejecutar backups programados
- Tiene piloto propio en Dashboard (verde/amarillo/rojo)
- Se detiene con el resto de motores al apagar el backend

#### Módulo `db/`

- Expone funciones que otros motores importan: `db.write_candle()`, `db.read_signals()`, `db.write_signal(snapshot)`, etc.
- Incluye funciones de ciclo de vida: `db.backup(destination)`, `db.restore(source)`
- Llamadas directas intra-proceso (sin latencia de red)

#### Backup / Restore — S3 compatible

- **Cloud provider:** configurable (S3-compatible: AWS S3, Backblaze B2, Cloudflare R2, etc.)
- **Scope del backup:** solo DB operativa (archive queda local, pesa mucho y es reconstruible)
- **Credenciales:** viven en el Config del usuario (encriptadas)
- **UI:** sección "ONLINE BACKUP" dentro del Paso 1 de Configuración, desplegable con formulario de credenciales + botones Backup/Restore
- **Backup:** `VACUUM INTO` para snapshot atómico sin detener el backend → comprime → sube al bucket
- **Restore:** baja del bucket → descomprime → reemplaza la DB local (requiere que el trader confirme)
- **Versionado de backups en S3:** timestamp en nombre de archivo (decisión default — revisable; alternativas: overwrite único, mantener últimos N)
- Uso principal: abrir scanner en máquina nueva y recuperar estado completo


---

## 4 · Reglas transversales

Decisiones que cruzan múltiples capas/motores.

### 4.1 Comunicación entre motores

**Decisión:** llamadas directas intra-proceso (memoria), **no HTTP ni WebSocket interno**.

- Motivo: todos los motores corren en el mismo proceso Python del backend. Meter HTTP entre ellos agregaría serialización + overhead sin beneficio.
- Implementación: cada motor expone sus funciones públicas como métodos de su clase. Otros motores las importan y llaman directamente.
- Latencia: microsegundos.

**Externamente** (hacia el frontend o hacia clientes API):

- **WebSocket** para push en tiempo real (señales, pilotos, banner de API)
- **REST HTTP** para consultas históricas y operaciones puntuales
- **Auth API Key (bearer token)** en todos los endpoints públicos

### 4.2 Gestión de memoria

- Cada motor expone endpoint `/memory` que devuelve su consumo actual en RAM
- **Umbral de alarma: 80%** del límite definido por motor → piloto pasa a amarillo
- **Umbral fatal: 95%** → piloto rojo + código específico (ENG-XXX o nuevo código a definir)
- Límites por motor configurables en Config (pendiente UI para esto — por ahora valores por defecto en código)
- Ring buffers del Data Engine están bajo esta gestión (ver 3.1)

### 4.3 Shutdown graceful

**Flujo al presionar "Detener sistema":**

1. Dashboard admin envía señal de shutdown al backend
2. Data Engine termina descargas en curso (si hay alguna), no acepta nuevas
3. Scoring Engine termina el scan actual (si está corriendo), no acepta nuevos
4. Database Engine dispara rotación si configurada
5. Cada motor reporta "detenido OK" o "timeout"
6. **Timeout general: 30 segundos** (configurable)
7. Si algún motor no responde → aparece botón **"Forzar detención"** en Dashboard
8. Al cerrar: wipe de API keys y credenciales en RAM + DB (ver 4.4)

### 4.4 Persistencia privada

- **API keys y credenciales S3** viven encriptadas en DB durante operación
- Al apagar el backend → se borran de DB y RAM (wipe explícito)
- Al próximo arranque → si se carga Config, se re-leen desde el Config (que está cifrado en esos campos)
- Motivo: máquinas compartidas, protección post-sesión

### 4.5 Monitoreo — heartbeat y pilotos

**Heartbeat cada 2 minutos:**

- Consultado solo por el **Dashboard** (no por el Cockpit — el Cockpit tiene su propio piloto master con lógica distinta)
- Cada motor reporta estado: verde/amarillo/rojo + código si aplica
- Se persiste en tabla `heartbeat` con TTL 24h

**3 colores universales:**

- **Verde** — operativo normal
- **Amarillo** — operativo con advertencia (DEGRADED, warmup, memoria alta, parity check fallido, etc.)
- **Rojo** — no operativo

**Estados especiales:**

- **WARMUP** — se muestra como amarillo con etiqueta "warming up" + spinner + % de progreso

### 4.6 Piloto master del Cockpit

Indicador global en el Cockpit con 3 estados:

- **Verde** — todo el sistema funciona, scan operativo
- **Amarillo** — hay al menos un motor/slot en amarillo O warmup (scan sigue corriendo sobre slots operables)
- **Rojo** — hay al menos un motor en rojo que impide el scan (Data Engine caído, Scoring Engine caído, etc.)

Lógica: rojo gana sobre amarillo, amarillo gana sobre verde. Es el "ojo rápido" del trader.

### 4.7 Sin notificaciones externas

- No hay notificaciones push, email, SMS, Slack
- El trader consulta Dashboard/Cockpit cuando quiere — filosofía pull, no push

### 4.8 Configuración — archivo JSON

- **Formato:** JSON plano (no encriptado en primera versión — campos sensibles como API keys y S3 credentials sí encriptados inline)
- **Nombre convencional:** `config_{nombre}.json` en directorio que el usuario elija
- **Botones en frontend:** Cargar / Guardar / Guardar como / **LAST**
- **LAST** = atajo que carga el último Config usado (ruta persistida aparte en archivo pequeño `last_config_path.txt` en directorio de instalación)
- **Auto-LAST al arrancar:** si existe LAST + está completo → se carga automáticamente y se arrancan motores hasta "operativo"; el frontend salta Paso 4 (arranque manual) e ingresa directo a Dashboard/Cockpit
- **Diálogo "salir sin guardar":** si el Config tiene cambios no guardados y el trader intenta cerrar/cambiar Config → diálogo modal preguntando si guardar

### 4.9 Logs — filesystem

- **Directorio:** `/LOG/` en raíz de instalación
- **Formato:** TXT simple, un archivo por día con timestamp
- **Rotación:** 5 días, se borran al arrancar el backend
- **Contenido:** logs críticos (errores, shutdowns, validator reports), no spam operativo
- **Motor de logging:** Loguru (ver 5.3 — stack)

### 4.10 Sin telemetría

- No se envía info a Anthropic, a Álvaro, a terceros
- Todo queda local (salvo los backups S3 que el usuario configura explícitamente)

### 4.11 Zona horaria — todo en ET con tz-aware (v1.1.0)

El producto opera exclusivamente sobre horario de mercado US (9:30-16:00 ET). **El backend razona y persiste en Eastern Time (`America/New_York`) con tz-aware explícito**, nunca naive.

**Reglas:**

- Todos los `datetime` del código usan `zoneinfo.ZoneInfo("America/New_York")` (Python 3.11 nativo).
- DB guarda timestamps **con tzinfo** (no naive).
- Twelve Data devuelve strings naive ET — el Data Engine los convierte a tz-aware al ingesar.
- Frontend recibe timestamps tz-aware y los muestra tal cual (la zona del trader puede ser UTC-3 Montevideo; en la UI se ve en ET, que es la referencia operativa).
- Daylight Saving Time (marzo/noviembre) lo resuelve `zoneinfo` automáticamente.

**Razones:** alineación con el resto del ecosistema (v4.2.1 y Observatory ya razonan en ET), el producto es mono-zona por definición, elimina bugs de conversión silenciosa de horas enteras.

**Si algún día se necesita UTC para backup portable o integración externa** → se convierte en la frontera, no como convención interna.

### 4.12 Autenticación API (v1.1.0)

**API Key bearer token** en todos los endpoints públicos (REST + WebSocket).

**Lifecycle:**

- **Autogenerado al primer arranque del backend** (random secure, formato `sk-{32-40 hex}`).
- **Mostrado una vez** en la UI de Configuración al completar el primer setup (Paso 4), con botón "Copiar".
- **Persistido encriptado en el Config del usuario** (junto con API keys del provider y credenciales S3).
- **Rotable desde Dashboard** — botón "Rotar token" genera uno nuevo, invalida el anterior, fuerza re-login del frontend.
- **Un solo token activo por deployment** en primera versión (single-user asumido).

**REST:** header `Authorization: Bearer sk-...`.
**WebSocket:** query param `?token=sk-...` en el handshake inicial.
**Sin auth:** el backend rechaza con HTTP 401 (REST) o close code 4001 (WS).

---

## 5 · Stack técnico — Opción 4 completa

### 5.1 Backend

- **Lenguaje:** Python 3.11
- **Framework HTTP:** FastAPI
- **WebSocket:** nativo de FastAPI (Starlette)
- **Server:** Uvicorn single-worker (single worker porque los motores comparten estado en memoria; múltiples workers romperían el modelo)
- **ORM:** SQLAlchemy 2.0 async
- **Migrations:** Alembic
- **Logging:** Loguru
- **Testing:** pytest + pytest-asyncio
- **Gestor de dependencias:** `uv`

### 5.2 Frontend

- **Framework:** React + TypeScript
- **Bundler:** Vite
- **Styling:** Tailwind CSS + shadcn/ui (componentes pre-armados, accesibles, copy-paste, sin runtime overhead)
- **State:** Zustand (lightweight, sin boilerplate de Redux)
- **Data fetching / cache:** TanStack Query (React Query) — maneja invalidación, polling, retries
- **Nodo-conexión (Paso 3 Config):** React Flow
- **Gráficos financieros (Cockpit):** Lightweight Charts (TradingView) — servido localmente como dependencia, sin embed
- **Testing:** Vitest
- **Gestor de dependencias:** `pnpm`

### 5.3 Protocolo y API

- **Formato de payloads:** JSON
- **Documentación API:** OpenAPI (FastAPI lo genera automáticamente)
- **Versionado:** todos los endpoints bajo `/api/v1/`
- **WebSocket envelope:** `{ event: "signal.new" | "slot.status" | ..., timestamp: ISO8601 (ET tz-aware), payload: {...} }`
- **Auth:** ver §4.12. API Key bearer token en REST (`Authorization: Bearer sk-...`) y en query param `?token=` en el handshake del WebSocket.

#### Catálogo de eventos WebSocket (v1.1.0)

Catálogo mixto de **6 eventos**, diseñado para aislar los que tienen latencia crítica (señales) de los que varían seguido (estados del sistema). Cada uno con su formato de payload estable:

| Event | Frecuencia típica | Payload (resumen) | Uso |
|---|---|---|---|
| `signal.new` | 1/15min/slot operativo | columnas planas + `layers` + `ind` + `patterns` resumidos + **`chat_format` listo** (sin snapshot) | Nueva señal emitida por el Scoring Engine |
| `slot.status` | al cambiar estado de un slot (incluye warmup progress) | `{slot_id, status: "warmup"|"operational"|"degraded"|"error", warmup_progress?: 0-100, error_code?: string}` | Cambios de estado por slot |
| `engine.status` | al cambiar estado de un motor | `{engine: "data"|"scoring"|"database"|"validator", status: "green"|"yellow"|"red"|"offline", memory_pct?: number, error_code?: string}` | Cambios de estado de motor |
| `api_usage.tick` | al usarse una API key (no polling) | `{key_id, used_minute, max_minute, used_daily, max_daily, last_call_ts}` | Actualización del banner de API del Cockpit |
| `validator.progress` | durante corridas del Validator | `{run_id, test_id: "D"|"A"|"B"|"C"|"E"|"F"|"G", status: "running"|"pass"|"fail"|"pending", message?: string}` | Progreso de batería de tests |
| `system.log` | eventos puntuales | `{level: "info"|"warning"|"error", source, message, error_code?: string}` | Feed de logs crítico para Dashboard |

**Throttling:** `api_usage.tick` es el único susceptible de ruido; se emite **solo cuando una key tiene actividad real** (no polling constante). Los demás son event-driven por diseño.

**Razones del catálogo mixto:**

- `signal.new` aislado porque es sensible a latencia y lleva payload pesado (layers + chat_format).
- `slot.status` / `engine.status` agrupan cambios frecuentes de estado pero conservan estructura granular (el frontend sabe exactamente qué re-renderizar).
- `api_usage.tick` separado porque su cadencia es distinta.
- `validator.progress` solo aparece durante corridas; frontend se suscribe on-demand.
- `system.log` como canal abierto para el feed de Dashboard.

#### Endpoints REST principales

Ver §3.6 para catálogo completo. Todos bajo `/api/v1/` con auth bearer token obligatoria.

### 5.4 Estructura del repo — monorepo

```
scanner-v5/
├── backend/
│   ├── engines/
│   │   ├── data/           # Data Engine
│   │   ├── scoring/        # Scoring Engine (motor puro)
│   │   └── database/       # Database Engine
│   ├── modules/
│   │   ├── validator/      # Validator Module
│   │   ├── slot_registry/  # Slot Registry Module
│   │   ├── config/         # Config loader/saver
│   │   └── db/             # Capa de persistencia
│   ├── api/                # Endpoints FastAPI
│   ├── fixtures/           # Canonicals embebidos en repo
│   │   ├── qqq_canonical_v1.json
│   │   ├── qqq_canonical_v1.sha256
│   │   └── parity_reference/  # Dataset de parity del Validator
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/          # Configuración, Dashboard, Memento, Cockpit
│   │   ├── stores/         # Zustand
│   │   └── api/            # TanStack Query hooks
│   ├── public/
│   └── package.json
├── docs/
│   └── specs/              # Copias sincronizadas manualmente desde el Observatory
│       ├── SCORING_ENGINE_SPEC.md
│       ├── FIXTURE_SPEC.md
│       └── ...
├── data/                   # DBs (gitignored)
│   ├── scanner.db
│   └── archive/
├── LOG/                    # Logs (gitignored)
└── scripts/                # Scripts auxiliares de mantenimiento
```

### 5.5 CI/CD y deployment

- **CI:** manual en primera versión (sin pipeline automatizado)
- **Deployment alfa (desarrollo):** correr backend + frontend por separado con `uv run` y `pnpm dev`
- **Deployment release (distribución):** **ejecutable Windows (.exe)** con Inno Setup
- **Plataforma primaria:** Windows (expansión a Mac/Linux pendiente)
- **Firma digital:** sin firma inicial (el .exe mostrará warning de SmartScreen — aceptable en alfa)
- **Uninstaller:** incluye checkbox "borrar datos y configuración" **por defecto desmarcado** (no perder data accidentalmente)
- **Auto-update:** sin auto-update en v5; el usuario baja manualmente nuevas versiones

### 5.6 Sincronización de specs

- **Manual** — Álvaro edita specs en Observatory, copia manualmente a `docs/specs/` del scanner
- Tabla en README del scanner "Specs pendientes actualizar" registra deriva entre ambos repos
- Snapshot manual a GitHub al final de cada sesión

### 5.7 Migraciones de DB — híbrido `create_all()` + Alembic (v1.1.0)

**Primer arranque en máquina nueva** (típico tras instalación con Inno Setup):

1. Si la DB no existe → `Base.metadata.create_all()` crea todas las tablas desde los modelos SQLAlchemy.
2. Inmediatamente después → `alembic stamp head` marca la versión baseline en `alembic_version`.

**Arranques subsiguientes** (la DB ya existe):

3. `alembic upgrade head` aplica migraciones pendientes si hay.

**Modificaciones futuras al schema** (agregar columna, tabla, índice):

4. El desarrollador genera migración con `alembic revision --autogenerate -m "descripción"`.
5. La migración se versiona en el repo.
6. El próximo arranque en cualquier máquina la aplica automáticamente en el paso 3.

**Razón del híbrido:** `create_all()` evita debuggear una migración genesis manual en la máquina de un usuario (robustez para producto distribuido). Alembic queda armado desde el primer arranque para que los cambios siguientes sigan el flujo estándar sin plumbing extra.

**Convención de archivos:**

- Modelos SQLAlchemy: `backend/modules/db/models.py`
- Config Alembic: `backend/alembic.ini` + `backend/alembic/`
- Migraciones versionadas: `backend/alembic/versions/`

---

## 6 · Frontend — 4 pestañas

### 6.1 Flujo general de arranque

1. Usuario abre scanner → **frontend arranca primero** (motores no corren todavía)
2. Frontend presenta pestaña **Configuración**
3. Usuario configura (o carga LAST)
4. Usuario arranca motores desde Paso 4 de Configuración (o se saltea si LAST completo)
5. Al estar operativo → Dashboard/Cockpit accesibles

**Orden visual de pestañas:** Configuración → Dashboard → Cockpit → Memento

**Orden de diseño/cierre de decisiones:** Configuración (cerrada) → Dashboard (cerrada) → Memento (cerrada) → Cockpit (**cerrada v1.1.0** — las 5 dudas estéticas + los 2 pendientes de contenido resueltos)

### 6.2 Pestaña CONFIGURACIÓN

**Layout:** secciones verticales apiladas con scroll (Opción 2). El trader hace scroll entre los 4 pasos.

**4 pasos (todos visibles simultáneamente, ordenados top-down):**

#### Paso 1 — Config del usuario

- Sección colapsable con:
  - Nombre del Config actual cargado
  - Botones: **Cargar** / **Guardar** / **Guardar como** / **LAST**
  - Subsección plegable **ONLINE BACKUP** (S3):
    - Dropdown de provider (S3, B2, R2, custom endpoint)
    - Campos: endpoint, bucket, access key, secret key (todos encriptados al guardar Config)
    - Botones: **Backup ahora** / **Restore desde cloud**

#### Paso 2 — API Keys

- Hasta **5 keys** configurables
- Por cada key:
  - Campo de valor (enmascarado por default, toggle para mostrar)
  - Campo de créditos por minuto
  - Campo de créditos diarios máximos
  - Toggle activa/inactiva
  - Piloto individual (verde/amarillo/rojo según salud reciente)
- Botón **Test conectividad** por key (valida que el provider responde)

#### Paso 3 — Fixtures + Slot Registry

- **Canvas nodo-conexión estilo Runpod** con 6 slots visibles
- Cada slot (nodo):
  - Número (1-6)
  - Campo ticker (dropdown con watchlist preset SPY/QQQ/IWM/AAPL/NVDA o entrada manual)
  - Campo fixture (dropdown con: canonicals del ticker disponibles + fixtures activas del Config + "Cargar fixture...")
  - Benchmark (auto-populado desde fixture, read-only)
  - Toggle activo/inactivo
  - Piloto de estado en tiempo real
- **Botón "Cargar fixture..."** abre modal con upload de `.json` + `.metrics.json` opcional (o zip)
- Restricción: mínimo 1 slot activo

#### Paso 4 — Arranque de motores

- Lista vertical en orden de dependencia: Database Engine → Data Engine → Slot Registry → Scoring Engine → Validator (corrida inicial)
- Cada motor: botón individual + piloto de progreso + mensaje de estado
- Botón global **"Arrancar todos"** (secuencial respetando dependencias)
- Al final — **Validator corre batería de arranque** con progress bar de 7 tests (D → A → B → C → E → F → G)
- Si batería OK → mensaje "Sistema operativo — ir al Cockpit/Dashboard"
- Si batería detecta Fatal → mensaje + código + log del Validator
- **Auto-LAST saltea Paso 4** completamente (arranque es automático)

### 6.3 Pestaña DASHBOARD

**Rol:** panel admin — estado del sistema, operaciones administrativas.

**Layout A:** vertical apilado con secciones colapsables.

**Header fijo:** Piloto Master global (verde/amarillo/rojo grande, visible siempre).

**4 secciones:**

#### Sección 1 — Motores y servicios

- Grid de cards (uno por motor/servicio): Database Engine, Data Engine, Scoring Engine, Validator, Twelve Data connector, S3 connector
- Cada card:
  - Nombre + piloto
  - Último heartbeat (timestamp relativo: "hace 45s")
  - Uso de memoria actual + % respecto al límite
  - Código de error si amarillo/rojo
  - Botón "ver log" (abre modal con últimos logs del motor)

#### Sección 2 — Slots

- Grid de cards, layout libre en pantalla (no secuencial)
- Cada card:
  - ID de slot + ticker + fixture
  - Piloto de estado
  - Última señal emitida (timestamp + score + confidence)
  - Estado: operativo / warmup con % / DEGRADED con código

#### Sección 3 — Base de datos (Variante 1 — grid cards con barras de progreso)

- Card por tabla (signals, heartbeat, system_log, candles_daily, candles_1h, candles_15m)
- Cada card:
  - Nombre de tabla
  - Filas actuales en DB operativa
  - Barra de progreso hacia límite de retención (colores según proximidad al límite)
  - Filas en archive (si aplica)
- Botón global **"Correr limpieza ahora"** (dispara rotación manual)
- Sección opcional "Últimos backups" con historial del S3

#### Sección 4 — Pruebas de validación

- Botón **Revalidar sistema** (corre batería completa)
- Botón **Test API** (solo categoría G — conectividad)
- **Último reporte Validator (Opción C persistente)** — se muestra siempre con resultado de la última corrida: timestamp + estado general + tabla de 7 categorías con resultado individual + log expandible
- **Heartbeat histórico UI — eliminado.** No se muestra gráfico temporal de heartbeat. Solo el estado actual.

### 6.4 Pestaña MEMENTO

**Rol:** consulta. Solo lectura. Datos estadísticos de fixtures y catálogo de patrones.

**Layout:** 2 secciones colapsables.

#### Sección A — Stats por Slot

- 6 subsecciones colapsables (una por slot activo), **default colapsadas**
- Al expandir un slot, muestra lo que lee desde el `.metrics.json` sibling de la fixture activa:
  - **WR por franja** (B, A, A+, S, S+) con N de señales entre paréntesis
  - **Spread B→S+** (métrica clave)
  - **Progresión monotónica** check (B < A < A+ < S < S+? sí/no)
  - **Uplift marginal por confirm** (FzaRel +12pp, BBinf_1H +8pp, ...)
  - **Cobertura por franja** (% de señales que caen en cada una)
  - **MFE/MAE por franja** (máximo recorrido favorable/adverso) — si están en el sibling
  - **Thresholds check** (umbrales de la fixture vs consenso empírico)
  - **Metadata:** dataset period, bench, fecha de calibración

#### Sección B — Catálogo de Patrones

- **3 subsecciones colapsables:** TRIGGERS / CONFIRMS / RISKS
- Cada una con tarjetas, una por patrón
- Tarjeta de patrón:
  - Nombre (ej. "doji", "FzaRel", "wedge_break_down")
  - Tendencia (bullish/bearish/both)
  - Peso (hardcoded para triggers/risks, desde fixture para confirms — se muestra el de la fixture activa del slot si el usuario selecciona uno)
  - Significado (texto descriptivo hardcoded — lo escribe Álvaro para v1)
  - **Stats globales** (WR @ score ≥ 30, cobertura global) — estas stats las suministra Álvaro manualmente para release
- **Gráfico visual descriptivo del patrón:** NO en v1 (diferido)

### 6.5 Pestaña COCKPIT

**Rol:** pantalla operativa del trader en sesión de mercado.

**ESTADO:** cerrada (v1.1.0). Decisiones estéticas y de contenido resueltas.

#### Decisión estética del producto — W (v1.1.0)

**Icomat como lenguaje visual base del producto entero** (las 4 pestañas). **Runpod como fuente de patrones estructurales** traducidos a la paleta/tipografía icomat.

- **Referencia primaria:** https://www.icomat.co.uk/ — oscuro, industrial, sobrio, limpio. Paleta negra profunda + acentos sutiles, tipografías sans-serif en minúscula, letterspacing generoso, backgrounds discretos, cards minimalistas.
- **Referencia secundaria:** https://www.runpod.io/ — patrones estructurales (nodo-conexión, iconos de sistema, diagramas) aplicados donde la función lo requiere (Paso 3 de Configuración, Dashboard con motores/slots/tablas).
- **No son dos estilos conviviendo** — es un solo estilo (icomat) con vocabulario estructural prestado donde aplica. Los componentes Runpod adoptan los colores/tipografía de icomat, no traen los suyos.

**Consecuencias:**

- **Dashboard:** densidad se resuelve con jerarquía tipográfica + spacing icomat + iconos Runpod funcionales (sin color chillón, sin cards azul-tech).
- **Configuración Paso 3:** canvas nodo-conexión estilo Runpod, pero en paleta icomat.
- **Memento:** naturalmente sobrio, tarjetas de stats con espacios generosos.
- **Cockpit:** minimalismo máximo con disclosure progresiva.

#### Layout cerrado

- **Watchlist izquierda:** 6 cards verticales, una por slot
- **Panel de detalle derecha:** muestra información del slot seleccionado
- **Default:** primera card seleccionada al entrar
- **Importante:** el panel **no salta** automáticamente entre cards cuando otros slots emiten señal (el trader mantiene foco — Decisión A1, explícita)

#### Gráfico

- **Lightweight Charts local** (servido desde frontend, sin embed de TradingView)
- **NO TradingView embed** (decisión firme — razones: estético, control total, sin dependencia externa)
- Botón **"Abrir en TradingView"** como escape al servicio externo del trader

#### Panel derecho — estructura definitiva (v1.1.0)

Tres zonas verticales:

**1. Banner superior (siempre visible, sticky)**

- Ticker + banda (S+/S/A+/A/B/REVISAR) + dirección (CALL/PUT) + score numérico
- **Botón `COPIAR` al chat** (aquí dentro, en el mismo banner)

**2. Resumen ejecutivo (siempre visible, ~8-10 líneas)**

Lo indispensable para decidir operar o no:

- Precio actual + Chg% del día
- Alineación 3/3/dir (ej. "3/3 bullish")
- ATR 15M + dMA200 (volatilidad + tendencia macro)
- Flags críticos (si aplican, uno por línea): catalizador ⚠️, squeeze ⚡, ORB ↑, gap, fuerza relativa extrema
- Vela analizada + timestamp (ej. `vela 14:30 ET · calc +4s`)

**3. Detalle técnico (expandible, colapsado por default)**

Botón **"ver detalle técnico"** expande sección. Estructura **espeja los bloques del template `chat_format` (B3)** — misma organización semántica en UI y en chat. El panel maquetado visualmente lleva los mismos bloques que el texto plano:

`PRECIO · CONTEXTO · VOLUMEN · FUERZA RELATIVA · NIVELES · EVENTOS · PATRONES · SCORING · RESULTADO · Meta`

Contenido:

- **PRECIO:** último, chg día, ATR 15M, dMA200
- **CONTEXTO:** alineación detallada, MAs diarias (20/40/200), BB 1H
- **VOLUMEN:** ratio 15M, ratio 1H, proyección de vela actual, secuencia (↑/↓)
- **FUERZA RELATIVA:** `sec_rel` (benchmark + diff%), `div_spy` si aplica
- **NIVELES:** soportes/resistencias con etiquetas (PD/R1/S1/etc.)
- **EVENTOS:** catalizador, squeeze, ORB, gap (se eliden si no aplican)
- **PATRONES:** lista con tf · dirección · categoría · peso · decay
- **SCORING:** estructura ✓/✗, triggers N(suma), confirms M(suma) tras dedup, bloqueo, conflicto
- **RESULTADO:** score, dirección, confianza, señal
- **Meta:** engine_version, fixture_id + fixture_version, slot_id, `candle_timestamp`, `compute_timestamp`

**Criterio del split:** resumen ejecutivo = decisión, detalle técnico = auditoría.

#### Botón "Copiar al chat" — mecánica (v1.1.0)

- **Ubicación:** banner superior del panel derecho (junto a ticker + banda + dirección + score).
- **Texto del botón:** `COPIAR`
- **Mecánica:** el backend pushea el campo `chat_format` listo dentro del payload de `signal.new` (ver §3.6). El frontend solo hace `navigator.clipboard.writeText(signal.chat_format)` al click.
- **Template del texto:** rediseñado respecto al `genCT` del v4.2.1. Organizado por bloques semánticos (los mismos que estructuran el detalle técnico), bloques opcionales eliden si no aplican, meta de trazabilidad al final. Referencia visual completa del template en `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` sección 7.
- **Ventaja arquitectónica:** el panel de detalle y el texto copiado muestran la misma información organizada de la misma manera. El trader mentalmente no cambia de esquema al pasar de uno a otro.

#### Scan manual

- Botón **"Scan ahora"** corre scan sobre todos los slots excepto los vacíos
- No hay scan individual por slot

#### Mostrar solo la última señal

- El Cockpit muestra solo la señal más reciente por slot, no un feed cronológico
- Para feed histórico → Memento o endpoint REST

#### Alertas visuales por banda de confianza (v1.1.0 — sobrias dentro de icomat)

- **REVISAR:** gris neutro
- **B:** azul claro
- **A:** azul más profundo
- **A+:** magenta con glow sutil
- **S:** dorado con glow marcado
- **S+:** negro metalizado con glow + **pulse lento en la letra S+ y en los bordes de la card** (no flash — animación controlada coherente con icomat; la disonancia intencional se mantiene pero dentro del lenguaje sobrio)
- **Bordes de la card de watchlist:** reflejan el color de la franja

#### Banner superior — API calls

Visible arriba del cockpit, muestra el estado de los créditos en tiempo real:

- **"Créditos/min":** 5 barras horizontales, una por API key. Cada una:
  - Label con nombre/alias de la key
  - Texto "X/Y" (usados/máximo del minuto)
  - Barra de progreso que se llena hacia el máximo
  - Timestamp "hace Ns" de la última llamada
- **"Créditos diarios":** suma consolidada de las keys, con progress bar hacia el máximo diario total
  - **Reseteo al final del día** (no medianoche UTC)

Los datos llegan por el evento WebSocket `api_usage.tick` (ver §5.3).

#### Lo que NO tiene el Cockpit

- **No tiene feed cronológico** (es Memento)
- **No tiene métricas del día agregadas** (P&L, R-ratio, etc. — esas viven en journal.html externo)

---


## 7 · Códigos de error nuevos a agregar

Se deben añadir a `FIXTURE_ERRORS.md` en el Observatory y copiar al scanner.

| Código | Severidad | Capa | Significado |
|---|---|---|---|
| `ENG-050` | Warning (amarillo) | Scoring | Parity check fallido — el motor devolvió output distinto al esperado en healthcheck o parity exhaustivo |
| `ENG-060` | Warning (amarillo) | Data Engine | Ticker sin datos durante N ciclos consecutivos (default N=3 ≈ 45 min de mercado). El slot pasa a DEGRADED. Se auto-recupera al primer fetch exitoso posterior. (v1.1.0) |
| `MET-001` | Fatal/Warning según contexto | Fixtures | Archivo sibling `.metrics.json` no encontrado (fatal si canonical `status: final`, warning si activa) |
| `MET-002` | Fatal | Fixtures | Schema del sibling `.metrics.json` inválido |
| `MET-003` | Fatal | Fixtures | Canonical con `status: final` tiene sibling con confirms incompletos (no todas las 10 categorías de `confirm_weights` tienen métricas) |
| `MET-004` | Fatal | Fixtures | Inconsistencia entre `status` declarado en la fixture y completitud del sibling |
| `MET-005` | Fatal | Fixtures | Hash del sibling desincronizado con el hash de la fixture (cambió una sin la otra) |
| `MET-006` | Warning | Fixtures | Thresholds de la fixture inconsistentes con los observados en el sibling (umbral de la fixture no coincide con el consenso empírico — informativo, no bloquea) |

Los códigos MET-XXX están alineados con `METRICS_FILE_SPEC.md` (spec del sibling, a crear en Observatory).
`ENG-060` es nuevo en v1.1.0 — agregar a `FIXTURE_ERRORS.md` (ver §8 abajo).

---

## 8 · Specs a actualizar al cierre de sesión

Lista consolidada. Álvaro edita en Observatory → copia manual a `docs/specs/` del scanner.

1. **`SCORING_ENGINE_SPEC.md` sección 2.2** — aclarar que los mínimos 40/25/25 son para que el motor corra; el scanner v5 live descarga 210/80/50 para operación completa con todos los indicadores definidos.

2. **`SLOT_REGISTRY_SPEC.md` sección 7** — documentar que el scanner v5 live **SÍ soporta hot-reload por slot**, contra la nota original que decía "no hay hot-reload en v5.x". Describir el flujo (secuencia de 5 pasos desde que el trader introduce ticker hasta que el slot vuelve a operativo).

3. **`FIXTURE_ERRORS.md` sección 3** — agregar entradas para `ENG-050`, `ENG-060` (v1.1.0) y `MET-001` a `MET-006` con descripción, severidad, acción sugerida.

4. **`FIXTURE_ERRORS.md` sección 6 (tabla resumen)** — agregar los 8 códigos nuevos a la tabla global (`ENG-050` + `ENG-060` + `MET-001..006`).

5. **`SCANNER_V5_DEV_HANDOFF.md` sección 3.1** — documentar trazabilidad completa en DB (Opción C) con snapshot de inputs gzip.

6. **`FIXTURE_SPEC.md`** — clarificar que:
   - Múltiples canonicals por ticker pueden coexistir (no una sola)
   - Las métricas de calibración viven en archivo sibling `.metrics.json` separado, NO como sexto bloque interno
   - `METRICS_FILE_SPEC.md` es el documento que define el schema del sibling (a crear)
   - El scanner v5 live NO edita, NO aprueba, solo consume

7. **`CANONICAL_MANAGER_SPEC.md` sección 2.1** — remover la UI 2 (dashboard admin del scanner) del diagrama de arquitectura del Canonical Manager. Queda solo UI 1 (CLI del Observatory). El scanner no aloja el manager.

8. **`METRICS_FILE_SPEC.md`** (nuevo documento a crear en Observatory) — define el schema del archivo sibling `.metrics.json`, sus campos obligatorios por status (draft/final), validaciones, y los códigos MET-XXX.

---

## 9 · Preguntas abiertas acumuladas

Se documentan para que el próximo chat de desarrollo o sesión de diseño las retome en el momento oportuno. No bloquean arrancar el desarrollo de las capas ya cerradas.

### 9.1 Cockpit — CERRADA (v1.1.0)

Los 7 items que bloqueaban el `FRONTEND_FOR_DESIGNER.md` están resueltos. Se dejan listados tachados para trazabilidad.

1. ~~Tensión Runpod vs Icomat~~ → **resuelto con W**: icomat base global, Runpod como patrones estructurales traducidos (ver §6.5).
2. ~~Densidad vs minimalismo~~ → **resuelto**: minimalismo máximo con disclosure progresiva.
3. ~~Coherencia de animaciones S+/S/A+/A con estilo~~ → **resuelto**: animaciones sobrias dentro del lenguaje icomat (pulse lento en S+, glow controlado).
4. ~~Icomat como referencia para DESIGNER~~ → **resuelto**: sí, referencia primaria.
5. ~~Ámbito de icomat~~ → **resuelto**: las 4 pestañas (con Runpod aportando estructura donde aplica).
6. ~~Campos resumen ejecutivo vs detalle técnico~~ → **resuelto**: split definitivo en §6.5.
7. ~~Texto exacto del "Copiar al chat"~~ → **resuelto**: template B3 rediseñado, backend genera `chat_format` listo en payload `signal.new` (§3.6).

### 9.2 Validación y testing

1. ~~Dataset de referencia concreto para el parity test exhaustivo~~ — **resuelto**: 30 sesiones de QQQ 2025 (245 señales), seed fijo=42. Ver `backend/fixtures/parity_reference/README.md`.
2. ~~Formato del snapshot de referencia en `parity_reference/`~~ — **resuelto**: JSON monolítico (`parity_qqq_sample.json`).

### 9.3 Fixtures y métricas

3. Decisión final de obligatoriedad del sibling `.metrics.json` por status (draft vs final) — resuelta en este documento, pero `METRICS_FILE_SPEC.md` aún no existe formalmente.
4. Naming exacto del archivo sibling: `.metrics.json`, `.metrics_v1.json`, otro.
5. Mecanismo preferido para distribuir canonicals nuevas al scanner (update del release vs upload manual — ambos permitidos, pero cuál es el canal principal).

### 9.4 Persistencia

6. Versionado de backups en S3 (timestamp por archivo, overwrite, últimos N) — tentativo timestamp, revisable.
7. Valores por defecto de los ring buffers de candles por timeframe en Data Engine.
8. Política de retención más agresiva si DB operativa crece demasiado — umbral de disparo (~5 GB? ~10 años?).

### 9.5 Scoring y monitoreo

9. Color/animación del spinner de "cargando datos" en Cockpit cuando hay déficit de créditos.
10. Qué hacer si un slot asigna ticker sin canonical en el release (rechazar en UI, fallback, permitir con warning) — ya resuelta: rechazar en UI, revisar si el UI lo implementa correctamente.
11. Límites de memoria por defecto por motor (80% de qué valor base) — a definir en implementación.

### 9.6 Deployment

12. Cuándo pasar a Mac/Linux (post v5 según roadmap implícito).
13. Cuándo firmar digitalmente el .exe (cuando haya presupuesto/necesidad).

### 9.7 Observatory-scanner sync

14. Automatizar sync de specs entre Observatory y scanner (hoy es manual con tabla en README).

### 9.8 Nuevas — del barrido de backend del 20-abril (v1.1.0)

15. **Detección de gaps en la DB local** del Data Engine (cómo decidir "hasta dónde rellenar" cuando se detecta vela faltante tras periodos offline, feriados, half-days). Resolver al programar Capa 1.
16. **Umbral exacto de ENG-060** — tentativo 3 ciclos consecutivos (≈45 min). Confirmar al programar Capa 1 con criterio empírico.

---

## 10 · Workflow y reglas de sesión

Reglas que gobiernan cómo Álvaro y Claude trabajan juntos. Deben respetarse en todo chat de desarrollo futuro.

### 10.1 Idioma y tono

- **Todo en español.** Tono directo, técnico, sin relleno.
- **Saludo inicial obligatorio en cada chat nuevo:** "¡Qué bolá asere! en qué pinchamos hoy?" (o variante equivalente acordada por el usuario).
- Sin saludo especial al cerrar sesión.

### 10.2 Formato de respuesta para decisiones

Cuando se plantea una decisión de diseño o implementación, Claude presenta:

- **Interrogante** (qué hay que decidir)
- **Opciones** (2-4 opciones concretas, nombradas)
- **Ventajas** de cada una
- **Desventajas** de cada una
- **Problemas futuros** anticipados
- **Recomendación** propia (con justificación breve)

Esto permite a Álvaro decidir con información completa. El rol de Claude es **ayudar a decidir, no imponer**.

### 10.3 Workflow de implementación

1. **Discusión completa** del cambio antes de implementar (Claude no genera código hasta que la discusión cierre)
2. **Confirmación explícita del usuario:** "ejecuta" (o equivalente)
3. **Ejecución** (generar código/docs/modificaciones)
4. **Verificación** con Álvaro antes de pasar al siguiente punto

### 10.4 Separación de roles

- **Claude:** recopilador de decisiones, asistente de implementación, generador de código y docs, validador de coherencia
- **Álvaro:** decisor final, calibrador empírico (en Observatory), validador de que los outputs coincidan con su visión
- **DESIGNER (rol externo a los chats):** responsable del diseño visual detallado del frontend, recibe el documento `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` como briefing

### 10.5 Sincronización entre chats

- Cada chat de desarrollo **debe leer este documento antes de empezar**
- Cambios de decisiones en chats nuevos → actualizar este documento
- Snapshot del repo a GitHub al cierre de cada sesión

### 10.6 Estilo de decisiones

- **Álvaro prefiere decisiones firmes y explícitas** sobre acumular configurabilidad. "Mejor 1 manera clara de hacer algo que 5 opciones".
- Configurabilidad se agrega solo si hay necesidad operativa concreta.

---

## 11 · Desvíos explícitos de specs originales

Lista de puntos donde este documento modifica o extiende los specs del Observatory. Son decisiones conscientes, justificadas, y deben reflejarse en los specs al actualizarlos (ver sección 8).

1. **Hot-reload por slot activado.** `SLOT_REGISTRY_SPEC.md` decía "no hay hot-reload en v5.x". Scanner v5 live lo habilita para los 3 escenarios (arranque con tickers nuevos, swap en caliente, activación de slot libre). Los otros 5 slots siguen operando durante el swap.

2. **Warmup 210/80/50 vs mínimos 40/25/25.** `SCORING_ENGINE_SPEC.md` sección 2.2 lista mínimos de 40/25/25 candles. Scanner live descarga 210/80/50. No es contradicción: los mínimos son "lo menos para que el motor corra", el warmup real es "lo necesario para que todos los indicadores estén plenamente definidos".

3. **Métricas de calibración como archivo sibling, no sexto bloque interno.** `FIXTURE_SPEC.md` tiene 5 bloques. Durante la sesión se evaluó un sexto bloque `calibration_metrics` interno, pero la decisión final fue **archivo sibling `.metrics.json`** separado. Razones: mantiene la fixture limpia, permite versionado independiente, facilita consumo por MEMENTO. Formalizado en `METRICS_FILE_SPEC.md` (a crear en Observatory).

4. **Trazabilidad completa (Opción C) por default en scanner live.** La spec no exigía snapshot completo de candles en DB. Scanner v5 live lo persiste por default. Costo aceptable (~160 MB/año), beneficio alto (reproducibilidad perfecta, auditoría legal).

5. **Canonicals coexisten (múltiples por ticker).** La spec original no prohibía, pero tampoco lo pedía explícitamente. Scanner v5 live requiere que puedan coexistir para permitir A/B silencioso entre canonicals aprobadas por Observatory.

6. **Canonical Manager vive solo en Observatory.** `CANONICAL_MANAGER_SPEC.md` sección 2.1 listaba dos UIs (Observatory CLI + Dashboard del scanner). Scanner v5 live **no aloja el manager**. Remover UI 2 del spec.

7. **Fixtures activas viven dentro del archivo Config del usuario.** Las spec no especificaban la ubicación operativa de fixtures no canonicals. Decisión: serializadas dentro del Config. Razón: portabilidad, evitar accidentes de compartir fixtures experimentales.

8. **Data Engine consulta la DB local antes de fetchear el provider** (v1.1.0). Ningún spec lo documentaba explícitamente. Scanner v5 live lo implementa como optimización estándar: si la vela requerida ya está en DB (dentro de ventanas de retención: daily 3 años, 1H 6 meses, 15M 3 meses), no se descarga. Reduce drásticamente llamadas a Twelve Data en escenarios de re-arranque cotidiano y hot-reload con tickers ya vistos.

9. **Retry policy con DEGRADED escalonado** (v1.1.0). Los spec viejos no definían el comportamiento ante fallo de fetch de un ticker individual. Decisión: retry corto + skip del ticker en el ciclo; tras 3 ciclos consecutivos fallidos, slot pasa a DEGRADED con código `ENG-060`. Se auto-recupera al primer éxito.

10. **Zona horaria ET tz-aware** (v1.1.0). Convención interna del backend explícita: `zoneinfo.ZoneInfo("America/New_York")`, timestamps en DB con tzinfo. Ningún spec fijaba esto anteriormente; producto es mono-zona por diseño.

11. **Auth API bearer token autogenerado** (v1.1.0). No había decisión previa sobre autenticación. Scanner v5 live genera token al primer arranque, lo encripta en Config, permite rotación desde Dashboard.

---

## 12 · Referencias cruzadas

### 12.1 Documentos del repo del scanner al cierre de sesión

- `SCANNER_V5_FEATURE_DECISIONS.md` **(este documento — fuente de verdad de decisiones)**
- `SCANNER_V5_HANDOFF_CURRENT.md` (handoff compacto para chat nuevo)
- `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` (briefing para DESIGNER — parcial, Cockpit TBD)
- `docs/specs/*.md` (copias sincronizadas desde Observatory)

### 12.2 Documentos del Observatory (lectura del scanner)

- `SCORING_ENGINE_SPEC.md` v5.2.0
- `FIXTURE_SPEC.md` v1.0.0 (a actualizar según sección 8)
- `SLOT_REGISTRY_SPEC.md` (a actualizar según sección 8)
- `CANONICAL_MANAGER_SPEC.md` (a actualizar según sección 8)
- `CALIBRATION_METHODOLOGY.md` (sin cambios)
- `FIXTURE_ERRORS.md` (a actualizar según sección 8)
- `METRICS_FILE_SPEC.md` (a crear)
- `SCANNER_V5_DEV_HANDOFF.md` (referencia histórica)

### 12.3 Referencias visuales

- **Runpod** (https://www.runpod.io) — referencia de patrones estructurales (nodo-conexión, iconos, diagramas) aplicados en Paso 3 Configuración y Dashboard
- **icomat.co.uk** — referencia estética primaria del producto entero (las 4 pestañas), en paleta icomat con vocabulario Runpod donde aplica
- **Scanner v4.2.1 HTML monolítico** — referencia conceptual de funcionalidad (no de código)

---

## 13 · Estado de la sesión al cierre (v1.1.0)

- **Arquitectura de 7 capas:** 100% cerrada
- **Transversales:** 100% cerradas (v1.1.0 agrega §4.11 zona horaria + §4.12 auth API)
- **Stack técnico:** 100% cerrado (v1.1.0 agrega §5.3 catálogo WebSocket + §5.7 Alembic genesis)
- **Frontend — Configuración:** 100% cerrada
- **Frontend — Dashboard:** 100% cerrado
- **Frontend — Memento:** 100% cerrado
- **Frontend — Cockpit:** **100% cerrado (v1.1.0)** — estética W + split resumen/detalle + botón COPIAR en banner + template B3
- **Specs del Observatory a actualizar:** 8 items identificados (sin cambios, pero §8 items 3-4 ampliados con ENG-060)
- **Códigos de error nuevos:** **8 definidos** (`ENG-050` + `ENG-060` nuevo en v1.1.0 + `MET-001..006`)
- **Preguntas abiertas:** 14 no-Cockpit + 2 nuevas del barrido backend = **16 vivas** (21 originales − 7 Cockpit cerradas + 2 nuevas)
- **Decisiones del barrido backend (v1.1.0):** 6 tomadas — catálogo WebSocket mixto, ET tz-aware, warmup paralelo + DB local, retry ENG-060, chat_format en payload, Alembic híbrido

**Bloqueantes reales remanentes:**
- **Para DESIGNER:** ninguno. `FRONTEND_FOR_DESIGNER.md` v2.0.0 se puede generar completo con el contenido de este doc.
- **Para Capa 1 Data Engine:** ninguno bloqueante. Pendientes resolubles durante implementación (gap detection, umbral exacto ENG-060, ring buffer defaults).
- **Para Capa 2 Validator:** ninguno bloqueante. Dataset parity resuelto (30 sesiones QQQ 2025 en JSON monolítico — ver `backend/fixtures/parity_reference/README.md`).

**Siguientes pasos sugeridos:**

1. Generar `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` v2.0.0 completo (Cockpit resuelto) y entregarlo al diseñador.
2. Arrancar desarrollo de Capa 1 (Data Engine) en chat nuevo con este doc + `HANDOFF_CURRENT` + `scanner_v4_2_1.html` (para round-robin) como inputs.
3. Actualizar los 8 specs del Observatory (§8) en paralelo.
4. Definir dataset parity exhaustivo con Álvaro para desbloquear Capa 2.

---

## 14 · Historial del documento

| Versión | Fecha | Cambios |
|---|---|---|
| 1.0.0 | 2026-04-20 | Documento inicial. Consolidación de sesión de diseño 19-20 abril 2026. Arquitectura 7 capas, stack, transversales, 3 pestañas cerradas, Cockpit 70% + 21 preguntas abiertas |
| 1.1.0 | 2026-04-20 | Barrido de backend (6 decisiones: WebSocket mixto, ET tz-aware, warmup paralelo + DB local, retry ENG-060, chat_format, Alembic híbrido) + cierre total del Cockpit (estética W, split resumen/detalle, botón COPIAR en banner, template B3). Agrega §4.11, §4.12, §5.7, reescribe §6.5. Cierra 7 preguntas de Cockpit, agrega 2 nuevas. Nuevo código `ENG-060`. 4 desvíos adicionales documentados (#8 a #11) |

---

**Fin de `SCANNER_V5_FEATURE_DECISIONS.md` v1.1.0.**
