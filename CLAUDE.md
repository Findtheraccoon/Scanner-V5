# CLAUDE.md

Contexto persistente para asistentes de Claude Code trabajando en Scanner-V5.
Leer este documento **primero** al arrancar un chat nuevo. Contiene el estado
del código, convenciones, y gotchas aprendidas en sesiones anteriores.

---

## Saludo obligatorio

Al iniciar cualquier chat con Álvaro: **"¡Qué bolá asere! en qué pinchamos hoy?"**
(o variante equivalente). Sin excepciones.

---

## Usuario y workflow

- **Álvaro** — paper trader de opciones (TradingView), habla español.
- **Workflow:** discusión → "ejecuta" → ejecución. **No tomar decisiones
  unilaterales.** Cuando hay una decisión abierta: interrogante + opciones +
  ventajas/desventajas + recomendación, esperar "ejecuta".
- **Estilo:** español técnico, directo, sin relleno. Prefiere 1 manera clara
  sobre acumular configurabilidad.

---

## Qué es Scanner-V5

Scanner de opciones 0DTE/1DTE sobre mercado en vivo, 6 slots paralelos
(default: SPY/QQQ/IWM/AAPL/NVDA + 1 libre). **Greenfield Python** — reemplaza
al scanner v4.2.1 HTML monolítico (referencia conceptual únicamente).

**Relación con Signal Observatory:** proyecto hermano separado. El Observatory
**calibra canonicals** (fuente de verdad), Scanner-V5 **consume, no calibra**.

---

## Jerarquía documental (regla inviolable)

Cuando un spec viejo del Observatory y los 3 docs operativos se contradicen,
los 3 docs operativos **siempre ganan**.

En orden de prioridad:

1. `docs/specs/SCANNER_V5_FEATURE_DECISIONS.md` — fuente de verdad de decisiones (~1450 líneas)
2. `docs/specs/SCANNER_V5_FRONTEND_FOR_DESIGNER.md` — briefing visual
3. `docs/specs/SCANNER_V5_HANDOFF_CURRENT.md` — handoff de producto
4. Este `CLAUDE.md` — contexto de implementación (estado actual del código)

Cuando hay ambigüedad entre spec viejo y Observatory real (`docs/specs/Observatory/Current/scanner/`), **el código de Observatory gana** porque es el que generó el canonical + sample de paridad.

---

## Estado actual de la implementación

**Rama activa:** `claude/review-project-status-LhwGj` — scaffolding inicial del frontend Vite + React 18. La rama previa fue mergeada a main; este branch continúa con la app web sobre el backend ya completo.

### Completado

| Capa | Módulo | Estado |
|---|---|---|
| 1 (Data Engine) | `backend/engines/data/` — KeyPool, TwelveDataClient, `DataEngine` orquestrador (warmup DB-first, fetch_for_scan retry), `auto_scan_loop` real con DEGRADED ENG-060 | ✅ |
| 2 (Validator) | `backend/modules/validator/` — batería D/A/B/C/E/F/G + runner + REST + TXT log + hot-reload revalidation | ✅ |
| 3 (Slot Registry) | `backend/modules/slot_registry/` + `backend/engines/registry_runtime.py` — runtime in-memory con hot-reload REST (disable + enable con warmup + persistencia JSON) | ✅ |
| 4 (Scoring Engine) | `backend/engines/scoring/` — Fases 1-5 + parity **245/245 (100%)** + healthcheck continuo | ✅ |
| 5 (Persistencia + API + WS) | `backend/modules/db/` + `backend/api/` + `backend/modules/signal_pipeline/` — SQLAlchemy async, Alembic híbrido, REST auth Bearer, WS con 6 eventos, pipeline scan→persist→broadcast con flag `persist`, backup/restore S3, transparent reads op+archive | ✅ |
| 6 (Database Engine) | `backend/engines/database/` — heartbeat + rotación retention + move-to-archive + retención agresiva (§9.4) + watchdog auto opt-in | ✅ |
| 7 (Archive + S3) | `data/archive/scanner_archive.db` + `modules/db/backup.py` + validator_reports histórico | ✅ |
| Config | `backend/modules/config/` — Fernet encriptado standalone (crypto + loader + models). Wiring a endpoints pendiente | ✅ standalone |
| D (Entrypoint) | `backend/main.py` + `backend/settings.py` + `backend/api/workers.py` — Pydantic Settings, lifecycle, worker factories, Validator wiring, archive wiring, shutdown rotation, healthcheck wired al heartbeat | ✅ |
| Fixtures | `backend/modules/fixtures/` — loader | ✅ base |

**Tests totales:** 1068 passing + 1 slow (parity regression guard) en `backend/tests/`. `ruff check .` limpio.

**Frontend tests:** 6/6 passing (`pnpm test` en `frontend/`). Vite build limpio (~261KB JS gzip 82KB · 43KB CSS gzip 9KB). `pnpm lint` (Biome) limpio.

### Scoring Engine — detalle por fase

- **Fase 1:** errors, constants, structure gate, output neutral.
- **Fase 2:** indicadores — SMA, EMA, Bollinger Bands, ATR, volume_ratio, gap_pct. **Rounding a 2 decimales al output** para paridad con Observatory (ver gotcha §Rounding).
- **Fase 3:** alignment gate — `trend_strict` + `trend_slope` fallback + `trend_with_fallback` + `compute_alignment` + catalyst override.
- **Fase 4:** 16 triggers + 4 risks + trigger gate + conflict gate dentro de `analyze()`.
- **Fase 5.1:** 10 detectores de confirms (BB sup/inf 1H/D, VolHigh, VolSeq, SqExp, Gap, FzaRel, DivSPY) con descripciones bit-a-bit Observatory.
- **Fase 5.2:** port Observatory indicators — `today_candles` + `vol_ratio_intraday` (median), `vol_sequence` dict, `bb_width` squeeze dict, `gap` dict, `find_pivots` + `key_levels`. Resuelve divergencias #1, #2, #4 con Observatory.
- **Fase 5.3:** wiring completo en `analyze()`:
  - **5.3a** · `ind_builder.py:build_ind_bundle()` agrupa indicadores consumidos por confirms.
  - **5.3b** · `confirms/categorize.py` (dedup + pesos fixture) + `bands.py` (resolve_band) + `errors.py:build_signal_output()` + wire paso 8-11 en analyze. Score = trigger_sum + confirm_sum (H-02).
  - **5.3c** · Tests de integración con monkeypatch de detectores.
- **Fase 5.4:** parity harness — `backend/engines/scoring/aggregator.py` (1min→15M/1H) + `backend/fixtures/parity_reference/parity_qqq_regenerate.py` (runner E2E). **✅ 245/245 matches (100%)** post fixes #aggregator/reset_day y #ORB/vol_ratio_intraday (ver gotchas #16 y #17).

**Tests scoring:** 643 passing en `backend/tests/engines/scoring/` (sub-total del total global 964).

### Capa 5 + Entrypoint + Data Engine — detalle por sub-fase

