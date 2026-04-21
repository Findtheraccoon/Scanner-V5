# SCANNER_V5_HANDOFF_CURRENT.md

> **Propósito:** briefing compacto para arrancar un chat nuevo de desarrollo del Scanner v5 live. Leer este documento primero, luego `SCANNER_V5_FEATURE_DECISIONS.md` para el detalle completo de cada decisión. El diseño está cerrado; los próximos chats ejecutan implementación.

**Última actualización:** 2026-04-20 · **Estado:** diseño 100% cerrado. Listo para arrancar desarrollo.

---

## Saludo obligatorio

Al iniciar cualquier chat con Álvaro: **"¡Qué bolá asere! en qué pinchamos hoy?"** (o variante equivalente). Sin excepciones.

---

## Jerarquía documental (regla inviolable)

Cuando un spec viejo del Observatory y los 3 docs operativos del scanner v5 se contradicen, los 3 docs operativos **siempre ganan**. Son verdad final. Los specs son referencia pero no mandan.

Los 3 docs operativos (en orden de prioridad):

1. `SCANNER_V5_FEATURE_DECISIONS.md` — fuente de verdad de decisiones (~1450 líneas)
2. `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` — briefing visual al diseñador
3. `SCANNER_V5_HANDOFF_CURRENT.md` — este documento

Nunca plantear tensiones con specs viejos como si ambas fuentes tuvieran el mismo peso.

---

## Qué es el Scanner v5 live

Scanner de trading de opciones (0DTE/1DTE) que opera sobre mercado en vivo con 6 slots de tickers paralelos. Por default trae 5 tickers preset (SPY/QQQ/IWM/AAPL/NVDA) y un slot libre para configurar a gusto del trader. Reemplaza al scanner v4.2.1 HTML monolítico.

**Relación con Signal Observatory:** el Observatory es proyecto hermano que vive en paralelo — calibra canonicals, genera métricas empíricas, es fuente de verdad de aprobación. El scanner live **consume, no calibra**.

---

## Contexto del usuario

- **Álvaro** — paper trader de opciones, TradingView, habla español.
- **Workflow:** discusión → "ejecuta" → ejecución. No decisiones unilaterales.
- **Formato de respuesta preferido cuando hay decisiones:** interrogante + opciones + ventajas/desventajas + problemas futuros + recomendación.
- **Idioma:** español, técnico, directo, sin relleno.
- **Estilo de decisiones:** prefiere 1 manera clara sobre acumular configurabilidad.

---

## Arquitectura — 7 capas

```
┌─────────────────────────────────────┐
│ Frontend (React + TS + Tailwind)    │
│  4 pestañas: Config/Dashboard/      │
│  Cockpit/Memento                    │
└────────────┬────────────────────────┘
             │ WebSocket + REST /api/v1/
┌────────────▼────────────────────────┐
│ 7. Persistencia                     │
│    SQLite (→ Postgres preparado)    │
│    DB operativa + DB archive        │
├─────────────────────────────────────┤
│ 6. Outputs Scoring                  │
│    Tabla signals + heartbeat +      │
│    system_log + snapshots gzip      │
│    + chat_format en payload WS      │
├─────────────────────────────────────┤
│ 5. Fixtures                         │
│    Canonicals embebidas + activas   │
│    en Config + sibling .metrics     │
├─────────────────────────────────────┤
│ 4. Scoring Engine (motor PURO)      │
│    analyze() stateless              │
│    invocado secuencial 6 slots      │
├─────────────────────────────────────┤
│ 3. Slot Registry (módulo)           │
│    6 slots, hot-reload por slot     │
├─────────────────────────────────────┤
│ 2. Validator (módulo)               │
│    7 tests D→A→B→C→E→F→G            │
├─────────────────────────────────────┤
│ 1. Data Engine (motor vivo)         │
│    Twelve Data, 5 API keys          │
│    DB local primero, warmup 210/80/50│
└─────────────────────────────────────┘
```

**Flujo del ciclo AUTO:** Cierre vela 15M ET → delay 3s → Data Engine consulta DB local → fetchea gap a Twelve Data → verifica integridad → señal al Scoring → Scoring consulta Slot Registry → invoca `analyze()` secuencial sobre slots operativos → persiste en DB → push WebSocket (`signal.new` con `chat_format` listo) al Cockpit. Latencia típica: ~4-5 segundos.

