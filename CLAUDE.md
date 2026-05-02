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

**Rama activa:** `claude/plan-feature-development-qh7yJ` — sesión nueva (2026-05-02) sobre main post-PR #50. La rama previa `OZyjj` cerró con PRs #45→#48 (cierre de deudas técnicas backend + 3 BUGs del smoke manual); luego se mergearon PRs #49 (19 bugs BUG-013→BUG-031 en QA con backend live + Playwright) y PR #50 (script standalone `replay_canonical_parity.py`).

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
| Config | `backend/modules/config/` — plaintext + `api/routes/config.py` con 10 endpoints (load/save/save_as/clear/last/current + PUT keys/s3/startup_flags + reload-policies). Modelo `.config` portable; sistema arranca de cero sin `.config` cargado. LAST persistido en `data/last_config_path.json`. | ✅ wired |
| D (Entrypoint) | `backend/main.py` + `backend/settings.py` + `backend/api/workers.py` — Pydantic Settings, lifecycle, worker factories, Validator wiring, archive wiring, shutdown rotation, healthcheck wired al heartbeat | ✅ |
| Fixtures | `backend/modules/fixtures/` — loader + `api/routes/fixtures.py` con GET list / POST upload / DELETE (valida engine_compat_range, 409 si fixture_id duplicado o usado por slot) | ✅ wired |