**Capa 5 (persistencia + API + WS):**
- **C5.1** · `modules/db/models.py` — SQLAlchemy async, tablas `signals` (schema híbrido 3: columnas planas + JSON blobs + snapshot gzip), `heartbeats`, `system_logs`, `candles_{daily,1h,15m}`. Custom `ETDateTime` TypeDecorator para persistir tz-aware ET en SQLite.
- **C5.2** · `modules/db/helpers.py` — `write_signal`, `read_signals_{latest,history,by_id}` con cursor pagination, `write_heartbeat`, `write_system_log`, `write_candles_batch` (UPSERT sqlite), `read_candles_window`, `latest_candle_dt`. Tipo `CandleTF = Literal["daily","1h","15m"]`.
- **C5.3** · `api/app.py` factory `create_app()` + `api/auth.py` Bearer dependency + `api/routes/health.py` (`GET /api/v1/engine/health`).
- **C5.4** · `api/routes/signals.py` — `GET /api/v1/signals/{latest,history,by_id}` con cursor + snapshot base64.
- **C5.5** · `api/routes/websocket.py` + `api/broadcaster.py` — `/ws?token=` con handshake y policy violation 1008. 6 eventos en `api/events.py`: `signal.new`, `slot.status`, `engine.status`, `api_usage.tick`, `validator.progress`, `system.log`.
- **C5.6** · `modules/signal_pipeline/pipeline.py` — `scan_and_emit` analyze→persist→broadcast. Helpers `build_chat_format` v0 y `build_ws_payload`.
- **C5.7** · `engines/database/heartbeat.py` + `engines/database/rotation.py` con `DEFAULT_RETENTION_POLICIES`.

**D (Entrypoint):**
- **D.1** · `backend/main.py` + `api/workers.py:heartbeat_worker`.
- **D.2** · `api/routes/scan.py` — `POST /api/v1/scan/manual` con Pydantic `ScanManualRequest`.
- **D.3** · `backend/settings.py` — `Settings(BaseSettings)` env prefix `SCANNER_`. Worker stub `auto_scheduler_worker` reemplazado después por el loop real.

**Data Engine (Capa 1 expansión):**
- **DE.1** · `modules/db/helpers.py:write_candles_batch` + `read_candles_window` + tablas `candles_*`.
- **DE.2** · `engines/data/engine.py:DataEngine` orquestrador (`warmup`, `fetch_for_scan`, `pool_snapshot`).
- **DE.3** · `engines/data/scan_loop.py:auto_scan_loop` real integrado con `main._build_scan_loop_factory` via `extra_workers` de `create_app`.
- **C.1** · `auto_scan_loop` emite `api_usage.tick` por key al cierre de cada ciclo con snapshot de credits.
- **C.2** · Retry nivel 1 (1s) en `fetch_for_scan` + `SlotFailureTracker` escala a DEGRADED ENG-060 tras 3 fallos consecutivos (ADR-0004). Emisión de `slot.status` en transiciones degraded↔recovered.
- **DE.3.1** · Warmup DB-first (ADR-0003). `DataEngine.warmup()` consulta DB local por (ticker, TF); si la DB tiene al menos N velas frescas, skip fetch. Thresholds: `daily=7d`, `1h=3d`, `15m=1d`. Fase 1 check todos los pares, Fase 2 gather solo de los fetches pendientes.

**Slot Registry runtime:**
- **SR.1** · `engines/registry_runtime.py:RegistryRuntime` — wrapper sobre `SlotRegistry` con `asyncio.Lock`, warmup overlay (`mark_warming`/`mark_warmed`/`is_warming`/`warming_slots`), `effective_status`, `replace_registry` para hot-reload. Tipo `SlotRuntimeStatus = Literal["active","warming_up","degraded","disabled"]`.
- **SR.2** · `auto_scan_loop(registry: RegistryRuntime, ...)` consulta `list_scannable_tickers()` cada ciclo 15M. Cambios en el registry toman efecto sin reiniciar.
- **SR.3** · `api/routes/slots.py` — `GET /api/v1/slots`, `GET /api/v1/slots/{id}`, `PATCH /api/v1/slots/{id}` con body `{enabled: false}` → `disable_slot` + broadcast `slot.status=disabled`.
- **SR.4** · PATCH `{enabled: true, ticker, fixture, benchmark?}` → `RegistryRuntime.enable_slot()` (valida fixture + REG-011/012/013), persist JSON, marca warming_up, broadcast. Background task hace `DataEngine.warmup([ticker])` → `mark_warmed` + broadcast `slot.status=active`. Requiere `app.state.data_engine` (503 si no).
- **SR.5** · PATCH (disable o enable) dispara `Validator.run_slot_revalidation()` en background (A→B→C con mismo run_id). Spec §3.3 — "validator corre solo sobre el slot afectado tras hot-reload".

### Capa 2 (Validator) — detalle por sub-fase

- **V.1** · `modules/validator/models.py` (`TestResult` frozen, `ValidatorReport` con `overall_status` derivado, `TEST_ORDER`/`TEST_DESCRIPTIONS`) + `runner.py:Validator.run_full_battery()` + `checks/d_infra.py` (DB `SELECT 1` + FS probe via `asyncio.to_thread`). Emite `validator.progress` 2 eventos por test.
- **V.2** · `checks/a_fixtures.py` (`load_fixture` por slot enabled, fail degraded con FIX-XXX), `checks/b_canonicals.py` (SHA-256 recompute, fail fatal REG-020), `checks/c_registry.py` (reload `load_registry` + reporta degraded/operative/disabled counts).
- **V.3** · `checks/e_e2e.py` con `scan_executor` callable inyectable + `scan_and_emit(persist: bool = True)`. Persist=False → skip write_signal + broadcast, retorna `{..., "id": None, "persisted": False}`. Fatal si executor crashea o shape inválida.
- **V.4** · `checks/f_parity.py` — corre `analyze()` sobre `parity_qqq_candles.db` (commiteado). Slicing/compare portados del runner CLI. Match rate < `min_match_rate` (default 0.70) → warning ENG-050.
- **V.5** · `checks/g_connectivity.py` — `td_probe` + `s3_probe` inyectables. Fatal si TODAS las TD keys fallan; warning si alguna falla o S3 cae.
- **V.6** · `api/routes/validator.py` — `POST /api/v1/validator/run` (bloqueante), `POST /api/v1/validator/connectivity` (solo G), `GET /api/v1/validator/report/latest`. Guarda el último reporte en `app.state.last_validator_report`.
- **V.7** · `main.py` `_build_validator` + `_build_td_probe` + `_build_validator_startup_factory`. Si `validator_run_at_startup=True` corre batería al arrancar. Continue-on-fatal.
- **V.8** (post-merge) · `modules/validator/log_writer.py` — TXT a `/LOG/` con retención 5 días. Se invoca desde el endpoint `POST /run` y desde el startup factory.
- **V.9** (post-merge) · `Validator.run_slot_revalidation()` — corre A→B→C con un solo run_id, spawneado desde `api/routes/slots.py` tras cualquier PATCH exitoso.

### Capa 7 (Archive + S3 + histórico) — detalle por sub-fase

- **AR.1** · Archive DB físico + rotación real.
  - `data/archive/scanner_archive.db` como engine separado (`create_app(archive_db_url=...)`).
  - `engines/database/rotation.py:rotate_with_archive(op, archive, policies)` — SELECT expired → INSERT OR IGNORE al archive (commit) → DELETE de op (commit). No-pérdida idempotente.
  - `heartbeat` se borra sin archivar (spec §3.7).
  - Settings: `SCANNER_ARCHIVE_DB_PATH`, `SCANNER_ROTATE_ON_SHUTDOWN` (lifespan hook opcional).
  - `POST /api/v1/database/rotate` — botón "Correr limpieza ahora" (§5.3).
  - `GET /api/v1/database/stats` — filas op + archive + retention_seconds por tabla.
  - `rotate_expired` legacy mantenido para compat sin archive.