---

## Estructura del repo — monorepo (§5.4 de FEATURE_DECISIONS)

```
scanner-v5/
├── backend/
│   ├── engines/
│   │   ├── data/           # Data Engine (motor vivo)
│   │   ├── scoring/        # Scoring Engine (motor puro)
│   │   └── database/       # Database Engine (supervisor rotación/backup)
│   ├── modules/
│   │   ├── validator/      # Validator Module
│   │   ├── slot_registry/  # Slot Registry Module
│   │   ├── config/         # Config loader/saver
│   │   └── db/             # Capa de persistencia (funciones SQLAlchemy)
│   ├── api/                # Endpoints FastAPI + WebSocket
│   ├── fixtures/           # Canonicals embebidos + parity_reference/
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/components/ pages/ stores/ api/
│   └── package.json
├── docs/specs/             # Copias sincronizadas desde Observatory
├── data/                   # DBs (gitignored)
├── LOG/                    # Logs (gitignored)
└── scripts/
```

**Nota clave:** `engines/database/` (supervisor con ciclo de vida) ≠ `modules/db/` (funciones de acceso importadas por otros motores). Dos cosas distintas, ambas intra-proceso.

---

## Stack técnico

**Backend:** Python 3.11 + FastAPI + Uvicorn single-worker + SQLAlchemy 2.0 async + Alembic + Loguru + pytest + `uv`.

**Frontend:** React + TypeScript + Vite + Tailwind + shadcn/ui + Zustand + TanStack Query + React Flow (nodo-conexión) + Lightweight Charts (gráficos financieros) + Vitest + `pnpm`.

**Protocolo:** JSON + OpenAPI + `/api/v1/` + WebSocket envelope `{event, timestamp, payload}` + Auth API Key bearer (autogenerado al primer arranque).

**Deployment:** alfa sin empaquetar → release `.exe` Windows con Inno Setup (Windows primero, Mac/Linux pendientes; sin firma digital inicial).

**Concurrencia:** proceso Python único, single-worker. Motores son módulos en el mismo proceso. Operaciones pesadas (VACUUM INTO, backup S3) van por `asyncio.to_thread()` para no bloquear el event loop.

**Migraciones DB:** híbrido. Primer arranque → `Base.metadata.create_all()` + `alembic stamp head`. Arranques siguientes → `alembic upgrade head`. Modificaciones futuras → `alembic revision --autogenerate`.

---

## Contrato inmutable — lo que NO se toca

Decisiones previas, ya en los specs del Observatory. Se implementan fielmente:

- **Scoring Engine v5.2.0:** firma `analyze()`, output estructurado, 5 invariantes (stateless/puro/determinístico/no_excepciones/fixture_readonly), pipeline de 5 etapas, 14 triggers hardcoded, 10 confirms externalizados, alignment + conflict inline, ORB time gate ≤10:30 ET, semver estricto.
- **Fixtures:** 5 bloques top-level, reglas duras de schema, canonicals inmutables con hash SHA-256, semver estricto.
- **Slot Registry:** archivo en raíz, exactamente 6 slots, códigos REG-XXX al arranque.
- **4 redundancias del sistema:** validación al arranque + hash canonicals + replay de paridad + fallback graceful por slot.
- **Versionado independiente:** engine, fixtures, registry, canonical_manager suben versiones por separado.

---

## Decisiones clave del scanner v5 live (resumen)

### Data Engine
- Twelve Data, 5 API keys configurables (créditos/min y diarios por key), round-robin proporcional, redistribución dinámica si una key se agota.
- **Consulta DB local antes de fetchear** provider (v1.1.0). Warmup real = gap entre lo que hay en DB y lo necesario.
- Warmup dimensiones totales: 210 daily + 80 1H + 50 15M.
- **Arranque paralelo full** del warmup con `asyncio.gather()` (v1.1.0).
- **Retry policy:** retry corto 1s → skip en ciclo si falla → 3 ciclos consecutivos fallidos → DEGRADED con código `ENG-060`. Auto-recuperación al primer éxito.
- AUTO: cierre 15M ET + delay 3s + integridad + señal. MANUAL: desde botón Cockpit.
- Reset contador diario al cierre de mercado (no medianoche UTC).
- API keys encriptadas en DB, wipe al apagar.
- Ring buffers RAM, DB infinita.