**Tests totales:** **1132 passing** + 1 slow (parity regression guard) en `backend/tests/` (post PR #49 stability fixes). 77 archivos de test, 1112 funciones `def test_` (la diferencia con 1132 viene de `@pytest.mark.parametrize`). `ruff check .` limpio.

**Frontend tests:** 7/7 passing (`pnpm test` en `frontend/`). Vite build limpio (~333KB JS gzip 104KB · 82KB CSS gzip 16KB). `pnpm lint` (Biome) limpio. `pnpm tsc --noEmit` limpio.

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

### Módulos nuevos del Config plaintext + REST + Fixtures REST + Vacuum (sesión OZyjj 2026-04-30)

| Archivo | Rol |
|---|---|
| `modules/config/models.py` | `UserConfig` Pydantic frozen + `TDKeyConfig` + `S3Config` + `StartupFlags` (override de `Settings`). Plaintext, sin encripción |
| `modules/config/loader.py` | `save_config` / `load_config` plaintext con atomic write |
| `modules/config/__init__.py` | API pública del módulo |
| `api/routes/config.py` | 10 endpoints: load / save / save_as / clear / last / current / PUT keys/s3/startup_flags / reload-policies. Hot-reload del KeyPool integrado |
| `api/routes/fixtures.py` | 3 endpoints: GET (list) / POST upload (multipart) / DELETE. Valida `engine_compat_range` ⊇ `ENGINE_VERSION`, persiste sibling `.sha256`, 409 si fixture_id duplicado o usado por slot |
| `engines/data/api_keys.py:KeyPool.reload(keys)` | Hot-reload de keys preservando contadores runtime de las que siguen activas. Wipe del secret de las eliminadas |
| `api/routes/database.py:vacuum` | `POST /database/vacuum` — SQLite VACUUM bloqueante via `asyncio.to_thread`. 503 si DB locked |
| `main.py:_try_load_last_config` | Carga silenciosa del LAST `.config` al arranque del backend si el path apuntado existe |

### Módulos nuevos del Launcher + Stability + Replay (sesiones OZyjj/stability/pre-alpha · PRs #46-#50)

| Archivo | Rol |
|---|---|
| `backend/launcher.py` | Supervisor del proceso uvicorn · setea `SCANNER_LAUNCHER_PID` env · detecta `restart_requested.flag` y re-arranca · WS idle shutdown 60s · bearer auto-inject (PR #46) |
| `scripts/build-launcher.sh` | Build wrapper · `pnpm build` → `frontend/dist/` → copia a `backend/static/` · verifica entrypoint para PyInstaller |
| `api/routes/system.py` | `POST /api/v1/system/{shutdown,restart}` con flag file + signal SIGTERM · auth Bearer obligatorio (PR #46) |
| `api/routes/candles.py` | `GET /api/v1/candles/{ticker}?tf=&n=` · alimenta el Panel.Chart OHLC SVG del Cockpit (PR #49 BUG-022) |
| `api/routes/scan.py:scan_slot` | `POST /api/v1/scan/slot/{id}` · resuelve fixture+candles desde registry/data_engine + broadcast `api_usage.tick` post-scan (PR #49 BUG-015/021) |
| `modules/fixtures/metrics_lookup.py` | Lookup de `wr_pct` por banda desde `.metrics.json` · usado por `signals.py` augment (PR #49 BUG-023) |
| `engines/data/probes.py:_build_td_probe` | Helper compartido extraído de `main.py` · construye el probe TD para Validator Check G · llamado al startup y al hot-reload de keys (PR #47 BUG-001 capa 2) |
| `Validator.set_td_probe(...)` | Setter para que `_reload_key_pool` reconstruya el probe sin reiniciar (PR #47) |
| `scripts/replay_canonical_parity.py` | Standalone parity test · 1m → CandleBuilder → analyze → SQLite + MFE/MAE forward 30 min · compara con `.metrics.json:metrics_training.by_band` · 245/245 paridad bit-a-bit, S y S+ exactos (PR #50) |
| `frontend/src/components/ui/{Pilot,Badge,Toggle,Dropzone}.tsx` | Componentes UI compartidos del Configuration · 4 estados/variantes c/u (sesión OZyjj) |
| `frontend/src/api/queryClient.ts` | Singleton del QueryClient TanStack para uso fuera de hooks (ej. desde `ws.ts`) (PR #49 BUG-020) |
| `frontend/src/pages/Configuration/boxes/{Box1Engines,Box2Config,Box3Keys,Box4Slots,Box5Validator,Box6S3}.tsx` | 6 boxes operativos del Configuration (sesión OZyjj · refinamientos UX-001/002/003 en PR #46) |

### Frontend (Cockpit + Configuración wired al backend · 2026-04-30 · refinado PR #46-#49)

| Capa | Detalle | Estado |
|---|---|---|
| Toolchain | Vite 5 + React 18 + TS strict + pnpm + Biome + Vitest + jsdom + RTL | ✅ |
| Estilos | tokens Phoenix completos (`src/styles/tokens.css`), reset+atmosphere global, `shell.css` topbar/apibar/footer, `cockpit.css` watchlist+panel + estados degradados | ✅ |
| Tailwind | Plugin custom Phoenix con utilities `glass-*`, `tier-*`, `bookmark-shape`, `iridescent-*`, `num-tabular`. Theme extendido con paleta + radii + tipografías | ✅ |
| Router | React Router 6 con 4 pestañas (Cockpit · Dashboard · Memento · Configuración) + `AppShell` compartido. `/` → `/cockpit` | ✅ |
| Cockpit shell | Watchlist + Panel banner/exec/chart/detail + halo cromático tier-aware + iridiscente Houdini + dithering anti-posterización + oklab + sweep specular | ✅ |
| Cockpit estados | 7 estados: normal · warmup · degraded · splus · error · scanning · loading · prioridad resuelta en `useCockpitState()` | ✅ |
| Stores Zustand | `auth` (persist localStorage), `slots`, `apiUsage`, `signals`, `engine` (con `dataPaused` + `ws`), `scanning` | ✅ |
| TanStack Query | `useEngineHealth`, `useSlots`, `useLatestSignal`, `useAutoScanStatus`, `useScanManual`, `useAutoScanPause/Resume` | ✅ |
| WebSocket | `useScannerWS()` con auto-reconnect (backoff 1/2/4/8/16s), dispatch a stores de los 6 eventos | ✅ |
| Efectos UI | Reloj/fecha live ET, Toast component (4 tonos), Botón Copiar funcional con clipboard, Toggle AUTO cableado, Botón Scan + mutation | ✅ |
| Bearer UI | Input compacto en footer con persistencia localStorage + reconexión WS al guardar | ✅ |
| DevStateSwitcher | Switcher dev-only (botón ⚙ bottom-right) para forzar 8 estados sin backend. **Deuda técnica documentada** | ✅ |
| Configuración wired | 6 boxes implementados (Engines/Config/Keys/Slots/Validator/S3) ~2227 líneas + 35 hooks TanStack + `configUi` + `validatorProgress` stores. Pilotos rojo/amarillo/verde reales (UX-001) · Box4 como tarjetas (UX-002) · `components/ui/{Pilot,Badge,Toggle,Dropzone}` | ✅ |
| Stubs restantes | Dashboard / Memento — placeholder unificado en `pages/_stub/StubPage.tsx` (10 líneas cada uno) | ✅ |
| Chart Cockpit | OHLC SVG real (50 candles 15m, bodies+wicks+línea de cierres+eje Y · BUG-022 PR #49). Lightweight Charts pendiente | ✅ shell |
| Augmentations backend | `signals.py` augment con `wr_pct` desde `metrics_lookup.py` + `chat_format` regenerado en read time + `ind.price` desde candles_15m (BUG-023/024 PR #49) | ✅ |
| Launcher exe | `backend/launcher.py` supervisor + `scripts/build-launcher.sh` (build frontend → static/ + verifica entrypoint) + bearer auto-inject + WS idle shutdown 60s + `launcher_attached` flag en `/engine/health` (BUG-014) | ✅ listo para PyInstaller |
| API client | `src/api/client.ts` + `queryClient.ts` singleton (uso fuera de hooks · BUG-020) + bearer + `ApiError` + `getBearerToken`. Vite proxy `/api`+`/ws` → `VITE_BACKEND_URL` | ✅ |
| Tests smoke | `src/test/router.test.tsx` — render + landmarks + 4 pestañas + active state + apibar + cockpit + Configuración (7/7) | ✅ |
| Wireframes Configuración | `Configuracion specs.md` (spec funcional 6 secciones · 18 endpoints + 11 deudas técnicas) + `Configuracion Wireframes V2.html` + `V3.html` mid-fi paper-style + `Configuracion Hi-Fi v1.html` reference | ✅ |

### Módulos nuevos del Frontend (Cockpit + estados + wiring)

| Archivo | Rol |
|---|---|
| `src/main.tsx` | Entrypoint · `QueryClientProvider` + `ToastProvider` + `RouterProvider` |
| `src/router.tsx` | React Router 6 con 4 rutas (cockpit/dashboard/memento/configuracion). `/` → `/cockpit` |
| `src/api/client.ts` | Fetch wrapper con bearer opcional + `ApiError` + `setBearerToken/getBearerToken` |
| `src/api/types.ts` | Tipos del backend (EngineHealth · SlotInfo · KeyUsage · SignalPayload · 6 WS events) |
| `src/api/queries.ts` | 7 hooks TanStack Query: `useEngineHealth/Slots/LatestSignal/AutoScanStatus/ScanManual/AutoScanPause/Resume` |
| `src/api/ws.ts` | `useScannerWS()` con auto-reconnect (backoff 1/2/4/8/16s), dispatch a stores |
| `src/stores/auth.ts` | Bearer token persist localStorage + sync con `setBearerToken` del client |
| `src/stores/engine.ts` | Estados de los motores + `dataPaused` + `ws` (WsConnectionState) + `stateOverride` (DEUDA: dev) |
| `src/stores/slots.ts` | 6 slots del registry + `selectedSlotId` (default 2 · QQQ del Hi-Fi v2) |
| `src/stores/apiUsage.ts` | Estado por TD key alimentado por `api_usage.tick` del WS |
| `src/stores/signals.ts` | `bySlot` + `latest` actualizados por `signal.new` del WS o por `useLatestSignal` |
| `src/stores/scanning.ts` | `active: Set<number>` efímero · ON/OFF por slot durante mutation `useScanManual` |
| `src/components/AppShell/{AppShell,TopBar,ApiBar,Footer}.tsx` | Shell con health-line + topbar (live indicator del WS) + apibar (5 keys + scan + auto) + footer (status + bearer input) |
| `src/components/Toast/{ToastProvider,toast.css}` | Stack bottom-right · 4 tonos (success/info/warn/error) · context provider |
| `src/components/Dev/{DevStateSwitcher,dev-state-switcher.css}` | DEUDA TÉCNICA · switcher dev-only (botón ⚙) para forzar 8 estados del Cockpit |
| `src/lib/clock.ts` | Reloj/fecha live ET vía `useSyncExternalStore` (un único setInterval global) |
| `src/lib/copyToClipboard.ts` | Helper con fallback `textarea + execCommand` |
| `src/lib/chatFormat.ts` | Template del payload de copiar (fallback hardcoded del Hi-Fi v2) |
| `src/pages/Cockpit/CockpitPage.tsx` | Página · resuelve `effectiveState` (incluye `loading` derivado de queries iniciales) |
| `src/pages/Cockpit/Watchlist.tsx` | 6 slots fallback hardcoded + override del backend cuando hay datos |
| `src/pages/Cockpit/Slot.tsx` | Card + bookmark sólo en A/A+/S/S+ + sparkline + flag `is-scanning` por store |
| `src/pages/Cockpit/Sparkline.tsx` | SVG con linear gradients fill+stroke por slot |
| `src/pages/Cockpit/Panel.tsx` | Banner sticky tier-aware + Exec chips + Chart estático + Detail colapsable |
| `src/pages/Cockpit/StateToast.tsx` | `useCockpitState()` resuelve estado por prioridad + `<StateToasts>` component |
| `src/pages/Cockpit/useEffectiveSlot.ts` | Helper que combina backend + fallback Hi-Fi v2 (fix del bug del banner sin backend) |
| `src/pages/Cockpit/data.ts` | Fallback hardcoded del Hi-Fi v2 (6 slots con tickers + bands + sparklines) |
| `src/pages/Cockpit/cockpit.css` | CSS verbatim del Hi-Fi v2 + estados degradados + scanning pulse + state-toasts |
| `src/pages/{Configuration,Dashboard,Memento}/*Page.tsx` | Stubs unificados via `pages/_stub/StubPage.tsx` |
| `src/styles/{tokens,global,shell}.css` | Paleta Phoenix + reset + atmosphere + topbar/apibar/footer compartido |
| `tailwind.config.ts` | Plugin custom Phoenix · utilities `glass-*/tier-*/bookmark-shape/iridescent-*` con interpolación oklab |
| `frontend/wireframing/Configuracion specs.md` | Spec funcional 6 secciones · 18 endpoints REST + 11 deudas técnicas + 6 eventos WS |
| `frontend/wireframing/Configuracion Wireframes V2.html` | Mid-fi paper-style 5 boxes (primera iteración) |
| `frontend/wireframing/Configuracion Wireframes V3.html` | Mid-fi paper-style 6 boxes con feedback aplicado · 1354 líneas |

### Pendiente

- **Frontend (próximas iteraciones · Cockpit + Configuración wired · faltan Dashboard/Memento):**
  - ~~Stores Zustand · TanStack Query · WebSocket listener~~ → **Cerrado 2026-04-29.** 8 stores + 35 hooks + `useScannerWS()` con auto-reconnect implementados.
  - ~~Estados degradados del Cockpit~~ → **Cerrado 2026-04-29.** 7 estados implementados con prioridad: error → splus → degraded → warmup → scanning → loading → normal.
  - ~~**Hi-Fi de Configuración**~~ → **Cerrado 2026-04-30 sesión OZyjj.** 6 boxes (Engines/Config/Keys/Slots/Validator/S3) implementados ~2227 líneas. Pilotos reales + Box4 como tarjetas + Cockpit sin fake data refinados en PR #46 (UX-001/002/003).
  - **Hi-Fi del Dashboard** — sin spec ni wireframe todavía. La persistencia DB + retención que se sacó de Configuración vive acá. Pendiente.
  - **Hi-Fi de Memento** — sin spec ni wireframe todavía. Pendiente.
  - **Lightweight Charts** en el panel del Cockpit. Por ahora hay OHLC SVG real (BUG-022 PR #49: 50 candles 15m, bodies+wicks+línea de cierres+eje Y) — listo para reemplazo cuando se decida la lib.
  - ~~**11 deudas técnicas del backend**~~ → **Cerradas todas las viables.** 9 en sesión OZyjj (PRs #45-#47); BUG-001 cierre real + BUG-002 (registry sin scan_context) + BUG-003 (Box4 select fixture) en PR #48. `POST /system/restart` quedó wired vía launcher (PR #46). `GET /system/open-folder` descartado v1.
  - ~~**SEC-001 path traversal SPA fallback**~~ → **Cerrado en PR #47.** Fix 2 capas (rechazo `..` + `resolve()` + `relative_to(base)`) + 8 tests de regresión en `tests/api/test_static.py`.
  - ~~**UX-001/002/003**~~ → **Cerrados en PR #46:** semáforos reales por box · Box 4 Slots como 6 cards · Cockpit sin fake data hardcodeados.
  - ~~**BUG-013 → BUG-031 (19 bugs)**~~ → **Cerrados en PR #49** (sesión QA con backend live + Playwright). Notable: `routes/candles.py` nuevo, `metrics_lookup.py` nuevo, broadcast `api_usage.tick` post-scan, hot-reload signals augment con `wr_pct`+`chat_format`+`last_price`, Box3Keys probe diagnostics, BUG-029 (preserva secret cuando frontend manda `***` masked).
  - ~~**Setting `auto_scan_run_at_startup`**~~ → **Eliminado por decisión.** El sistema arranca con auto-scan activo (lifespan); el toggle pause/resume se hace desde el Cockpit, no desde Configuración Paso 5.
  - ~~**Auto-scan inicial PAUSED**~~ → **Cerrado en PR #49 (BUG-016).** Antes arrancaba consumiendo TD credits sin que el usuario lo pidiera; ahora el `running.clear()` inicial obliga a tocar Resume.
- ~~**Fase 5.4 cierre**~~ → **Cerrado 2026-04-23 al 100%.** Post subida del `qqq_1min.json` original del Observatory, se identificaron 2 bugs reales del motor (ver gotchas #16 y #17): aggregator no resetaba al cambio de día + ORB gate usaba mean-cross-day en vez de median-intraday. Ambos arreglados → **245/245 match**. `DEFAULT_MIN_MATCH_RATE` subido a 0.99. Regression guard en `test_parity_regression.py` (slow, ~2min).
- ~~**Healthcheck continuo spec §3.4**~~ → **Cerrado 2026-04-23.** `engines/scoring/healthcheck.py` wired al `heartbeat_worker` con `healthcheck_fn` opcional. Cada 2 min valida operativamente el motor (no-crash, shape, signal vocab) y reporta green/yellow+ENG-050/red+ENG-001 al Dashboard.
- ~~**Watchdog automático AR.5**~~ → **Cerrado 2026-04-23.** `engines/database/watchdog.py:aggressive_rotation_watchdog` opt-in via `SCANNER_AGGRESSIVE_ROTATION_ENABLED=true`. Chequea tamaño DB cada `SCANNER_AGGRESSIVE_ROTATION_INTERVAL_S` (default 3600s) y dispara rotación agresiva. Default off por ser destructivo.
- ~~**`modules/config/` encriptado**~~ → **Refactoreado 2026-04-30 a plaintext + wired al REST (sesión OZyjj).** El módulo Fernet/master_key fue eliminado: el `.config` es ahora un archivo portable JSON plaintext que el usuario maneja como un documento (Cargar / Guardar / LAST). Sin `.config` cargado, el sistema arranca de cero. La seguridad depende de dónde el usuario almacene el archivo. 10 endpoints REST en `api/routes/config.py`. LAST persistido en `data/last_config_path.json`. Hot-reload del KeyPool tras `PUT /config/twelvedata_keys`.
- **Distribución Windows:** `.exe` via Inno Setup. Depende de frontend.
- ~~**Auto-scan pause/resume**~~ → **Cerrado.** `POST /api/v1/scan/auto/{pause,resume,status}` con `asyncio.Event` en `app.state.auto_scan_running`. El loop bloquea en `await running.wait()` antes del próximo ciclo y emite `engine.status={status: "paused"}` por WS. 6 tests nuevos en `tests/api/test_scan.py::TestAutoScanPauseResume`. Frontend cableado vía `useAutoScanPause/Resume/Status`.

#### Deudas técnicas a eliminar / cerrar antes de la release 1

**Frontend:**
- **`frontend/src/components/Dev/DevStateSwitcher.tsx` + `dev-state-switcher.css`**: switcher flotante (sólo `import.meta.env.DEV`) que fuerza estados del Cockpit (warmup/degraded/splus/error/scanning/loading) escribiendo en `useEngineStore.stateOverride`. Útil para previsualizar variantes sin levantar backend ni reproducir condiciones reales. Pre-release: borrar la carpeta `Dev/`, quitar `stateOverride` + `setStateOverride` de `engine.ts`, y la rama del override en `useCockpitState`.

**Backend (endpoints faltantes — estado 2026-04-30 post sesión OZyjj):**

Identificados durante el spec funcional `Configuracion specs.md` §6.2. Estado tras la sesión:

| Método | Path | Estado |
|---|---|---|
| `POST` | `/api/v1/fixtures/upload` | ✅ wired (sesión OZyjj) |
| `DELETE` | `/api/v1/fixtures/{fixture_id}` | ✅ wired (sesión OZyjj) |
| `POST` | `/api/v1/database/vacuum` | ✅ wired (sesión OZyjj) |
| `PUT` | `/api/v1/config/twelvedata_keys` | ✅ wired (sesión OZyjj) — hot-reload del KeyPool |
| `PUT` | `/api/v1/config/s3` | ✅ wired (sesión OZyjj) |
| `PUT` | `/api/v1/config/startup_flags` | ✅ wired (sesión OZyjj) |
| `POST` | `/api/v1/config/reload-policies` | ✅ wired (sesión OZyjj) |
| `POST` | `/api/v1/config/master-key/generate` | ❌ eliminado (modelo `.config` plaintext) |
| `POST` | `/api/v1/config/master-key/load` | ❌ eliminado (modelo `.config` plaintext) |
| `POST` | `/api/v1/system/restart` | ⏸ diferido a PR aparte (alto riesgo `os.execv`) |
| `GET` | `/api/v1/system/open-folder` | ❌ descartado v1 (per spec) |

Adicionales wired en la sesión:
- `POST /api/v1/config/load`, `/save`, `/save_as`, `/clear` — gestión del `.config` portable.
- `GET /api/v1/config/last`, `/current` — lectura del runtime + LAST.
- `GET /api/v1/fixtures` — listado con metadata + sha256 status + slots que lo usan.

#### Deudas técnicas de seguridad (sesión 2026-04-30 · post launcher)

##### 🟢 SEC-001 · Path traversal en SPA fallback — **CERRADO en PR #47**

**Hallazgo del security-review skill** sobre el commit `1e2b159` (launcher / static mount).

**Localización:** `backend/api/app.py` · función `_mount_frontend.spa_fallback` (líneas ≈ 315–327).

**Síntoma:** el handler `@app.get("/{path:path}")` está sin auth y solo descarta paths que empiezan con `api/` o `ws`. Con `..` URL-encoded en el path (`/..%2Fdata%2Fbearer.txt`), `Path("static") / "../data/bearer.txt"` traversa fuera del `static_dir`. `is_file()` + `FileResponse` sirven el archivo al caller anónimo.

**Impacto en modo launcher:**
- Lectura no autenticada de `data/bearer.txt` → atacante obtiene el bearer master que da acceso a TODO el REST + WS.
- Lectura de `data/scanner.db`, `data/last_config_path.json`, `slot_registry.json`, fixtures, código de `backend/`, etc.
- Una vez con el bearer, puede hacer `GET /config/current?include_secrets=true` para extraer TD keys + S3 creds en plaintext.

**Vector práctico:** cualquier proceso/tab del browser con acceso a `127.0.0.1:8000` (mismo equipo, container vecino, drive-by, DNS rebinding).

**Fix recomendado** (no aplicado todavía):

```python
@app.get("/{path:path}", include_in_schema=False)
async def spa_fallback(path: str) -> Response:
    if path.startswith("api/") or path.startswith("ws"):
        raise HTTPException(status_code=404)
    # Reject traversal explicitly + resolve+containment.
    if ".." in path.split("/") or path.startswith("/"):
        return HTMLResponse(content=cached_index)
    base_resolved = base.resolve()
    try:
        candidate = (base / path).resolve()
        candidate.relative_to(base_resolved)        # raises si fuera de base
    except (ValueError, OSError):
        return HTMLResponse(content=cached_index)
    if candidate.is_file():
        return FileResponse(str(candidate))
    return HTMLResponse(content=cached_index)
```

**Test de regresión obligatorio:**
```python
r = await client.get("/..%2Fdata%2Fbearer.txt")
assert "scanner-bearer" in r.text   # devuelve SPA index, NO el bearer
```

**Hardening adicional sugerido:**
- Mover `data/bearer.txt` fuera del cwd del backend (ej. user home) para que ni siquiera una regresión del fallback alcance el archivo.
- Reemplazar el handler hand-rolled por `StaticFiles(directory=base, html=True)` (Starlette ya implementa traversal protection); mantener solo una capa thin custom para inyectar el meta del bearer en `index.html`.
- Considerar bind a `127.0.0.1` exclusivo (ya está) + `Host:` header check para mitigar DNS rebinding desde browsers.

##### Revisión más profunda pendiente

El security-review skill que se corrió (2026-04-30) **solo cubrió el diff del PR #45** (launcher + system endpoints + cableado motores). NO se hizo audit completo del repo. Zonas ciegas conocidas que requieren revisión más profunda antes de release 1:

1. **`POST /database/{backup,restore,backups}`** — credenciales S3 viajan en body request por compat histórica. Si alguien intercepta el HTTP local (proxy, otro proceso con acceso al puerto), las roba.
2. **`POST /fixtures/upload`** — multipart. ¿Path traversal vía `fixture_id` controlado por el atacante en el JSON del fixture? El backend usa `fixture_id` como filename — verificar que `..` se rechaza.
3. **`POST /config/{load,save,save_as}`** — aceptan `path` arbitrario del usuario. Sin sandbox del filesystem. Diseñado así por modelo "el usuario maneja sus paths" — pero si el frontend está expuesto via proxy, alguien podría leer/escribir cualquier archivo del SO.
4. **SQLi** — SQLAlchemy ORM previene la mayoría, pero hay algunos paths con strings interpolados. No revisado a fondo.
5. **Dependency vulns** — `pip-audit`, `npm audit` o `osv-scanner` nunca corridos en este repo. Pendiente.
6. **Secrets en logs** — verificar si bearer / TD secrets / S3 creds aparecen en excepciones, debug prints o el log file de loguru por error.
7. **WS message validation** — el backend ignora mensajes entrantes (server-push only) → bajo riesgo, pero no validé contra DoS por flooding.
8. **CSRF / XSS** — React escapa por default; verificar que no hay `dangerouslySetInnerHTML` ni library deps con XSS conocido.
9. **Permission check del `.config`** — al cargar un `.config` el backend lee de un path absoluto del filesystem; un atacante podría apuntar a un archivo sensible y ver el error de parsing (information disclosure parcial).
10. **Heartbeat workers de data + database** — son siempre green sin healthcheck real. Si el backend está degradado parcialmente, el endpoint de health miente. No es una vuln de seguridad pero puede confundir un audit operacional.

**Acción propuesta para release 1:**
- Cerrar SEC-001 antes del merge a producción.
- Programar audit completo del repo con security-review sobre `git diff $(git merge-base HEAD main)...HEAD` extendido al historial entero.
- Correr `pip-audit` + `pnpm audit` en CI.
- Considerar contratar audit externo si va a producción multi-usuario.

#### Deudas técnicas de UX · Configuración + Cockpit (sesión 2026-04-30)

##### 🟢 UX-001 · Pilotos por box con semáforo real — **CERRADO en PR #46**

Hoy el `BoxState` calcula `ok / warn / err / pend` con lógica ad-hoc por box. Los pilotos del rail (dot por box) y el badge de estado en el head no siempre reflejan el "configurado / parcial / no configurado" que el usuario espera. Modelo correcto:

- **🔴 rojo (`err`):** el box no está configurado en absoluto (ej. 0 TD keys, 0 slots habilitados, 0 fixtures, S3 vacío + sin probar).
- **🟡 amarillo (`warn`):** parcialmente configurado o con fallas no fatales (ej. 3/5 TD keys, 1 slot degraded de 5, último report del Validator con `warning`, S3 con creds pero probe falló).
- **🟢 verde (`ok`):** todo OK.

**Casos especiales:**
- **Box 3 TD Keys:** con **al menos 1 key configurada y probada OK** → verde. El producto funciona con 1 sola key (no requiere las 5).
- **Box 1 Motores:** verde si los 4 motores reportan green; warn si alguno yellow / paused; rojo si alguno red o si todos offline.
- **Box 6 S3:** opcional → si está vacío sin nunca haber sido configurado, mostrar como `pend` (gris) en lugar de rojo (no es error, es opcional). Si tiene creds pero probe falló → warn.

**Localización del fix:**
- `frontend/src/pages/Configuration/boxes/Box*.tsx` — variable `state: BoxState` derivada en cada box.
- `frontend/src/components/ui/Pilot.tsx` — variantes ya existen (`ok/warn/err/pend`); solo falta cablearlas correctamente.

**Test de regresión:** snapshot por box con cada estado de configuración representativo.

##### 🟢 UX-002 · Box 4 Slots como tarjetas en lugar de tabla — **CERRADO en PR #46**

Hoy Box 4 muestra los 6 slots como filas de una tabla compacta (ticker · fixture · enabled · status). Decisión nueva: mostrarlos como **6 tarjetas** análogas a las cards de TD keys del Box 3, donde el usuario:

1. **Primero ingresa el ticker** (input grande, foco evidente).
2. **Luego elige el fixture** (dropdown poblado con `useFixtures()` filtrado por compatibilidad).
3. Toggle enabled + estado runtime + acciones (deshabilitar / reintentar).

**Razón del cambio:** la tabla es densa y poco evidente para un usuario que arranca de cero. Las tarjetas guían el flujo "ticker → fixture → enable" naturalmente.

**Localización del fix:**
- `frontend/src/pages/Configuration/boxes/Box4Slots.tsx` — refactor del `<table class="slots-table">` a `<div class="slot-cards">` con `.slot-card` por slot.
- `frontend/src/pages/Configuration/configuration.css` — estilos `.slot-cards` + `.slot-card` (similares a `.key-card` pero con campos diferentes).
- Mantener la biblioteca de fixtures + el upload zone debajo (no cambian).

**Estimado:** ~150 LOC de refactor sin tocar wiring (`usePatchSlot` sigue igual).

##### 🟢 UX-003 · Cockpit sin fallback de valores fake en estado de loading — **CERRADO en PR #46/#47**

Hoy el panel del Cockpit (Banner + Exec chips + Chart + Detail) muestra **valores hardcodeados de QQQ** (`$485.32`, `+0.82%`, alineación, ATR, MA, etc) cuando no hay backend conectado o no hay señal cargada. Eso engaña: el usuario cree que el sistema está corriendo cuando en realidad no llegó dato real.

**Comportamiento correcto:**
- Sin motores levantados (data en `offline` / WS desconectado) → **estado "loading"** explícito en el panel: spinner + texto "esperando motores", sin valores numéricos.
- Sin señal cargada para el slot seleccionado → todos los valores numéricos como `—` (no fake).
- Banner del ticker: muestra solo el símbolo y el bookmark de tier; sin precio, sin alineación, sin ATR, sin niveles, sin MA. Todo en `—` o ausente.
- Chart: vacío con mensaje "sin datos" en lugar del SVG hardcodeado del Hi-Fi v2.

**Localización del fix:**
- `frontend/src/pages/Cockpit/Panel.tsx` — eliminar fallbacks del Hi-Fi v2 (`$485.32`, etc), reemplazar por `—` cuando `signal` es null.
- `frontend/src/pages/Cockpit/data.ts` — el módulo de fallback hardcodeado se mantiene pero NO se debe usar como display por default. Solo para tests / desarrollo. O eliminarlo completamente si queda huérfano.
- `frontend/src/pages/Cockpit/StateToast.tsx` — extender `useCockpitState()` para que el estado "loading" tenga prioridad cuando `useEngineStore.data === "offline"` o el WS está disconnected, y se traduzca a un overlay del panel.
- Coherente con el cambio que ya se hizo en Watchlist (commit `461645b`) — eliminar fake data del watchlist; aplicar mismo principio al panel.

**Test de regresión:** test del Cockpit que verifica que sin signal cargada, los `$` y `%` no aparecen en el DOM, solo `—`.

##### 🟢 BUG-001 · Probe de TD keys — **CERRADO en PR #47/#48** (contract + bootstrap-from-zero)

**Reportado por usuario tras smoke manual del Box 3 Keys con 1 key cargada desde la UI.** El botón "probar todas" o "probar individual" en `Box3Keys.tsx` rompe el frontend con `TypeError: cannot read properties of undefined (reading 'find')` y, aún arreglando el shape, el probe no corre porque el `td_probe` del Validator quedó en `None`.

**Capa 1 — contract mismatch backend ↔ frontend (causa directa del crash):**

- **Frontend espera** (`frontend/src/api/types.ts:310-316`):
  ```ts
  export interface ValidatorConnectivityResult {
    run_id: string;
    trigger: "connectivity";
    overall_status: ValidatorOverallStatus;
    td_keys: Array<{ key_id: string; ok: boolean; error?: string }>;
    s3?: { ok: boolean; error?: string } | null;
  }
  ```
- **Backend devuelve** el `TestResult` crudo del Check G (`backend/api/routes/validator.py:127-135`):
  ```python
  result = await validator.run_single_check("G")
  return result.model_dump()
  # → { "test_id": "G", "status": "skip"|"passed"|..., "severity": ..., "message": ...,
  #     "details": { "twelvedata": [...], "s3": {...} }, "duration_ms": ... }
  ```
- **Curl directo confirma:** `{"test_id":"G","status":"skip","details":{}}`. Sin `td_keys` en el payload, `r.td_keys.find(...)` en `Box3Keys.tsx:112` revienta.

**Capa 2 — probe nunca correría aunque el frontend leyera bien (bug latente):**

- En `backend/main.py:199-203`, `td_probe` se construye solo si `scan_context` existe al arranque (= TD keys vía env var `SCANNER_TWELVEDATA_KEYS`). Cuando las keys se ingresan desde la UI, el backend ya arrancó con `td_probe=None`.
- `PUT /config/twelvedata_keys` hot-reloadea el `KeyPool` pero **no reconstruye `validator.td_probe`** (`backend/api/routes/config.py` no lo toca). Por eso el endpoint sigue devolviendo `skip "sin probes de conectividad configuradas"` aun después de agregar keys.

**Fix recomendado (2 capas):**

1. **Backend** — adaptar la respuesta de `POST /validator/connectivity` al shape que espera el frontend:
   ```python
   @router.post("/connectivity")
   async def run_connectivity(...) -> dict:
       validator = _get_validator(request)
       result = await validator.run_single_check("G")
       td_details = (result.details or {}).get("twelvedata", []) if result.details else []
       s3_details = (result.details or {}).get("s3") if result.details else None
       return {
           "run_id": str(uuid4()),
           "trigger": "connectivity",
           "overall_status": _result_to_overall(result.status),  # passed→pass, etc
           "td_keys": td_details,   # esperar [{key_id, ok, error?}]
           "s3": s3_details,
       }
   ```
   Verificar primero el shape exacto que `Validator.run_single_check("G")` pone en `details["twelvedata"]` — puede que también necesite normalización.

2. **Backend** — reconstruir `td_probe` al hot-reload:
   - En `api/routes/config.py:put_twelvedata_keys` (donde se llama `key_pool.reload(keys)`), también reconstruir el probe del Validator y reasignarlo:
     ```python
     # Tras reload del KeyPool:
     validator = request.app.state.validator
     if validator is not None:
         from main import _build_td_probe   # extraer a helper compartido
         validator.td_probe = _build_td_probe(new_key_configs, td_client)
     ```
   - Alternativa más limpia: que el `Validator` consulte siempre `app.state.key_pool` + `app.state.td_client` al correr Check G, en lugar de capturar `td_probe` por inyección. Decisión a discutir con el usuario antes de refactorear.

**Tests de regresión obligatorios:**
- Backend: `tests/api/test_validator.py::test_connectivity_returns_td_keys_shape` — assert response.json() tiene `{run_id, trigger, overall_status, td_keys, s3}` con `td_keys` como `list`.
- Backend: `tests/api/test_validator.py::test_connectivity_after_hot_reload` — arrancar sin keys, `PUT /config/twelvedata_keys`, `POST /validator/connectivity`, assert que el probe corrió (no `skip`).
- Frontend: smoke manual de "probar todas" + "probar individual" sin crash, con feedback visible.

**Workaround para el usuario hasta el fix:** arrancar el backend con `SCANNER_TWELVEDATA_KEYS="k1:sk-...:8:800"` env var → `td_probe` se construye al startup y el probe corre, aunque el frontend siga crasheando hasta que se cierre la capa 1.

**Localización:**
- `backend/api/routes/validator.py:127-135` — endpoint a re-shape.
- `backend/main.py:199-203` + `backend/api/routes/config.py` — wiring del `td_probe` al hot-reload.
- `backend/modules/validator/checks/g_connectivity.py` — verificar el shape del `details["twelvedata"]`.
- `frontend/src/api/types.ts:310-316` — contrato esperado (no cambiar; el backend debe adaptarse).
- `frontend/src/pages/Configuration/boxes/Box3Keys.tsx:108-125` — defensive guard `if (!r.td_keys) return;` sería un parche pero el fix correcto es backend.

---

### Para el siguiente chat

**Estado al 2026-05-02 (post PRs #48-#50 mergeados a main):** backend completo + 31 BUGs cerrados (BUG-001 → BUG-031) + SEC-001 cerrado · **frontend con 2 pestañas wired**: Cockpit (Hi-Fi v2 Phoenix con chart OHLC SVG real) + Configuración (6 boxes operativos). Dashboard / Memento siguen como stubs (10 líneas cada uno). **1132 tests passing** + 1 slow (parity guard).

**Sesión 2026-05-01 (PR #48):** cierre de los 3 bugs reportados durante el smoke manual del flujo "primer arranque sin TD keys vía env var":
- **BUG-001 cierre real** (HIGH) · `_reload_key_pool` ahora bootstrapea `KeyPool` + `TwelveDataClient` cuando `app.state.key_pool is None` (caso real: backend arrancado sin `SCANNER_TWELVEDATA_KEYS`, usuario carga keys por primera vez vía UI). Defensive toast en `Box3Keys.tsx` cuando `r.td_keys.length === 0`.
- **BUG-002** (HIGH) · `_bootstrap_registry_runtime` siempre carga el registry (antes solo si había TD keys vía env). `_ensure_registry_file` crea `slot_registry.json` con 6 slots disabled si no existe. `_reload_key_pool` bootstrap path extendido también construye `DataEngine`.
- **BUG-003** (HIGH) · select de fixture en Box 4 nunca se habilitaba — root cause: ticker autosaveaba on-blur con `enabled:false` que wipea ticker+fixture. Fix: drafts locales hasta que el toggle activa, sin autosave on-blur. Validación local + un único PATCH al toggle ON. CSS `select.inp { width: 100% }`.
- 6 tests nuevos para los 3 bugs.

**Sesión 2026-05-01 (PR #49 · `claude/stability-fixes-BUG-013-031`):** sesión completa de QA + fixes con backend live (TD key real) + frontend Vite + Playwright para verificación visual E2E. **19 bugs cerrados (BUG-013 → BUG-031)**, todos con verificación E2E documentada en `CHANGELOG.md`.

Backend:
- **BUG-013** · `enable_slot` auto-fill de benchmark desde fixture cuando caller no especifica (REG-013 fix).
- **BUG-014** · launcher.py setea `SCANNER_LAUNCHER_PID` + `health.py` expone `launcher_attached` (deshabilita botón Restart en dev sin launcher).
- **BUG-015** · nuevo `POST /api/v1/scan/slot/{id}` resuelve fixture+candles desde registry/data_engine (reemplaza `/scan/manual` con body vacío que daba 422).
- **BUG-016** · auto-scan inicial PAUSED (`running.clear()` por default) — antes consumía TD credits sin pedirlo.
- **BUG-021** · `/scan/slot/{id}` broadcastea `api_usage.tick` post-scan + response incluye `fetch_meta` (banner de credits del Cockpit refresca).
- **BUG-022** · nuevo `GET /api/v1/candles/{ticker}?tf=&n=` para chart del Cockpit + frontend Panel.Chart con render OHLC SVG real (50 candles 15m, bodies+wicks+línea de cierres+eje Y).
- **BUG-023** · `modules/fixtures/metrics_lookup.py` (nuevo) + `signals.py` augment con `wr_pct` desde `.metrics.json`.
- **BUG-024** · `signals.py` augment con `chat_format` regenerado en read time + `ind.price` desde candles_15m si viene vacío (caso BLOCKED). `pipeline.py:build_chat_format` reescrito con bloques claros.
- **BUG-026/028** · `fetcher.py:test_key_diag` clasifica fallos del probe TD (rate_limit / invalid_key / http_xxx / network / malformed_response) + cliente fresh por llamada + 200ms entre keys consecutivas.
- **BUG-029** · `config_put_td_keys` preserva secret original cuando frontend re-envía `***` (masked redacted) — antes guardaba literalmente `"***"` y la key vieja quedaba inválida. **Patrón importante para cualquier endpoint que reciba secrets editables desde la UI.** Ver gotcha #18.

Frontend (type contracts + adapters):
- **BUG-009-012** · `RawSlotInfo` + `adaptSlot()` en `useSlots` (backend usa `slot`/`base_state`/`fixture_path`, frontend esperaba `slot_id`/`enabled`). `DatabaseStatsResponse` alineado al shape real.
- **BUG-017/018** · `useLatestSignal` toma `items[0]` (backend devuelve `list[dict]`). `SignalPayload.signal: boolean`; Banner deriva label visible (NEUTRAL/SETUP/REVISAR/BLOQUEADO) desde `conf` en lugar de crashear con `.toLowerCase()` sobre bool.
- **BUG-019** · `AppShell.useBackendWiring` auto-selecciona primer slot operativo + `ApiBar.handleScan` resuelve targetSlot por status (no por selectedSlotId hardcoded — antes 409 si vacío).
- **BUG-020** · `ws.ts` dispatch de `slot.status` invalida `['slots']` query · `api/queryClient.ts` (nuevo singleton para uso fuera de hooks).
- **BUG-025/027/030/031** · Panel.Exec wired a `signal.layers` + `signal.ind` · Box3Keys.onProbeOne actualiza badges de TODAS las keys · `useScanSlot.onSettled` invalida `['candles']` + ws dispatch de `signal.new` también (chart refresca tras scan) · chip "PROBABILIDAD" en Cockpit Exec block.

Infra:
- **BUG-006** · `.gitattributes`: `text eol=lf` para `fixtures/**/*.json` y `.sha256` (Windows autocrlf rompía hash de canonicals · REG-020). **Acción manual requerida tras merge:** `git add --renormalize . && git commit -m "renormalize line endings post .gitattributes"`. Ver gotcha #19.

**Sesión 2026-05-02 (PR #50 · `prueba-pre-alpha`):** script standalone de regression / parity test del scoring engine vs canonical pre-alfa.
- `scripts/replay_canonical_parity.py` (~470 líneas) · itera 1m candles → CandleBuilder agrega 15m/1h → `analyze(fixture, *)` en cada cierre 15m → persiste a SQLite + tracking forward 30 min para MFE/MAE → agrega por banda y compara con `.metrics.json:metrics_training.by_band`.
- Última ejecución (2026-05-01) sobre `qqq_canonical_v1` full 36m: counts por banda dentro de **±1.55%**; **S y S+ exactos (51/51, 11/11)**; WR @ 30 min mean |Δ| = 2.64 pp; banda S idéntica (60.8% ↔ 60.8%); mfe_mae con AVG(MFE/MAE) matchea banda B casi exacto (10.34 ↔ 10.37). Wall time ~82 min single-threaded.
- Veredicto: **engine V5 production-ready** para la calibración existente.
- Sirve como garantía I2 del scoring engine spec (determinístico, mismos inputs → mismo output).
- DB output a `backend/data/replay_*.db` (gitignored).

---

**Estado al 2026-04-30 (post sesión OZyjj · scaffold React de Configuración):** backend completo · **frontend con 4 pestañas wired**: Cockpit + Configuración (NUEVO), Dashboard / Memento siguen como stubs.

**Sesión 2026-04-30 (continuación · scaffold de Configuración):**

10 commits incrementales sobre la rama `claude/review-project-status-OZyjj`, todos con `tsc --noEmit` + `pnpm lint` + `pnpm test` + `pnpm build` verdes.

**1. Tipos + queries:**
- `frontend/src/api/types.ts` (+220 líneas): TDKeyConfig, S3Config, StartupFlags, UserConfig, FixtureListItem, ValidatorReport*, DatabaseStats*, S3Backup*, SlotPatch*.
- `frontend/src/api/queries.ts` (+24 hooks): config (10) · fixtures (3) · validator (4) · database (4) · S3 (3) · slots PATCH.

**2. Stores + WS:**
- `stores/configUi.ts`: collapse map de los 6 boxes (default todos colapsados).
- `stores/validatorProgress.ts`: alimentado por WS `validator.progress` con runId + tests + lastMessage + finishedAt derivado.
- `api/ws.ts`: dispatch de `validator.progress` reemplaza el no-op anterior.

**3. Componentes UI compartidos:**
- `components/ui/Pilot.tsx` (4 estados con glow).
- `components/ui/Badge.tsx` (6 variantes: default/ok/warn/err/run/pend).
- `components/ui/Toggle.tsx` (on/off con accent Phoenix).
- `components/ui/Dropzone.tsx` (drag-and-drop + file picker).

**4. Pestaña Configuración:**
- `pages/Configuration/Frame.tsx`: contenedor grid 2-col con `::before` línea vertical.
- `pages/Configuration/Box.tsx`: subgrid (col 1: dot button · col 2: head + body) con collapse store.
- `pages/Configuration/configuration.css` (~870 líneas): portado del Hi-Fi v1 standalone con clases prefijadas `cfg-`, +componentes UI (`.btn`, `.field`, `.inp`, `.pg`, `.card`, `.toolbar`, `.note`, `.num`, `.dropzone`).
- `pages/Configuration/boxes/Box1Engines.tsx`: 5 cards (database/data/slot_registry/scoring/validator) + flow lifespan. Lee `useEngineHealth` + `useSlots` + `useValidatorReportLatest`. Aggregate state `levelToState()`/`aggregateState()`.
- `pages/Configuration/boxes/Box2Config.tsx`: 2 cards (acciones · resumen). Load/save/save_as/clear/download via `useConfigCurrent` + 4 mutations. Toast feedback.
- `pages/Configuration/boxes/Box3Keys.tsx`: 5 cards de TD keys con form inline para agregar (4 fields). Probe agregado + individual via `useValidatorConnectivity` filtrado en frontend. Uso live por WS `api_usage.tick` → `useApiUsageStore`. Eliminar via `usePutTdKeys` con keys filtrado.
- `pages/Configuration/boxes/Box4Slots.tsx`: tabla 6 slots (ticker · fixture select nativo · toggle · runtime status). Biblioteca de fixtures + delete. Upload via `Dropzone` + `useUploadFixture`. PATCH /slots/{id} via `usePatchSlot`.
- `pages/Configuration/boxes/Box5Validator.tsx`: grid 7 celdas (D/A/B/C/E/F/G) alimentado por store live o por último reporte. Histórico de reports con cursor pagination. Engines mini compactos. `useValidatorRun` + `useValidatorConnectivity`.
- `pages/Configuration/boxes/Box6S3.tsx`: form 6 fields + listado de backups + 4 acciones (probar / guardar creds en .config / backup / restore). Hidratación inicial del form desde `useConfigCurrent(true)`. Confirm doble en restore.

**5. Tests:**
- `test/router.test.tsx`: 2 tests nuevos (header + 6 boxes con dots, todos colapsados por default). Total 7 tests passing.

Métricas finales del bundle:
- CSS 81.46 KB (gz 15.60)
- JS 341.47 KB (gz 105.38)

**Decisiones / deudas v1 documentadas en commits:**
- Edición fina de cred/min y cred/día de TD keys: queda como deuda (se hace editando .config y volviendo a cargar).
- Edición inline del ticker en Box 4: deshabilitada (cambio en vivo es destructivo).
- Modal de detalle de reporte del Validator: deuda v2.
- Confirmaciones via `window.confirm()` simple (modal pulido v2).
- mini-rep del histórico con 1 dot · no 7 dots desglosados (el endpoint list no devuelve `tests`).

**Sesión 2026-04-30 — cierre de 9/11 deudas técnicas backend (sesión OZyjj):**

**Refactor del módulo `config/` a plaintext (decisión de producto):**
- Borrado `crypto.py` (Fernet + master key flow). El `.config` es un archivo portable que el usuario maneja como un documento. Sin `.config` cargado el sistema arranca de cero — coherente con el modelo histórico del producto ("nada persiste cuando el usuario apaga el scanner; los secretos viven en su `.config`").
- `models.py` agrega `StartupFlags` (override de `Settings` cuando hay `.config` cargado).
- `loader.py` simplificado: save/load JSON plaintext con atomic write.

**KeyPool hot-reload:**
- Nuevo método `async reload(keys)` que reemplaza la configuración preservando contadores runtime (`used_minute`, `used_daily`, etc) de las keys cuyo `key_id` siga en el set nuevo. Wipe best-effort del `secret` de keys eliminadas. Permite que `PUT /config/twelvedata_keys` aplique cambios sin reiniciar el backend.

**10 endpoints REST en `api/routes/config.py`:**
- `POST /config/load` · `/save` · `/save_as` · `/clear` — gestión del `.config` runtime.
- `GET /config/last` (path del último cargado, persistido en `data/last_config_path.json`) · `/current` (UserConfig runtime con secretos redactados por default; `?include_secrets=true` para edición).
- `PUT /config/twelvedata_keys` (con reload del KeyPool) · `/s3` · `/startup_flags`.
- `POST /config/reload-policies` (sync de `db_size_limit_mb` runtime).

**3 endpoints REST en `api/routes/fixtures.py`:**
- `GET /fixtures` — lista los `.json` del `fixtures_dir` con metadata + sha256_status + slots que lo usan.
- `POST /fixtures/upload` — multipart con `.json`. Valida Pydantic + reglas FIX-XXX + `engine_compat_range` ⊇ `ENGINE_VERSION`. 409 si fixture_id duplicado. Persiste `.json` + sibling `.sha256`.
- `DELETE /fixtures/{fixture_id}` — borra `.json` + `.sha256` + `.metrics.json`. 409 si algún slot lo tiene cargado.

**1 endpoint REST adicional en `api/routes/database.py`:**
- `POST /database/vacuum` — bloqueante via `asyncio.to_thread`. Recupera espacio post rotación agresiva. 400 con `:memory:`, 503 si la DB está locked.

**Wiring al lifecycle:**
- `Settings.last_config_path_file` (`data/last_config_path.json`) y `Settings.fixtures_dir` (`fixtures`) nuevos.
- `app.state.{user_config, user_config_path, last_config_path_file, fixtures_dir, key_pool}` expuestos vía `create_app()`.
- `main.py:_try_load_last_config` carga el LAST silenciosamente al arranque si el path apuntado existe; si falla, runtime queda vacío y el usuario carga manualmente.

**Dependencia nueva:** `python-multipart>=0.0.20` en `pyproject.toml` (requerido por `UploadFile` de FastAPI).

**Tests nuevos:** 24 (config route) + 7 (KeyPool reload) + 3 (vacuum) + 16 (fixtures) = **50 tests nuevos**. Suite total: 1118 passing.

Sesión previa 2026-04-29 — **Cockpit funcional + estados degradados + endpoints pause/resume + spec funcional + 2 wireframes mid-fi de Configuración**:

**Backend nuevo:**
- `POST /api/v1/scan/auto/{pause,resume,status}` con `asyncio.Event` en `app.state.auto_scan_running`. El loop bloquea en `await running.wait()` antes del próximo ciclo y emite `engine.status={status:"paused"}` por WS. **6 tests nuevos** en `tests/api/test_scan.py::TestAutoScanPauseResume`. Cierra la deuda histórica del toggle AUTO.

**Frontend nuevo (sesión completa):**
- **5 stores Zustand**: `auth` (persist localStorage), `slots`, `apiUsage`, `signals`, `engine` (con `dataPaused`/`ws`/`stateOverride`), `scanning`.
- **7 TanStack Query hooks**: `useEngineHealth`, `useSlots`, `useLatestSignal`, `useAutoScanStatus`, `useScanManual`, `useAutoScanPause`, `useAutoScanResume`.
- **`useScannerWS()`** con auto-reconnect (backoff 1/2/4/8/16s), dispatch a stores de los 6 eventos del WS. Idempotente.
- **Bearer token UI** compacto en footer con persistencia localStorage + reconexión WS al guardar.
- **Toast system reutilizable** (4 tonos: success/info/warn/error) con context provider montado en `main.tsx`.
- **Reloj y fecha live ET** vía `useSyncExternalStore` (un único `setInterval` global).
- **Botones funcionales**: Copiar (clipboard + fallback execCommand + label dinámico + toast), Scan (mutation `/scan/manual` + feedback 900ms + tracking via `useScanningStore`), Toggle AUTO (cableado a `useAutoScanPause/Resume` + status sync).
- **7 estados del Cockpit** implementados (Hi-Fi v1 portados): `normal · warmup · degraded · splus · error · scanning · loading`. Resolución por prioridad en `useCockpitState()`.
- **Banner del Panel — paquete A "hero"**: iridiscente `conic-gradient(in oklab)` animado 18s + ghost ticker iridiscente text-clip animado 16s reverse + specular sweep diagonal cada 12s + halo cromático tier-aware (`--ticker-halo` por tier B/A/A+/S/S+).
- **Anti-posterización**: dithering SVG turbulence sobre el iridiscente (alpha 0.3, mix-blend overlay) + `conic-gradient(in oklab from ...)` en banner/ghost/bookmarks S y S+/utility plugin + blur backdrop subido un escalón global (12→18, 20→28, 28→36, 16→22).
- **Helper `useEffectiveSlot(id)`** que combina backend + fallback hardcoded del Hi-Fi v2 — fix del bug donde el banner no reaccionaba al cambio de slot sin backend.
- **Bookmark sólo en A/A+/S/S+** (B y REVISAR muestran tier por score numérico, sin bookmark).
- **Reorden de pestañas**: Cockpit · Dashboard · Memento · Configuración. `/` redirige a `/cockpit`.
- **Live indicator** del topbar refleja el estado del WS (live/linking/offline) con color y label.
- **DevStateSwitcher** (deuda técnica): switcher dev-only (botón ⚙ bottom-right, plegable) con 8 estados forzables vía `useEngineStore.stateOverride`. Sólo se monta si `import.meta.env.DEV`. **Anotado para eliminar pre-release 1.**

**Documentación nueva:**
- `frontend/wireframing/Configuracion specs.md` — spec funcional 6 secciones: layout · 5 pasos · apéndice de contratos. Lista 18 endpoints REST + 11 deudas técnicas del backend + 6 eventos WS + matriz hot-reload/reinicio + persistencia local vs backend.
- `frontend/wireframing/Configuracion Wireframes V2.html` — primer mid-fi paper-style alineado al spec (5 boxes).
- `frontend/wireframing/Configuracion Wireframes V3.html` — iteración con feedback del usuario (1354 líneas): 6 boxes · línea-guía vertical izquierda con dots · auto-colapso al quedar OK · Box 1 observabilidad de motores (sin arranque manual) · Box 2 carga/guardado del Config (sin bearer/master/paths) · Box 4 sin columna benchmark · fixture como dropdown · Box 5 sin flags · Box 6 sólo S3 al final.

**Branch de trabajo:** `claude/review-project-status-OZyjj`.

**PR:** abierto al final de la sesión OZyjj con los 4 commits del bloque (refactor config + endpoints config + endpoints vacuum/fixtures + handoff).

**Decisiones cerradas en la sesión OZyjj (2026-04-30):**
1. **`auto_scan_run_at_startup` eliminado del scope** — el sistema arranca con auto-scan activo (decisión 6 del handoff anterior: motores con lifespan, sin arranque manual desde la UI).
2. **`.config` plaintext (decisión A del usuario)** — sin master key, sin Fernet. El `.config` es un archivo portable que el usuario maneja como un documento. Tirado el módulo `crypto.py` y simplificado el `loader.py` plaintext.
3. **`/system/restart` diferido a otro PR** — alto riesgo de testear `os.execv` sin romper el dev server.
4. **`/system/open-folder` descartado v1** — confirmado por la nota en el spec (era opcional).

**Decisiones abiertas para el próximo chat:**
1. **Próximo bloque sugerido** (mismo que el handoff anterior):
   - (a) **Hi-Fi v1 Phoenix de Configuración** sobre el wireframe V3 mid-fi + scaffold React reemplazando el stub. **Ahora el backend está 100% listo para cablear** (excepto `/system/restart` que se difirió).
   - (b) **`POST /system/restart`** en un PR aparte si se considera valioso para v1 (el frontend muestra fallback "ejecutar `python backend/main.py` manualmente" hasta entonces).
   - (c) **Hi-Fi del Dashboard** — sin spec ni wireframe todavía. La persistencia DB + retención que se sacó de Configuración vive acá.
   - (d) **Lightweight Charts** en el panel del Cockpit (reemplaza el SVG estático).
2. **Recomendación:** ir por (a) ahora que el backend está completo. (b) puede esperar — el fallback manual es aceptable para alfa.

Superficie backend disponible para el frontend:

| Método | Path | Notas |
|---|---|---|
| GET | `/api/v1/engine/health` | Piloto del scoring engine con healthcheck status |
| GET | `/api/v1/signals/{latest,history,{id}}` | Histórico transparent op+archive |
| POST | `/api/v1/scan/manual` | Scan on-demand |
| GET | `/api/v1/scan/auto/status` | `{paused: bool}` (NUEVO) |
| POST | `/api/v1/scan/auto/{pause,resume}` | Toggle AUTO (NUEVO) |
| GET/PATCH | `/api/v1/slots`, `/api/v1/slots/{id}` | List + enable/disable + hot-reload warmup |
| POST | `/api/v1/validator/{run,connectivity}` | Batería completa + solo conectividad |
| GET | `/api/v1/validator/reports{,/latest,/{id}}` | Histórico de reportes |
| POST | `/api/v1/database/rotate{,/aggressive}` | Rotación manual + agresiva §9.4 |
| POST | `/api/v1/database/vacuum` | SQLite VACUUM (NUEVO sesión OZyjj) |
| GET | `/api/v1/database/stats` | Contadores + tamaño op + umbrales |
| POST | `/api/v1/database/{backup,restore,backups}` | S3-compat, multi-provider |
| POST | `/api/v1/config/{load,save,save_as,clear}` | Gestión del `.config` runtime (NUEVO sesión OZyjj) |
| GET | `/api/v1/config/{last,current}` | LAST + UserConfig runtime (NUEVO sesión OZyjj) |
| PUT | `/api/v1/config/{twelvedata_keys,s3,startup_flags}` | Edita runtime + reload del KeyPool (NUEVO sesión OZyjj) |
| POST | `/api/v1/config/reload-policies` | Hot-reload de `db_size_limit_mb` (NUEVO sesión OZyjj) |
| GET | `/api/v1/fixtures` | List `.json` con metadata + sha256 + slots usage (NUEVO sesión OZyjj) |
| POST | `/api/v1/fixtures/upload` | Multipart upload + valida engine_compat_range (NUEVO sesión OZyjj) |
| DELETE | `/api/v1/fixtures/{fixture_id}` | Borra `.json` + siblings; 409 si usado (NUEVO sesión OZyjj) |
| GET | `/api/v1/candles/{ticker}?tf=&n=` | Velas para chart del Cockpit (NUEVO PR #49 BUG-022) |
| POST | `/api/v1/scan/slot/{id}` | Scan target por slot · resuelve fixture+candles desde registry/data_engine + broadcast `api_usage.tick` (NUEVO PR #49 BUG-015/021) |
| POST | `/api/v1/system/{shutdown,restart}` | Control del proceso vía launcher · `restart_requested.flag` + signal SIGTERM (NUEVO PR #46) |
| WS | `/ws?token=...` | 6 eventos push |

**Pestañas (estado actual al 2026-05-02):**
1. **Cockpit** — Watchlist + detalle técnico + botón COPIAR con `chat_format` · **completo wired al backend**, 7 estados + bearer + DevStateSwitcher + chart OHLC SVG real (BUG-022).
2. **Dashboard** — stub (10 líneas). Sin spec ni wireframe todavía. Incluirá persistencia DB + retención (sacadas de Configuración).
3. **Memento** — stub (10 líneas). Sin spec.
4. **Configuración** — **wired completo** (sesión OZyjj 2026-04-30 + refinamientos PR #46-#49). 6 boxes operativos (Engines/Config/Keys/Slots/Validator/S3) ~2227 líneas.

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

### 18. Endpoints PUT con secretos: preservar el valor original si el frontend manda `"***"` (masked)

Patrón de UX típico: el frontend muestra los secretos redactados (`***`) en el form de edición. Si el usuario edita otros campos y guarda sin re-pegar el secret, el body llega con `"***"` literal en el campo `secret`/`access_key`/etc.

**Bug original (BUG-029, PR #49):** `config.py:config_put_td_keys` guardaba ese `"***"` como si fuera el nuevo valor → la key real quedaba inválida silenciosamente. El usuario veía la UI confirmando "guardado" pero el probe siguiente fallaba con `invalid_key`.

**Fix obligatorio para cualquier PUT que reciba secrets editables:**

```python
def merge_secret(submitted: str, existing: str | None) -> str | None:
    """Si el frontend manda el sentinel masked, preservar el valor original."""
    MASKED_SENTINELS = {"***", "***REDACTED***", ""}
    if submitted in MASKED_SENTINELS:
        return existing
    return submitted
```

Aplicar en TODOS los endpoints PUT que tomen secrets:
- `PUT /config/twelvedata_keys` (TD secret) — fix aplicado.
- `PUT /config/s3` (access_key + secret_key) — verificar.
- Cualquier endpoint nuevo con `password` / `token` / `api_key` / `secret`.

**Test de regresión obligatorio:**

```python
async def test_put_preserves_secret_when_masked():
    # Setup: PUT con secret real
    await client.put("/config/twelvedata_keys", json=[{"key_id": "k1", "secret": "sk-real", ...}])
    # Edit: PUT con "***" (frontend no recargó el secret)
    await client.put("/config/twelvedata_keys", json=[{"key_id": "k1", "secret": "***", ...}])
    # Verify: el secret real se preservó
    r = await client.get("/config/current?include_secrets=true")
    assert r.json()["twelvedata_keys"][0]["secret"] == "sk-real"  # NO "***"
```

**Lección general:** redactar `***` en GET es seguro; aceptar `***` en PUT es bug. La capa de "ignorar el sentinel" debe vivir en el handler del PUT, no en el frontend (que no es la fuente de verdad).

### 19. `.gitattributes` + Windows autocrlf rompe hash SHA-256 de canonicals

**Bug original (BUG-006, PR #49):** clones en Windows con `core.autocrlf=true` (default) convertían LF→CRLF al checkout de archivos `.json`. El hash SHA-256 calculado por `validate_canonical_hash()` no matcheaba el hash commiteado en el `.sha256` sibling → REG-020 fatal → registry no carga → scan_loop=stub.

**Fix:** `.gitattributes` con `text eol=lf` para `backend/fixtures/**/*.json` y `*.sha256`. Una vez en main, **acción manual obligatoria una sola vez:**

```bash
git add --renormalize .
git commit -m "renormalize line endings post .gitattributes (BUG-006)"
```

`.gitattributes` solo aplica a checkouts futuros. Sin el `--renormalize`, los archivos en el index quedan con CRLF y el bug persiste para clones nuevos.

**Cuándo aplicar este patrón:**
- Cualquier archivo binario-en-text (hashes, parquet, .npy, etc) que el repo trackea como text.
- Cualquier `.json` cuyo SHA se valida contra un sibling `.sha256`.
- Cualquier dataset commiteado donde la byte-equality importa.

**Cómo detectar el bug en futuros canonicals:**
- Desktop Linux/Mac: nunca aparece (autocrlf=input).
- Windows: aparece la primera vez que el clone se usa para arrancar el backend.
- CI Linux: aparece solo si el CI corre en Windows.

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

- **Todo desarrollo:** branch designada de la sesión (ej. `claude/plan-feature-development-qh7yJ`). Nunca push directo a main.
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
6. Correr los tests antes de tocar nada para verificar baseline verde (**1132 passing esperados** + 1 slow parity guard, post PR #49).
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