- **AR.2** · Backup + Restore S3-compatible.
  - `modules/db/backup.py` — `S3Config` Pydantic, `backup_to_s3()` (VACUUM INTO + gzip + upload_fileobj), `restore_from_s3()` (download → gunzip → sibling file, NO pisa op viva), `list_backups()` (sort desc por key).
  - Multi-provider via `endpoint_url` (AWS S3 / B2 / R2 / custom).
  - Endpoints `POST /database/{backup,restore,backups}` — todos POST por credenciales en body.
  - Dep dev `moto[s3]>=5.1.0` para tests.
  - **Deuda:** credenciales S3 en body hasta que `modules/config/` encriptado exista.
- **AR.3** · Transparent reads op + archive (Opción X).
  - `read_signals_history`, `read_signal_by_id`, `read_candles_window`, `read_validator_reports_*` aceptan `archive_session` opcional.
  - Merge + sort + dedup (op-wins).
  - `api/deps.py:get_archive_session()` yield-ea `None` si el app arrancó sin archive.
  - Endpoints `/signals/{history,/{id}}` + `/validator/reports/*` son transparentes.
- **AR.4** · Reportes históricos del Validator en DB.
  - Tabla `validator_reports` (id, run_id, trigger, started_at, finished_at, overall_status, tests_json).
  - Retención 30d op → archive.
  - `ValidatorTrigger = Literal["startup","manual","hot_reload","connectivity"]`.
  - Endpoints `/validator/reports/latest`, `/validator/reports` (cursor, filtros), `/validator/reports/{id}`.
  - Wiring automático: `POST /run` → `"manual"`, startup factory → `"startup"`, `_spawn_revalidation` → `"hot_reload"`. Silencioso ante fallos DB.
  - `ValidatorReportRecord` SQL (nombre distinto al Pydantic `ValidatorReport`).
- **AR.5** · Retención agresiva (§9.4).
  - `AGGRESSIVE_RETENTION_POLICIES` ~50% de las normales.
  - `DEFAULT_SIZE_LIMIT_MB = 5000` (tentativo revisable, spec §9.4).
  - `check_and_rotate_aggressive(op, archive, db_path, *, size_limit_mb)` — mide tamaño del archivo, solo dispara si supera. Retorna `{triggered, size_mb_before, size_mb_after, rotation, vacuum_recommended}`.
  - `POST /api/v1/database/rotate/aggressive` — 503 sin archive, 400 con `:memory:`.
  - `GET /stats` extendido con `size_mb_operative` + `size_limit_mb` para barra del Dashboard.
  - Settings: `SCANNER_DB_SIZE_LIMIT_MB=5000`.
  - `vacuum_recommended=True` al trigger — SQLite DELETE no reclama hasta VACUUM.

### Módulos nuevos del Scoring Engine (Fase 5)

| Archivo | Rol |
|---|---|
| `engines/scoring/aggregator.py` | Agrega velas 1-minuto a 15M/1H open-stamped, con flag `include_partial` |
| `engines/scoring/bands.py` | `resolve_band(score, fixture) → (conf, signal)` vía `fixture.score_bands` |
| `engines/scoring/ind_builder.py` | `build_ind_bundle(daily, 1h, 15m, spy, bench, sim_date) → IndBundle` |
| `engines/scoring/indicators/gap.py` | Observatory `gap()` dict `{pct, significant, dir}` |
| `engines/scoring/indicators/pivots.py` | `find_pivots()` + `key_levels()` |
| `engines/scoring/confirms/categorize.py` | `categorize_confirm()` + `apply_confirm_weights()` (dedup por categoría) |
| `engines/scoring/confirms/bollinger.py`, `volume.py`, `squeeze.py`, `gap.py`, `relative_strength.py` | Detectores de confirms por familia |
| `fixtures/parity_reference/parity_qqq_regenerate.py` | Runner parity E2E (Opción B) contra `parity_qqq_candles.db` |
| `fixtures/parity_reference/fixtures/parity_qqq_candles.db` | Dataset de velas QQQ/SPY commiteado (10.6MB, usado por Check F y runner) |

### Módulos nuevos del Validator (Capa 2)

| Archivo | Rol |
|---|---|
| `modules/validator/models.py` | `TestResult`, `ValidatorReport`, `TEST_ORDER` |
| `modules/validator/runner.py` | `Validator` — `run_full_battery`, `run_single_check`, `run_slot_revalidation` |
| `modules/validator/checks/d_infra.py` | DB `SELECT 1` + FS probe |
| `modules/validator/checks/a_fixtures.py` | `load_fixture` sobre slots enabled |
| `modules/validator/checks/b_canonicals.py` | Hash SHA-256 de canonicals (REG-020) |
| `modules/validator/checks/c_registry.py` | Reload `load_registry` + report |
| `modules/validator/checks/e_e2e.py` | Shape check sobre `scan_executor` inyectable |
| `modules/validator/checks/f_parity.py` | Parity exhaustivo vs `parity_qqq_sample.json` |
| `modules/validator/checks/g_connectivity.py` | `td_probe` + `s3_probe` inyectables |
| `modules/validator/log_writer.py` | TXT a `/LOG/` con retención 5 días |
| `api/routes/validator.py` | `/api/v1/validator/{run,connectivity,report/latest}` |

### Módulos nuevos del Slot Registry runtime

| Archivo | Rol |
|---|---|
| `engines/registry_runtime.py:RegistryRuntime` | `disable_slot`, `enable_slot` (con warmup overlay + persist), `mark_warming/warmed`, `replace_registry` |
| `modules/slot_registry/writer.py` | `save_registry()` con escritura atómica (`tempfile` + `os.replace`) |
| `api/routes/slots.py` | REST + spawn warmup task + spawn revalidation task |

### Módulos nuevos de Capa 7 (Archive + S3 + Histórico Validator)

| Archivo | Rol |
|---|---|
| `engines/database/rotation.py` | `rotate_expired` (legacy), `rotate_with_archive` (move), `check_and_rotate_aggressive` (§9.4), `compute_stats`. Políticas `DEFAULT_RETENTION_POLICIES` + `AGGRESSIVE_RETENTION_POLICIES` |
| `engines/database/watchdog.py` | `aggressive_rotation_watchdog` loop async opt-in (`SCANNER_AGGRESSIVE_ROTATION_ENABLED=false` por default) — chequea tamaño DB cada `interval_s` y dispara rotación agresiva |
| `modules/db/backup.py` | `S3Config` Pydantic, `backup_to_s3`, `restore_from_s3`, `list_backups` — multi-provider via `endpoint_url` |
| `api/routes/database.py` | REST `/rotate`, `/rotate/aggressive`, `/stats`, `/backup`, `/restore`, `/backups` |
| `api/deps.py:get_archive_session` | Yield `AsyncSession | None` según `app.state.archive_session_factory` |
| `modules/db/models.py:ValidatorReportRecord` | Tabla `validator_reports` (id, run_id, trigger, started_at, finished_at, overall_status, tests_json) |
| `modules/db/helpers.py` — `write_validator_report`, `read_validator_reports_{latest,history}`, `read_validator_report_by_id` | Persistencia + transparent reads |
| `api/routes/validator.py` — `/reports*` | Endpoints histórico |