### Validator (módulo, no motor)
- Dispara al arranque + 3 botones Dashboard + automático tras hot-reload.
- 7 categorías D→A→B→C→E→F→G; severidad Fatal/DEGRADED/Warning.
- Test end-to-end usa flag `is_validator_test: true` para no contaminar DB.
- Dataset parity en `backend/fixtures/parity_reference/` (JSON monolítico, 30 sesiones QQQ 2025, 245 señales).
- Reporte JSON al frontend vía `validator.progress` WebSocket event + TXT a `/LOG/` 5 días.

### Slot Registry (módulo)
- Editado en Paso 3 Config con UI nodo-conexión estilo Runpod.
- Consulta desde Scoring en **cada scan** (Opción A, sin cache).
- Mínimo 1 slot activo, los demás desactivables libremente.
- **Hot-reload por slot habilitado** (desvío del spec original): ticker nuevo → señal al Data Engine → warmup → operativo; otros 5 slots siguen funcionando.
- Validator corre sobre solo el slot afectado tras hot-reload.

### Scoring Engine (motor puro)
- Portado fielmente del spec, sin modificaciones de contrato.
- Invocado secuencial sobre slots operativos (~0.3-0.8 s para 6 slots).
- Slots DEGRADED o WARMUP: no se invocan.
- Healthcheck cada 2 min: mini parity test con canonical QQQ + dataset sintético + `sim_datetime` fijo → código `ENG-050` si difiere (warning, no detiene scan).
- `sim_datetime` y `sim_date` siempre None en live (solo Observatory los usa).

### Fixtures
- Canonicals embebidas en repo, parte del release, inmutables.
- **Múltiples canonicals por ticker coexisten** (ej. `qqq_canonical_v1` + `v2`).
- **Schema:** 5 bloques + archivo sibling `.metrics.json` separado (NO sexto bloque).
- Obligatorio sibling para canonicals `status: final`; opcional para activas.
- Fixtures activas viven dentro del Config del usuario.
- Upload desde frontend: `.json` + `.metrics.json` separados o zip.
- Peso Config ~16-20 KB con fixtures completas.
- Scanner **no edita, no aprueba, solo consume**.

### Outputs Scoring (tabla `signals`)
- Schema híbrido 3: columnas planas + blobs JSON + `candles_snapshot_gzip`.
- ~3 KB por señal → ~160 MB/año. Trivial en SQLite.
- Trazabilidad completa (Opción C): terna + timestamps dobles + snapshot completo.
- **Payload del evento `signal.new`:** columnas planas + layers + ind + patterns resumidos + **`chat_format` listo** (sin snapshot). El snapshot se consulta bajo demanda vía REST.
- Tabla `heartbeat` TTL 24h. Tabla `system_log` retención 30 días.

### Persistencia
- SQLite en primera instancia, arquitectura preparada para Postgres.
- DB operativa (`data/scanner.db`) + DB archive (`data/archive/scanner_archive.db`, sin límite).
- Rotación al shutdown + botón manual "Correr limpieza ahora" en Dashboard.
- Retenciones: signals 1 año, heartbeat 24h, system_log 30d, candles_daily 3 años, candles_1h 6m, candles_15m 3m.
- Database Engine separado (módulo intra-proceso) supervisa rotación y backups.
- Backup/Restore S3-compatible solo de DB operativa (via `VACUUM INTO` + comprimir + upload).
- Credenciales S3 en Config, encriptadas.

### Transversales
- **Zona horaria ET tz-aware** (v1.1.0): `zoneinfo.ZoneInfo("America/New_York")`, timestamps en DB con tzinfo, nunca naive. Producto mono-zona por diseño.
- **Auth API bearer token autogenerado** (v1.1.0) al primer arranque, encriptado en Config, rotable desde Dashboard. Un token activo por deployment (single-user).
- Comunicación intra-proceso (llamadas directas en memoria) — no HTTP entre motores.
- Frontend arranca primero; motores se activan desde Paso 4 Config.
- Heartbeat cada 2 min, solo consultado por Dashboard.
- 3 colores (verde/amarillo/rojo) + estado WARMUP.
- Piloto master del Cockpit (verde si todo OK, amarillo si algo amarillo/warmup, rojo si algo rojo).
- Sin notificaciones externas (pull, no push).
- Shutdown graceful con timeout 30s + botón "Forzar detención".
- Logs `/LOG/` TXT rotación 5 días.
- Sin telemetría.
- Umbral memoria 80% → amarillo, 95% → rojo.