### Módulos nuevos del Scoring healthcheck (spec §3.4)

| Archivo | Rol |
|---|---|
| `engines/scoring/healthcheck.py` | Mini parity test determinístico con dataset sintético + fixture canonical + `sim_datetime` fijo. Chequea invariantes operativos (no-crash, shape, signal vocab, score numérico, error=False). ~10ms por corrida |
| `api/workers.py:heartbeat_worker` | Extendido con `healthcheck_fn` opcional (corre via `asyncio.to_thread` antes de emitir el heartbeat). Sin el param, el worker reporta siempre green |
| `tests/engines/scoring/test_parity_regression.py` | Regression guard `@pytest.mark.slow @pytest.mark.parity` — falla si parity < 100%. ~2min. Se excluye del `pytest -q` default |

### Módulos nuevos del Config encriptado (standalone, pendiente wiring)

| Archivo | Rol |
|---|---|
| `modules/config/crypto.py` | `get_master_key()` env→file→auto-gen + `encrypt_str`/`decrypt_str` con Fernet. `MasterKeyError` custom |
| `modules/config/models.py` | `UserConfig` Pydantic frozen + `TDKeyConfig` + `S3Config` (copias encriptadas del body). Secretos en plain fields en runtime |
| `modules/config/loader.py` | `save_config` encripta los 3 secretos (`twelvedata_keys`, `s3_config`, `api_bearer_token`) como `<name>_enc` + atomic write. `load_config` desencripta y reconstruye el modelo |
| `modules/config/__init__.py` | API pública del módulo |

### Frontend (scaffold inicial · 2026-04-27)

| Capa | Detalle | Estado |
|---|---|---|
| Toolchain | Vite 5 + React 18 + TS strict + pnpm + Biome + Vitest + jsdom + RTL | ✅ |
| Estilos | tokens Phoenix completos (`src/styles/tokens.css`), reset+atmosphere global, `shell.css` topbar/apibar/footer, `cockpit.css` watchlist+panel — ports verbatim del Hi-Fi v2 | ✅ |
| Tailwind | Plugin custom Phoenix con utilities `glass-*`, `tier-*`, `bookmark-shape`, `iridescent-*`, `num-tabular`. Theme extendido con paleta + radii + tipografías | ✅ |
| Router | React Router 6 con 4 pestañas + `AppShell` compartido (health-line + topbar + apibar + Outlet + footer). `/` → `/cockpit` | ✅ |
| Cockpit | Watchlist (6 slots, 5 cargados + 1 vacío) + Panel derecho (banner sticky · resumen ejecutivo · chart estático · detalle técnico colapsable). Selectores CSS 1:1 con Hi-Fi v2 | ✅ shell estático |
| Stubs | Configuración / Dashboard / Memento — placeholder unificado en `pages/_stub/StubPage.tsx` | ✅ |
| API client | `src/api/client.ts` con bearer opcional + `ApiError`. Vite proxy `/api`+`/ws` → `VITE_BACKEND_URL` (default localhost:8000) | ✅ base |
| Tests smoke | `src/test/router.test.tsx` — render + landmarks + 4 pestañas + active state + apibar + cockpit + 2 stubs (6/6) | ✅ |

### Pendiente

- **Frontend (próximas iteraciones, scaffold ya operativo):**
  - **Stores Zustand** (`auth`, `slots`, `apiUsage`, `signals`) — migrar la fuente de datos del Cockpit desde `pages/Cockpit/data.ts` hacia stores.
  - **TanStack Query hooks** (`useEngineHealth`, `useSlots`, `useLatestSignals`, `useApiUsage`) consumiendo los endpoints `/api/v1/*`.
  - **WebSocket listener** `useScannerWS()` que mappea los 6 eventos a actions de stores. Auto-reconnect + token bearer.
  - **Lightweight Charts** en el panel del Cockpit (reemplaza el SVG estático del prototipo).
  - **Estados restantes del Cockpit** (warmup, degraded, fatal, scan en curso, S+ nueva, AUTO off) — diseñar variantes y conectarlas al estado global.
  - **Hi-Fi del Dashboard / Configuración / Memento** y reemplazo de los stubs.
  - **Cockpit Hi-Fi v1** ya mergeado a main (PR #31, ref histórica). El scaffold actual usa **Hi-Fi v2 "Phoenix"** como fuente.
- ~~**Fase 5.4 cierre**~~ → **Cerrado 2026-04-23 al 100%.** Post subida del `qqq_1min.json` original del Observatory, se identificaron 2 bugs reales del motor (ver gotchas #16 y #17): aggregator no resetaba al cambio de día + ORB gate usaba mean-cross-day en vez de median-intraday. Ambos arreglados → **245/245 match**. `DEFAULT_MIN_MATCH_RATE` subido a 0.99. Regression guard en `test_parity_regression.py` (slow, ~2min).
- ~~**Healthcheck continuo spec §3.4**~~ → **Cerrado 2026-04-23.** `engines/scoring/healthcheck.py` wired al `heartbeat_worker` con `healthcheck_fn` opcional. Cada 2 min valida operativamente el motor (no-crash, shape, signal vocab) y reporta green/yellow+ENG-050/red+ENG-001 al Dashboard.
- ~~**Watchdog automático AR.5**~~ → **Cerrado 2026-04-23.** `engines/database/watchdog.py:aggressive_rotation_watchdog` opt-in via `SCANNER_AGGRESSIVE_ROTATION_ENABLED=true`. Chequea tamaño DB cada `SCANNER_AGGRESSIVE_ROTATION_INTERVAL_S` (default 3600s) y dispara rotación agresiva. Default off por ser destructivo.
- ~~**`modules/config/` encriptado**~~ → **Cerrado 2026-04-23 en modo standalone.** Fernet-based con master key desde env `SCANNER_MASTER_KEY` o file `data/master.key` (auto-gen). `UserConfig` Pydantic con 3 campos secretos encriptados inline al persistir. **Wiring a endpoints pendiente** — los endpoints `POST /database/backup` siguen aceptando credenciales en body por compat. Integración cuando el frontend consuma el Config (decisión UX: cómo editar + cuándo recargar).
- **Distribución Windows:** `.exe` via Inno Setup. Depende de frontend + decisión sobre bundling del `master.key`.
- ~~**Auto-scan pause/resume**~~ → **Cerrado.** `POST /api/v1/scan/auto/{pause,resume,status}` con `asyncio.Event` en `app.state.auto_scan_running`. El loop bloquea en `await running.wait()` antes del próximo ciclo y emite `engine.status={status: "paused"}` por WS. 6 tests nuevos en `tests/api/test_scan.py::TestAutoScanPauseResume`. Frontend cableado vía `useAutoScanPause/Resume/Status`.

#### Deudas técnicas a eliminar antes de la release 1

- **`frontend/src/components/Dev/DevStateSwitcher.tsx` + `dev-state-switcher.css`**: switcher flotante (sólo `import.meta.env.DEV`) que fuerza estados del Cockpit (warmup/degraded/splus/error/scanning/loading) escribiendo en `useEngineStore.stateOverride`. Útil para previsualizar variantes sin levantar backend ni reproducir condiciones reales. Pre-release: borrar la carpeta `Dev/`, quitar `stateOverride` + `setStateOverride` de `engine.ts`, y la rama del override en `useCockpitState`.

### Para el siguiente chat

**Estado al 2026-04-27 (segunda sesión del día):** backend **completo a spec §3 + §4 + §9.4** (sin cambios desde 2026-04-23) · 1068 tests + 1 slow passing · parity 245/245 · ruff limpio. **Frontend scaffold operativo** sobre Vite + React 18 + TS strict + Tailwind + Biome + Vitest. Cockpit Hi-Fi v2 portado a componentes React (datos hardcoded), 4 pestañas con router, 6/6 tests smoke verdes, build limpio.

Última sesión (2026-04-26 / 2026-04-27) — **Cockpit Hi-Fi v2 "Phoenix"**:

- Creado `frontend/wireframing/Cockpit Hi-Fi v2.html` (~90KB, ~2700 líneas) usando el plugin `frontend-design` (ahora sí disponible) + iteraciones cromáticas con la referencia `frontend/wireframing/Cockpit Hi-Fi Phoenix reference.html` que aportó Álvaro desde un editor visual externo.
- **Paleta master:** acento naranja `#FF6A2C` Phoenix (variantes `#E55A1F / #7A2E0E / #3D1808`) sobre base neutra `#0d0d0d`. Bull/bear semánticos verde/rojo se mantienen.
- **Tiers de score con paleta dedicada:** `--tier-r/b/a/ap/s/sp-{color,border,glow}` (R `#737880`, B `#82AAC0`, A `#3B9AE8`, A+ `#B941D5`, S `#DC9418`, S+ base `#06080E` + texto `#9AAABF`).
- **Glass cromado real** (no físicas pesadas): `backdrop-filter: blur(40-44px) saturate(180-220%) brightness/contrast` en topbar, apibar, cards de watchlist, banner principal, exec, chart canvas, footer. Edge glass top/bottom + bordes refractivos laterales (cálido izq + frío der). Watchlist y panel transparentes para que los glows ambient atraviesen.
- **Iridiscentes Houdini animados:** `@property --iri-angle` para `conic-gradient` rotando. Aplicado solo a tiers premium: **S** (familia dorada full-color rotación 8s) y **S+** (reflejos translúcidos sobre `#06080E` premium, rotación 11s). Botón COPIAR con `iri-pan` 9s. R/B/A/A+ con relleno plano del color del tier.
- **Bookmarks como lengüeta de marca-páginas:** `clip-path: polygon(...)` con bordes superiores planos, costados rectos, punta triangular abajo (V con micro-suavizado en los hombros). Tamaño 26×30px. Solo se muestran en setups A, A+, S, S+ (R y B sin bookmark — su tier se infiere del score numérico). El sweep metálico blanco animado del S+ sigue activo encima del iridiscente.
- **Banner principal del ticker** con 3 órdenes jerárquicos: ticker grande, banda+score+CALL+SETUP, subíndices uppercase. **Banda del banner sin relleno**, solo la letra del tier con `text-shadow` glow doble. Ticker ghost gigante translúcido detrás (240px, gradient text-clip iridiscente). Más oscuro `rgba(8,8,8,0.92→0.85)`.
- **Ambient atmosphere:** glows del body en paleta cálida libre (naranja, rosa magenta, ámbar — sin azul ni mint). Dithering multi-capa: puntos 22×22px + turbulence SVG fina animada (`grain-breathe` 14s) para romper banding sin centellar.
- **Layout final:**
  - Topbar 100px sin logo (solo `SCANNER` uppercase letterspaced + `v5.0.0-dev` mono pequeño) + pestañas centradas con tab-shape + sombra superior + indicador "live" verde.
  - API bar 114px, primera celda con **scan ahora + auto toggle** apilados centrados (migrados desde el footer); 5 cells de KEY 1..5 con `KEY 1 · hace 3s` en una línea + uso `4/8` + barra; última celda "diaria" con 5 filas apiladas `[name · barra · usados/800]`.
  - Watchlist con cards de glass esmerilado, sparkline ambient con gradient stroke, contenido `slot · ticker · CALL · score · WR%`.
  - Panel: banner sticky → resumido (precio + 6 chips: alineación, ATR, vela, R, S, vol) → gráfico SVG con MA20/40/200 + 30 velas → detalle técnico colapsado por default.
  - Footer con `proveedor · twelvedata · 5 keys` + status `motor scoring · data engine · database`.
- **Estados:** solo "operativo normal" implementado. Los 7 estados restantes (warmup, degraded, fatal, loading, scan en curso, S+ nueva, AUTO off) quedan para cuando se scaffoldee React.

**Branch de trabajo:** `claude/review-project-status-LhwGj`.

**PR del scaffold:** se crea al pushear (esta sesión).

**Decisiones cerradas en esta sesión:**
1. Stack: Vite 5 + React 18 + TS strict + Tailwind 3 + Zustand 5 + TanStack Query 5 + React Router 6 + pnpm + Biome + Vitest + jsdom + RTL. **shadcn/ui se difiere** hasta que entremos a Configuración (forms).
2. Efectos del Hi-Fi v2 → CSS verbatim en `tokens.css`/`global.css`/`shell.css`/`pages/Cockpit/cockpit.css` + Tailwind plugin custom para utilities reutilizables (glass/tier/bookmark/iridescent). Los selectores BEM del prototipo se preservaron 1:1, lo que permite portar futuros hi-fi del diseñador casi sin diff visual.
3. **Backend desde día 1**: Vite proxy `/api`+`/ws` → `localhost:8000`. No MSW ni fixtures locales — el backend levanta con un comando.
4. **Lint/format**: Biome (single tool). CSS files ignorados del Biome (son ports verbatim del prototipo del diseñador y el soporte CSS de Biome es preview).
5. **Tests** desde el día 1: smoke con Vitest + RTL + jsdom. 6/6 verdes.

**Decisiones abiertas para el próximo chat:**
1. **Próximo bloque:** ¿wiring real al backend (stores Zustand + TanStack hooks + `useScannerWS`) o siguiente pestaña hi-fi (Dashboard recomendado)?
2. **Lightweight Charts** o algún otro lib para el chart real (Hi-Fi v2 actualmente usa SVG estático).
3. **Deuda técnica del backend ya identificada:** `POST /api/v1/scan/auto/{pause,resume}` para cablear el toggle AUTO. Sigue pendiente.
4. **Compatibilidad:** las animaciones iridiscentes usan `@property` Houdini (Chrome 85+, Edge 85+, Safari 16.4+, Firefox 128+). Como el target es desktop Windows con browsers modernos, OK. Si hace falta fallback estático, está pensado.

Superficie backend disponible para el frontend:

| Método | Path | Notas |
|---|---|---|
| GET | `/api/v1/engine/health` | Piloto del scoring engine con healthcheck status |
| GET | `/api/v1/signals/{latest,history,{id}}` | Histórico transparent op+archive |
| POST | `/api/v1/scan/manual` | Scan on-demand |
| GET/PATCH | `/api/v1/slots`, `/api/v1/slots/{id}` | List + enable/disable + hot-reload warmup |
| POST | `/api/v1/validator/{run,connectivity}` | Batería completa + solo conectividad |
| GET | `/api/v1/validator/reports{,/latest,/{id}}` | Histórico de reportes |
| POST | `/api/v1/database/rotate{,/aggressive}` | Rotación manual + agresiva §9.4 |
| GET | `/api/v1/database/stats` | Contadores + tamaño op + umbrales |
| POST | `/api/v1/database/{backup,restore,backups}` | S3-compat, multi-provider |
| WS | `/ws?token=...` | 6 eventos push |

**Stack frontend recomendado** (spec): React 18 + TypeScript + Vite + Tailwind + shadcn/ui + Zustand + TanStack Query + React Flow (Paso 3 nodo-conexión) + Lightweight Charts (Cockpit) + Vitest + `pnpm`.

**Pestañas (ver `docs/operational/FRONTEND_FOR_DESIGNER.md` v2.0.0):**
1. **Configuración** — 4 pasos apilados (Config + ONLINE BACKUP S3 / API Keys / Fixtures + Slot Registry canvas Runpod / Arranque motores con progress bar del Validator).
2. **Dashboard** — Piloto Master + 4 secciones (Motores/Slots/Base de datos/Pruebas validación).
3. **Memento** — Consulta de stats por slot + catálogo de patrones.
4. **Cockpit** — Watchlist + detalle técnico + botón COPIAR con `chat_format` del payload WS.

**Decisiones abiertas que pedir a Álvaro antes de empezar frontend:**
- ¿Vite + pnpm como recomienda el spec, o preferís otro stack?
- ¿Empezamos por Configuración (más complejo — canvas Runpod, upload fixtures) o por Dashboard (más simple, refleja estado backend)?
- ¿Auto-LAST al arrancar (spec §5.2): backend ya tiene el `startup factory`, falta el flag en el Config del usuario.

**Comando de arranque end-to-end verificado:**
```bash
SCANNER_API_KEYS="sk-dev" \
SCANNER_TWELVEDATA_KEYS="k1:sk-td-1:8:800" \
SCANNER_REGISTRY_PATH="slot_registry.json" \
python backend/main.py
```

Al arrancar: Validator corre batería completa → emite progress via WS → persiste reporte en DB + TXT en `LOG/`. Database Engine inicializa op + archive. Heartbeat del scoring engine corre healthcheck cada `heartbeat_interval_s` (default 120s) y emite `engine.status` con green/yellow/red. Si `SCANNER_AGGRESSIVE_ROTATION_ENABLED=true`, watchdog chequea tamaño DB cada `aggressive_rotation_interval_s` (default 1h).

**Archivos de datos en el repo:**
- `backend/fixtures/parity_reference/fixtures/parity_qqq_candles.db` (10.6MB commiteado).
- `backend/fixtures/parity_reference/fixtures/parity_qqq_sample.json` (390KB).
- `backend/fixtures/qqq_canonical_v1.json` + `.sha256` + `.metrics.json`.
- `docs/specs/Observatory/Current/qqq_1min.json` (30MB) + `qqq_daily.json` + `spy_daily.json` — dataset Observatory de verificación.

### Divergencias conocidas con Observatory — estado post-Fase 5.2/5.4

1. ~~`vol_sequence` port~~ → **Resuelto Fase 5.2b.**
2. ~~`volume_ratio` mediana intraday~~ → **Resuelto Fase 5.2a** (nuevo `vol_ratio_intraday`; el `volume_ratio_at` legacy sigue disponible pero no se usa en el pipeline principal).
3. **ATR Wilder vs Observatory mean:** pendiente. No afecta confirms críticos (Gap usa `atr_pct` que da similar magnitude). Documentada en `indicators/atr.py`.
4. ~~Pivot fakeouts~~ → **Resuelto Fase 5.2e** (`find_pivots` + `key_levels`).
5. **Convención 1H aggregation:** ~~ambigua~~ → **Resuelta con el replay Observatory** portado en `docs/specs/Observatory/Current/Replay/candle_builder.py` L117-127: 1H open-stamped con `include_current=True`. Mi aggregator coincide.
6. ~~**Data source mismatch**~~ → **Resuelto 2026-04-23 con parity 100%.** La hipótesis inicial ("velas portables ≠ velas Observatory") se refutó al pullear el `qqq_1min.json` del Observatory (30MB): las 1min matchean bit-a-bit (0 diffs en 96562 velas compartidas). Los mismatches eran 2 bugs reales del motor scanner que el dataset portable había estado enmascarando:
   - **Bug aggregator:** no aplicaba `reset_day()` al cambiar de fecha. Ver gotcha #16. Fix: bucket key `(date, hour)` + descartar bucket en construcción al cambio de día. Parity 77% → 98.37%.
   - **Bug ORB vol_ratio:** gate usaba `volume_ratio_at` mean-cross-day en lugar de `vol_ratio_intraday` median-same-day. Ver gotcha #17. Fix: wire `vol_ratio_intraday` (ya porteado en Fase 5.2a pero nunca conectado al ORB). Parity 98.37% → **100%**.

---

## Gotchas críticas (errores cometidos y corregidos)

**NO repetir estos errores.** Cada uno requirió un commit de corrección.

### 1. H-02 "volumen fuera del score"

El hallazgo H-02 se refiere a **eliminar `volMult` (parámetro de peso que multiplicaba el score)**, NO a eliminar gates binarios de volumen. El gate `volume_ratio >= 1.0` del ORB **debe estar presente** — es paridad con Observatory `engine.py`. Verificado: `orb.py:112`.

**Lección:** "parámetro de peso" ≠ "gate binario (fire/no fire)". El primero se eliminó, el segundo se mantiene.

### 2. Alignment semantics (Option B)

Observatory usa: `trend_strict(price, ma20, ma40)` + `trend_slope(candles, ma20)` con shift de 5 velas + `trend_with_fallback`.

- Valores: `"bullish" | "bearish" | "neutral"` (para tendencia por TF), `"bullish" | "bearish" | "mixed"` (para alignment). **NUNCA `"up"/"down"/"flat"`** — esa fue mi primera versión incorrecta.
- **Catalyst override:** si `has_catalyst AND t_15m == t_1h AND t_15m != "neutral"`, el gate pasa aunque daily sea neutral.
- Minimum 25 velas para slope fallback, shift de 5.

### 3. Loop range en detección de triggers candle

Observatory: `for i in range(min(max_age+1, n-1))` — **NO `n`**. La diferencia: `n-1` garantiza que siempre haya una `pv = candles[idx-1]` disponible para Envolvente.

**Lección:** los triggers de 1 vela (Doji, Hammer, Star) funcionan con `n`, pero cuando se añade Envolvente al mismo loop hay que usar `n-1`.

### 4. Triggers extras 15M Engulfing

Spec §5.1 lista 14 triggers canónicos. Observatory `patterns.py` emite además **Envolvente alcista/bajista 15M con decay** (no en la tabla del spec). Están en el sample que generó el canonical, entonces el engine **debe** emitirlos. Total: 14 + 2 = **16 triggers detectores**.

### 5. ORB time gate — string compare

Observatory usa:
```python
_hhmm = sim_datetime[11:16]  # "HH:MM" de "YYYY-MM-DD HH:MM:SS"
_orb_in_first_hour = _hhmm <= "10:30"
```

**Los segundos se ignoran** — `"10:30:59"` es válido (mi primera versión lo rechazaba por comparación numérica). Implementado en `orb.py:_is_orb_time_valid`.

### 6. Rounding a 2 decimales

Observatory redondea al output de cada indicador. Mi paridad requiere:
- SMA/EMA/BB (middle, upper, lower)/ATR/volume_ratio/gap_pct → `round(..., 2)` al retornar.
- **Recurrencias (EMA, Wilder ATR):** mantener `prev` **sin redondear** internamente, solo redondear en la salida. Si redondeas `prev`, el error se compone.

### 7. RISK detectors no suman al score

Por H-04, los 4 detectores de RISK (vol_bajo_rebote, vol_declinante, BB sup/inf fakeout) emiten patterns con `cat="RISK"` y `sg="WARN"`, peso negativo **informativo** únicamente. **No contribuyen al score final**. Solo aparecen en `patterns[]` y `layers.risk`.

### 8. Parity replay mode — daily incluye la sesión del día

El sample canonical QQQ fue generado por Observatory en **replay mode** (post-cierre de sesión). Al procesar señal a las `2025-02-28 10:30`, Observatory ya tiene la vela daily CERRADA de `2025-02-28` disponible. Esto significa:

- `candles_daily` incluye `dt <= date` (inclusive el día de la señal), NO `dt < date`.
- `a_chg` y `spy_chg` usan el close FINAL del día actual, alineados temporalmente.
- En live production esto sería look-ahead; para paridad con el sample hay que replicar el replay.

El runner `parity_qqq_regenerate.py` implementa esta convención en su `slice_for_signal`. **No cambiar sin regenerar el sample.**

### 9. Aggregation 15M vs 1H asimétrica

- **15M:** bucket open-stamped `[T, T+14]`. La última vela al momento T es **parcial** (close = 1min de T). El sample `price_at_signal` matchea ese close.
- **1H:** bucket open-stamped **con dt = primera 1min del día** (`09:30` en mercado US, no `09:00` round). Se resetea al cambio de día para evitar contaminar con data del día anterior (ver gotcha #16). Convención verificada bit-a-bit contra el `CandleBuilder` de Observatory post parity 100%.

### 10. Git: squash-merges se ven como "commits nuevos" en main (resuelto)

**Histórico:** GitHub squash-merge cambia el SHA. Cuando mergeás tu branch viejo a main vía PR, main obtiene un commit "nuevo" (squash) con el mismo código pero SHA distinto. Reciclar la misma branch causaba conflictos porque git no reconocía los squashes como propios.

**Resolución:** desde el PR #14 (2026-04-22) **el merge method de GitHub cambió a "Create a merge commit"** — preserva SHAs originales, permite reciclar la branch indefinidamente. Trade-off: main queda con merge bubbles en lugar de commits squash limpios. Los PRs #14, #15, #16, #17 se mergearon así sin fricción.

**Si en el futuro vuelve a squash-merge:** usar `git merge origin/main -X ours --no-ff` (seguro SOLO si main tiene squashes de la misma branch, mismo autor/contenido).

### 11. SQLite drop-ea tzinfo aunque declares `DateTime(timezone=True)`

SQLAlchemy + SQLite no preserva la zona horaria — devuelve datetimes naive al leer. Para ET tz-aware (ADR-0002) hay que usar un `TypeDecorator` custom (`ETDateTime` en `modules/db/models.py`) que:
- Valida `tzinfo is not None` al escribir (fail-fast si te pasan naive).
- Reatacha `ET_TZ` al leer.

**Lección:** en cualquier modelo nuevo con timestamps, usar `ETDateTime` y no `DateTime(timezone=True)` directo.

### 12. httpx `AsyncClient` + `ASGITransport` no corre el lifespan

En tests con `from httpx import ASGITransport, AsyncClient`, el startup/shutdown de FastAPI NO se ejecuta. Si tu app depende de `init_db()` en el lifespan, los tests fallan con tablas inexistentes.

**Fix:** `create_app(auto_init_db=False)` + `await init_db(app.state.db_engine)` manual en el fixture.

### 13. `backend.main` vs `main` en imports de tests

Tests unitarios corren desde `backend/` como cwd. `from backend.main import ...` falla con `ModuleNotFoundError` porque `backend` NO es un paquete importable — `backend/` es el sys.path root.

**Usar `from main import ...` en tests.** Regla general: imports absolutos **desde el directorio `backend/`**, no **del directorio `backend/`**.

### 14. Pydantic models cuyo nombre empieza con `Test*` colisionan con pytest

`pyproject.toml` tiene `python_classes = ["Test*"]`. Si una clase Pydantic se llama `TestResult` (o similar), pytest la intenta colectar como clase de tests y emite `PytestCollectionWarning`.

**Fix:** agregar `__test__ = False` como atributo de clase (antes de `model_config`).

```python
class TestResult(BaseModel):
    __test__ = False  # evita colección por pytest
    model_config = ConfigDict(frozen=True, extra="forbid")
    ...
```

Aplica a cualquier clase pública del dominio que coincida con el patrón — usar esto, NO renombrar la clase (rompería API pública).

### 15. `RUF006` — guardar referencia a `asyncio.create_task`

Python no mantiene referencias fuertes a tasks creados con `create_task` — si el GC los recoge antes de terminar, el task se cancela silenciosamente. Ruff lo detecta como `RUF006`.

**Patrón:** mantener un set de tasks vivos en `app.state` + `add_done_callback(set.discard)`:

```python
task = asyncio.create_task(coro(), name="xxx")
tasks = getattr(app.state, "my_tasks", None)
if tasks is None:
    tasks = set()
    app.state.my_tasks = tasks
tasks.add(task)
task.add_done_callback(tasks.discard)
```

Se usa para el warmup post-enable y para la revalidation del Validator en `api/routes/slots.py`.

### 16. Aggregator 1min→1H/15M: resetear bucket al cambio de día

El `CandleBuilder` de Observatory (`docs/specs/Observatory/Current/Replay/candle_builder.py` líneas 94-99) **descarta el bucket en construcción al cambio de fecha** — la vela 1H del último período del día anterior (típicamente `15:xx` en mercado US) nunca persiste en `candles_1h`. Es decisión explícita: sin 1min a `16:00` no hay cambio de bucket → building_1h queda abierta → llega 1min del día nuevo → `reset_day()` la descarta.

**Bug original en mi aggregator:** agrupaba por `HH:00` round cross-day. Las 1H del día actual acumulaban data pre-market o residuos del día anterior según cómo llegaban las 1min. MA20/40 divergían ~0.5 puntos vs Observatory → mismatch en trends y alignment.

**Fix:** bucket key = `(date, hour)` para 1H, `(date, hour, minute//15)` para 15M. Al cambio de fecha, la key cambia automáticamente; además descartamos explícitamente el bucket previo (no lo pusheamos a `result`). El `dt` de la vela agregada = dt de la **primera** 1min del bucket (no `HH:00` round) — primera vela del día es `09:30:00`, no `09:00:00`.

**Impacto histórico:** parity Fase 5.4 subió 77.14% → 98.37% solo con este fix.

### 17. ORB volume gate: usar `vol_ratio_intraday` (median same-day), no `volume_ratio_at` (mean cross-day)

El ORB breakout/breakdown tiene un gate binario `vol_ratio >= 1.0`. Observatory `indicators.py:vol_ratio(today_only=True)` computa la **mediana** de volúmenes de las velas completas del **mismo día**. Razones:

1. Anula el outlier del 9:30 (volumen apertura 3-5x del resto).
2. Same-day comparison — no mezcla perfiles de volumen de sesiones previas.
3. `price_at_signal` típicamente está al principio de sesión (9:30, 9:45, 10:00) — comparar contra data cross-day da ratios 0.04-0.31 que bloquean el ORB incorrectamente.

**Bug original en mi `analyze.py`:** usaba `volume_ratio_at(mean, 20)` — media sobre las últimas 20 velas 15M, cross-day. Al inicio del día la ventana era ~17 velas del día anterior + ~3 del actual → bloqueaba el ORB sistemáticamente.

**Fix:** `vol_ratio_intraday(candles_15m, sim_date)` ya estaba porteado desde Fase 5.2a pero nunca se había wired. Reemplazar el cálculo del `vol_ratio` en `analyze.py` resolvió los 4 mismatches restantes post-fix aggregator.

**Impacto histórico:** parity Fase 5.4 subió 98.37% → 100% solo con este fix.

**Lección general:** tanto #16 como #17 existían en el motor productivo. El parity exhaustivo fue el mecanismo que los expuso. Mantener Check F activo detecta regresiones futuras.

---

## Observatory como autoridad de paridad

El código de Observatory vive en `docs/specs/Observatory/Current/scanner/`:
- `scoring.py` — pipeline principal
- `engine.py` — gates, time filters, ORB logic
- `patterns.py` — detección de triggers (es la fuente canónica)
- `indicators.py` — indicadores (SMA/EMA/BB/ATR/volume)

**Sample canonical QQQ:** `backend/fixtures/parity_reference/` — 30 sesiones 2025, 245 señales. Se generó con este código exacto. Cualquier divergencia entre mi engine y el sample = bug en mi port.

**Regla:** si hay duda sobre semántica (rounding, string vs numeric compare, ranges de loop, qué patterns emitir), **leer Observatory primero**, preguntar al usuario solo si sigue habiendo ambigüedad.

---

## Convenciones de código

- **Python 3.11**, type hints estrictos, Pydantic v2 con `frozen=True, extra="forbid"` para modelos públicos.
- **Tests:** pytest, fixture-free cuando sea posible, factories locales.
- **Docstrings:** español, pegados al "por qué" y a la paridad Observatory cuando aplique. Referenciar líneas exactas cuando es port literal.
- **Comments:** solo cuando el WHY no es obvio. NO narrar el WHAT.
- **Imports:** absolutos desde `backend/` (ej. `from engines.scoring.alignment import ...`), nunca relativos.
- **Rounding:** helpers como `round(x, 2)` al output, `prev` interno sin redondear en recurrencias.

---

## Git workflow

- **Todo desarrollo:** rama `claude/review-project-setup-4DnEm`. Nunca push directo a main.
- **Antes de commit:** correr `cd backend && python -m pytest tests/ -q` y asegurar que pasa.
- **Commit messages:** español, conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`). Scope entre paréntesis (`feat(scoring):`).
- **Footer:** incluir `https://claude.ai/code/...` como manda la configuración del repo.
- **Merge strategy GitHub:** actualmente "Squash and merge". Ver gotcha #10 — considerar cambiar a "Create a merge commit" si se sigue reciclando la misma branch long-lived.
- **Nunca:**
  - `--no-verify` para saltear hooks.
  - `--amend` a commits ya pusheados.
  - `reset --hard` o `push --force` sin pedir permiso.
  - `add -A` o `add .` — listar archivos explícitos.

---

## Comandos útiles rápidos

```bash
# Tests scoring completos
cd backend && python -m pytest tests/engines/scoring/ -q

# Tests con verbose y último fallo
cd backend && python -m pytest tests/engines/scoring/ -xvs

# Lint
cd backend && ruff check .

# Ver estado vs main
git log --oneline origin/main..HEAD
git log --oneline HEAD..origin/main
```

---

## Qué hacer al arrancar un chat nuevo

1. Saludar con la frase obligatoria.
2. Leer este `CLAUDE.md` completo (ya lo estás haciendo).
3. Leer `docs/specs/SCANNER_V5_HANDOFF_CURRENT.md` para contexto de producto.
4. Si se va a tocar scoring: leer `docs/specs/SCORING_ENGINE_SPEC.md` + `docs/specs/Observatory/Current/scanner/scoring.py` + `patterns.py` + `engine.py`.
5. Si se va a tocar Validator (próximo gran bloque): leer `docs/specs/SCANNER_V5_FEATURE_DECISIONS.md` sección batería D/A/B/C/E/F/G.
6. Correr los tests antes de tocar nada para verificar baseline verde (851 passing esperados).
7. **No avanzar sin "ejecuta".** Proponer, esperar, ejecutar.

### Arranque end-to-end del backend

```bash
SCANNER_API_KEYS="sk-dev" \
SCANNER_TWELVEDATA_KEYS="k1:sk-td-1:8:800" \
SCANNER_REGISTRY_PATH="slot_registry.json" \
python backend/main.py
```

---

## Protocolo Handoff al cerrar un chat

Al terminar una sesión de desarrollo (antes de dejar el chat inactivo), correr
este protocolo para dejar el proyecto listo para el siguiente chat. Álvaro lo
dispara con "handoff" — no inferirlo por cuenta propia.

### Pasos

1. **Actualizar avances en `CLAUDE.md` — sección "Estado actual de la implementación":**
   - Mover ítems nuevos de "Pendiente" a "Completado" (o agregar sub-fases en
     el desglose por sub-fase).
   - Actualizar el contador de **tests passing** (`cd backend && python -m
     pytest tests/ -q` para el número global; añadir el sub-total del módulo
     tocado si aplica).
   - Actualizar "Divergencias conocidas" si se resolvió alguna.
   - Agregar **gotchas nuevas** (sección #N) si se aprendió algo que no se
     debe repetir en futuros chats — con ejemplo concreto de código o commit.

2. **Actualizar descripciones de directorios y `README.md`:**
   - Si se crearon directorios nuevos en `backend/modules/<x>/` o
     `backend/engines/<x>/`, asegurar que aparecen en el árbol del
     `README.md` raíz y que su `README.md` de módulo describe el alcance
     actual.
   - Si los `README.md` de módulos tocados quedaron obsoletos, refrescarlos
     con el scope final (no narrar el what del código — reflejar
     responsabilidades y puntos de entrada).

3. **Indexar archivos nuevos en `CLAUDE.md`:**
   - Agregar los módulos/archivos relevantes a la tabla correspondiente
     ("Módulos nuevos del Scoring Engine" o crear sub-sección análoga por
     capa si no existe).
   - Mantener la tabla concisa: archivo + rol en 1 línea.

4. **Dejar info relevante para el siguiente chat:**
   - Sub-sección "Para el siguiente chat" (temporal, puede sobrescribirse en
     el próximo handoff): decisiones abiertas, caminos recomendados,
     bloqueos conocidos, tests o comandos puntuales que el próximo chat
     necesitará correr.
   - Si hay PR abierto: link + estado.

5. **Commit + push:**
   - `docs(claude): handoff <YYYY-MM-DD> — <resumen 1 línea>`.
   - Push a la rama de trabajo actual (ver §Git workflow).
   - Si hay PR abierto que refleja el trabajo de la sesión, actualizar la
     descripción con los deltas del día.

### Cuándo NO correr el protocolo

- Commits WIP intermedios (cambio de contexto breve, va en el próximo
  commit).
- Sesiones exploratorias sin cambios de código.
- Cuando el trabajo sigue en vuelo y no hay un "checkpoint" natural.

---

**Fin del contexto. Cuando leas esto por primera vez en un chat nuevo: saludar, confirmar que lo leíste mencionando 1-2 gotchas específicas, y preguntar en qué pinchamos hoy.**