### WebSocket — catálogo de 6 eventos (v1.1.0)

| Event | Payload | Uso |
|---|---|---|
| `signal.new` | columnas planas + layers + ind + patterns + `chat_format` | Nueva señal emitida |
| `slot.status` | `{slot_id, status, warmup_progress?, error_code?}` | Cambios de estado de slot |
| `engine.status` | `{engine, status, memory_pct?, error_code?}` | Cambios de estado de motor |
| `api_usage.tick` | `{key_id, used_minute, max_minute, used_daily, max_daily, last_call_ts}` | Actualización banner API |
| `validator.progress` | `{run_id, test_id, status, message?}` | Progreso batería de tests |
| `system.log` | `{level, source, message, error_code?}` | Feed de logs crítico |

---

## Frontend — 4 pestañas (todas cerradas)

### Configuración ✅
Layout vertical apilado, 4 pasos: Config (Cargar/Guardar/LAST + ONLINE BACKUP S3 plegable) · API Keys (hasta 5, con piloto individual + test conectividad) · Fixtures + Slot Registry (canvas nodo-conexión Runpod, 6 slots con dropdown fixture + upload) · Arranque de motores (lista ordenada + "Arrancar todos" + progress bar 7 tests Validator). Auto-LAST al arrancar saltea Paso 4.

### Dashboard ✅
Layout A vertical, secciones colapsables, header con Piloto Master. 4 secciones: Motores y servicios (grid de cards) · Slots (grid libre) · Base de datos (grid con barras + "Correr limpieza ahora") · Pruebas de validación (Revalidar sistema / Test API + último reporte Validator Opción C persistente). Heartbeat histórico UI eliminado.

### Memento ✅
Consulta. 2 secciones colapsables: Stats por Slot (6 subsecciones, leen desde sibling `.metrics.json`: WR por franja, spread B→S+, progresión monotónica, uplift por confirm, cobertura, MFE/MAE, thresholds) · Catálogo de Patrones (tarjetas en 3 subsecciones TRIGGERS/CONFIRMS/RISKS). Gráfico descriptivo por patrón NO en v1.

### Cockpit ✅ (cerrado v1.1.0)

**Estética:** icomat base (las 4 pestañas) + Runpod como patrones estructurales traducidos a paleta icomat (Paso 3 Config + Dashboard). No son dos estilos conviviendo — un solo estilo con vocabulario estructural prestado.

**Layout:**
- Watchlist izquierda: 6 cards verticales. Bordes reflejan banda. Animaciones sobrias (pulse lento en S+, glow controlado en S/A+).
- Panel derecho en 3 zonas:
  1. **Banner superior (sticky)** — ticker + banda + dirección + score numérico + **botón `COPIAR`**.
  2. **Resumen ejecutivo** (siempre visible, ~8-10 líneas) — precio, chg día, alineación, ATR 15M, dMA200, flags críticos, vela + timestamps.
  3. **Detalle técnico** (expandible) — espeja bloques del template B3: PRECIO · CONTEXTO · VOLUMEN · FUERZA RELATIVA · NIVELES · EVENTOS · PATRONES · SCORING · RESULTADO · Meta.
- Gráfico: Lightweight Charts local + botón "Abrir en TradingView".
- Banner superior global: 5 barras de API keys (créditos/min + timestamp última call) + créditos diarios consolidados (reset cierre ET).

**Botón `COPIAR`:** el backend pushea `chat_format` listo dentro del payload de `signal.new`. El frontend hace `navigator.clipboard.writeText()` al click — sin round-trip. Template rediseñado en bloques semánticos (referencia visual completa en `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` §7.5).

**Disclosure progresiva:** el detalle técnico está colapsado por default. El trader decide en 2 segundos con el resumen ejecutivo.

---

## Códigos de error nuevos (release v5.0.0)

- `ENG-050` warning — parity check fallido en healthcheck o Validator.
- `ENG-060` warning — ticker sin datos durante N ciclos consecutivos (default N=3 ≈ 45 min). Slot pasa a DEGRADED, auto-recupera al primer éxito. **(v1.1.0)**
- `MET-001` fatal/warning — sibling `.metrics.json` no encontrado.
- `MET-002` fatal — schema del sibling inválido.
- `MET-003` fatal — canonical final con confirms incompletos en sibling.
- `MET-004` fatal — inconsistencia status fixture vs completitud sibling.
- `MET-005` fatal — hash del sibling desincronizado.
- `MET-006` warning — thresholds fixture inconsistentes con sibling.

---

## Specs del Observatory a actualizar (pendiente manual)

1. `SCORING_ENGINE_SPEC.md` §2.2 — aclarar mínimos 40/25/25 vs warmup real 210/80/50.
2. `SLOT_REGISTRY_SPEC.md` §7 — habilitar hot-reload por slot.
3. `FIXTURE_ERRORS.md` §3 y §6 — agregar `ENG-050`, `ENG-060`, `MET-001..006`.
4. `SCANNER_V5_DEV_HANDOFF.md` §3.1 — trazabilidad completa Opción C con snapshot.
5. `FIXTURE_SPEC.md` — múltiples canonicals coexisten, sibling `.metrics.json`.
6. `CANONICAL_MANAGER_SPEC.md` §2.1 — remover UI 2, solo Observatory.
7. `METRICS_FILE_SPEC.md` — crear nuevo spec para el sibling.

---

## Preguntas abiertas (16 vivas — ver FEATURE_DECISIONS §9)

**Bloqueantes para Capa 2 Validator:** ninguno. Dataset parity resuelto (30 sesiones QQQ 2025 en JSON monolítico, ver `backend/fixtures/parity_reference/README.md`).

**No bloqueantes** (se resuelven en implementación de cada capa):
- Detección de gaps en DB local del Data Engine (resolver al programar Capa 1).
- Umbral exacto de `ENG-060` (tentativo 3 ciclos, confirmar al programar Capa 1).
- Ring buffer defaults por timeframe.
- Límites de memoria por motor.
- Umbral de retención agresiva.
- Versionado de backups S3 (tentativo timestamp).
- Naming exacto del sibling `.metrics.json`.
- Canal principal de distribución de canonicals nuevas.
- Color/animación del spinner de "cargando datos" en Cockpit cuando hay déficit de créditos.

**De roadmap:** Mac/Linux post-v5, firma digital del .exe, automatizar sync specs Observatory↔scanner.

---

## Próximos pasos

1. **Arrancar desarrollo de Capa 1 (Data Engine)** en chat nuevo. Inputs: este handoff + `FEATURE_DECISIONS.md` + `FRONTEND_FOR_DESIGNER.md` + `scanner_v4_2_1.html` (referencia del round-robin ya validado en producción) + specs del Observatory en `docs/specs/`.
2. **Entregar `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` v2.0.0** al diseñador.
3. **Actualizar specs del Observatory** según §8 de FEATURE_DECISIONS (manual, pendiente).
4. ~~Definir dataset parity exhaustivo~~ — resuelto (30 sesiones QQQ 2025 JSON, ver `backend/fixtures/parity_reference/README.md`).

---

## Documentos del proyecto

- **`SCANNER_V5_FEATURE_DECISIONS.md` v1.1.0** — fuente de verdad de decisiones (~1450 líneas).
- **`SCANNER_V5_HANDOFF_CURRENT.md`** — este documento.
- **`SCANNER_V5_FRONTEND_FOR_DESIGNER.md` v2.0.0** — briefing para diseñador (completo, Cockpit cerrado).
- `docs/specs/*.md` — copias sincronizadas manualmente desde Observatory.
- `scanner_v4_2_1.html` — referencia conceptual de v4.2.1 (detección de patterns, indicadores, round-robin).

---

**Fin del handoff. Al próximo chat: abrir con el saludo, leer `FEATURE_DECISIONS` si se va a trabajar en una capa específica, y pedir "ejecuta" antes de escribir código.**
