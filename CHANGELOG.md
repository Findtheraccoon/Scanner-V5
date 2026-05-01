# Changelog

Todos los cambios relevantes del proyecto Scanner-v5 se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

Nótese que este changelog versiona al **scanner como producto** (ej. `v0.1.0 → v0.2.0`). Los componentes internos (Scoring Engine, schema de fixtures, Slot Registry, Canonical Manager) mantienen sus propias cadenas semver independientes, tal como lo define `FEATURE_DECISIONS.md §2.6`.

---

## [Unreleased]

### Added

- Bootstrap inicial del repo.
- Estructura de carpetas según `FEATURE_DECISIONS.md §5.4`.
- Sistema de documentación en 4 niveles (ver `README.md`).
- 7 ADRs retroactivos (`docs/adr/0001` a `docs/adr/0007`) que consolidan las decisiones tomadas durante la sesión de diseño 19–20 abril 2026.
- Templates de GitHub para PRs y issues.
- Convenciones de commits (`CONTRIBUTING.md`).
- Template base para ADRs futuros (`docs/adr/0000-template.md`).

### Changed

- N/A.

### Fixed

- **BUG-004** · Orden de bootstrap registry vs scan_loop. `_build_scan_loop_factory` corría
  antes que `_bootstrap_registry_runtime`, así que un clone fresco con
  `SCANNER_TWELVEDATA_KEYS` en env var fallaba con REG-001 (file not found) y caía a
  `scan_loop=stub`, aunque las keys fueran válidas. Ahora `_ensure_registry_file` corre
  primero — el log subsecuente muestra el motivo real (REG-003 si no hay slots
  operativos, o load OK si los hay). `backend/main.py:main` (`_ensure_registry_file`
  invocado pre-`_build_scan_loop_factory`).
- **BUG-005** · `GET /api/v1/fixtures` 500 — `AttributeError: 'SlotRegistry' object has no
  attribute 'snapshot'`. `_slots_using_fixture` llamaba un método inexistente; reemplazado
  por iteración directa sobre `runtime._registry.slots` (Pydantic `frozen=True`, lectura
  sync segura). Desbloquea Configuración Box 4 (lista + dropdown de fixtures).
  `backend/api/routes/fixtures.py:_slots_using_fixture`.
- **BUG-006** · Hash mismatch de canonicals en clones Windows. `core.autocrlf=true`
  convertía LF→CRLF al checkout y rompía el SHA-256 del canonical, disparando REG-020 y
  bloqueando scan_loop + registry. Agregado `.gitattributes` con `text eol=lf` para
  `backend/fixtures/**`. **Acción requerida tras merge:** ejecutar `git add --renormalize .`
  + commit del re-normalize una vez que el `.gitattributes` esté en main para alinear
  los archivos en el index.
- **BUG-007** · Registry runtime ahora degrada gracefully ante `RegistryError`. Antes,
  cualquier fallo en `load_registry` (REG-002 schema, REG-020 hash mismatch, REG-030
  engine version) dejaba `app.state.registry_runtime = None` y todos los endpoints
  `/slots` y `/fixtures` respondían 503. Ahora se construye un `SlotRegistry` synthetic
  in-memory con 6 slots DISABLED y se publica como runtime; el archivo en disco se
  conserva intacto para debugging. `backend/main.py:_build_empty_registry` +
  `_bootstrap_registry_runtime`.
- **BUG-008** · `GET /api/v1/engine/health` ahora incluye `registry_load_error` cuando
  el bootstrap del registry usó el fallback in-memory. La UI puede mostrar el motivo
  exacto del problema (ej. "REG-020: canonical hash mismatch...") en vez de quedarse
  con un registry vacío sin explicación. `backend/api/routes/health.py:engine_health`.
- **BUG-009** · `DatabaseStatsResponse` (frontend types) no matcheaba la respuesta
  real del backend (`{tables: dict[str, table_stats]}` vs declarado
  `{tables: {operative:[], archive:[]}}`). El hook `useDatabaseStats` no estaba
  consumido en ninguna view, así que el bug era contract latente — corregido para
  prevenir regresión silenciosa cuando se implemente el panel de DB stats.
  `frontend/src/api/types.ts:DatabaseStatsResponse`.
- **BUG-010** · `Box4Slots` mandaba `fixture_id` ("qqq_canonical_v1") al backend
  en `PATCH /slots/{id}` body, pero el backend espera `fixture` = path relativo
  ("fixtures/qqq_canonical_v1.json"). Resultado: error FIX-000 al intentar
  habilitar un slot desde la UI con cualquier canonical (incluyendo el bootstrap
  QQQ). Fix: dropdown options ahora usan `value=f.path` (display sigue mostrando
  el `fixture_id`); `fixtureDraft` mantiene el path; preselección viene de
  `slot.fixture_path` (ver BUG-011 sobre el adapter).
  `frontend/src/pages/Configuration/boxes/Box4Slots.tsx`.
- **BUG-011** · El backend serializa `/slots` con campos `slot` (no `slot_id`),
  `fixture_path`, `base_state`, pero el `SlotInfo` del frontend declaraba
  `slot_id` + `enabled` + sin `fixture_path`. Toda la UI (Cockpit Watchlist,
  Box4 SlotCard) leía `slot.slot_id === undefined` y `slot.enabled === undefined`.
  Fix: introducido `RawSlotInfo` que matchea el shape del backend + adapter
  `adaptSlot()` en `useSlots()` que normaliza al `SlotInfo` que la UI consume.
  `frontend/src/api/{types,queries}.ts`.
- **BUG-012** · Como consecuencia de BUG-011, `slot.enabled` era siempre
  `undefined` → toggle nunca reflejaba el estado real, `editingDisabled` era
  siempre `false`, y el `is-disabled` CSS class no se aplicaba. Fix: el adapter
  deriva `enabled = base_state !== "DISABLED"` desde la respuesta cruda.
  `frontend/src/api/queries.ts:adaptSlot`.
- **BUG-013** · `PATCH /slots/{id}` rechazaba con `REG-013: fixture declara
  benchmark "SPY" pero el slot pide None` cuando la UI hacía el toggle ON sin
  campo `benchmark` en el body. Box 4 nunca expone benchmark al usuario porque
  el design dice "benchmark lo define el fixture", pero la validación strict
  trataba `benchmark=None` como "el slot pide None" y fallaba contra cualquier
  fixture que declarara uno. Fix: en `RegistryRuntime.enable_slot`, si el
  caller no especifica `benchmark`, se autollena desde
  `fixture.ticker_info.benchmark` antes de validar. Si el caller manda un
  valor explícito que no matchea, REG-013 sigue saltando como antes.
  `backend/engines/registry_runtime.py:enable_slot` + test
  `tests/engines/test_registry_runtime.py::test_enable_autofills_benchmark_from_fixture`.
- **BUG-014** · El botón "reiniciar backend" en Box 1 dispara `POST /system/restart`
  que envía SIGINT al proceso esperando que un launcher externo
  (`backend/launcher.py`) lo relance. En modo dev (`python main.py` directo)
  no hay launcher → el backend muere permanentemente y la UI no avisa al
  usuario. Fix: el launcher ahora setea `SCANNER_LAUNCHER_PID` env var antes
  de importar main; `/engine/health` lo lee y expone `launcher_attached: bool`;
  `Box1Engines.tsx` usa el flag para cambiar el label del botón a
  "reiniciar (modo dev)" + tooltip explicativo, y el `confirm()` advierte
  que el proceso NO se relanzará solo. `backend/launcher.py:setup_env` +
  `backend/api/routes/health.py:engine_health` +
  `frontend/src/pages/Configuration/boxes/Box1Engines.tsx:onRestart`.
- **BUG-017** · `useLatestSignal` trataba la respuesta de `GET /signals/latest`
  como un objeto único (`SignalPayload | null`) cuando el backend devuelve
  `list[dict]` (array). `applySignal(latestQuery.data)` recibía el array,
  `array.slot_id` era `undefined`, y el store `useSignalsStore.bySlot`
  nunca se poblaba — el Banner del Cockpit se quedaba en "ESPERANDO SEÑAL"
  para siempre aunque hubiera signals reales en DB. Fix: `queryFn` retorna
  `items[0]` (el endpoint ya viene ordenado DESC LIMIT 1).
  `frontend/src/api/queries.ts:useLatestSignal`.
- **BUG-031** · La probabilidad (% WR) del backtest training del canonical
  ya estaba inyectada en el signal payload (BUG-023) pero la presentación
  era poco visible: en watchlist aparecía sólo el número (`55%`) sin label
  y en el Cockpit Panel no aparecía. Mejoras:
  1. **Watchlist** (`Slot.tsx`): el WR ahora se renderiza con sufijo
     `prob` (ej. `55% prob`) y `title` con tooltip que explica
     "WR @ banda · backtest training del canonical".
  2. **Cockpit Exec block** (`Panel.tsx`): nuevo chip "probabilidad"
     como primer chip del grid, mostrando `wr_pct% @ band` (ej.
     `54.9% @ A`). Para signals NEUTRAL/blocked sin banda asignada,
     muestra `—` (no hay WR para "sin setup").
  Verificado: el chip aparece junto a ALINEACIÓN/ATR 15M/VELA/etc.
  con valor `—` cuando conf=`—` y con valor real cuando hay banda.
  `frontend/src/pages/Cockpit/{Slot,Panel}.tsx`.
- **BUG-030** · El chart del Cockpit (BUG-022) no refrescaba tras un
  scan manual ni tras `signal.new` del auto-loop. `useScanSlot.onSettled`
  invalidaba `["signals.latest", slotId]` pero no `["candles"]`, así
  que la query de candles seguía sirviendo cache hasta el `staleTime`
  (10s) o hasta el próximo refetch automático. Resultado: el usuario
  hacía scan, veía el banner actualizado pero el chart "se quedaba"
  con las mismas velas. Fix:
  1. `useScanSlot.onSettled` ahora hace `qc.invalidateQueries({queryKey:
     ["candles"]})` después del scan — la query family completa se
     marca stale y refetchea inmediatamente.
  2. WS dispatcher de `signal.new` también invalida `["candles"]` —
     cuando el auto-scan loop completa un ciclo y persiste velas
     nuevas en DB, el chart se actualiza sin esperar polling.
  Verificado: 1 request a `/candles/QQQ` al cargar el Cockpit, +1
  request adicional cada vez que clickeás SCAN AHORA. La query
  refetchea correctamente; el DOM no cambia visualmente solo cuando
  no hay candles nuevas que traer (after-hours / entre boundaries 15m).
  `frontend/src/api/queries.ts:useScanSlot` +
  `frontend/src/api/ws.ts:dispatch`.
- **BUG-029** · 🎯 **Causa raíz del "una key OK, otra 401"** reportado al
  agregar 2 keys reales. Mecánica del bug:
  1. `GET /config/current` enmascara secrets con `_REDACTED = "***"` por
     seguridad — el frontend nunca tiene los secretos reales en memoria.
  2. Cuando el usuario agrega una nueva key (slot 2..5), el frontend
     hace `PUT /config/twelvedata_keys` con la lista completa: las
     entries previas con `secret: "***"` (los masked que recibió en el
     GET) + la nueva entry con su secret real.
  3. El handler PUT antes hacía `model_copy(update={"twelvedata_keys": req.twelvedata_keys})`
     sin distinguir secretos masked de reales, así que el `"***"` se
     persistía como secret real → la key vieja quedaba inválida.
  4. Al probar, TD rechazaba el `"***"` con 401 "**apikey** parameter is
     incorrect", el frontend marcaba esa key como FAIL.
  Síntoma observado por el usuario: "key 1 OK, agregás key 2, key 1
  pasa a 401 invalid_key". El usuario creía tener 4 secretos malos
  cuando en realidad eran masked overwriteados por el flujo.
  Fix: el PUT detecta `secret == _REDACTED` para entries cuyo `key_id`
  ya existe en runtime, y preserva el secret original. La response
  ahora incluye `preserved_redacted: int` para diagnostico.
  Verificado E2E: Key 1 con secret real → GET masked → PUT con Key 1
  masked + Key 2 nueva → Key 1 mantiene secret real `6213e4f9...a047`
  (len=32), probe ok=True; Key 2 con su secret propio. Antes del fix
  Key 1 quedaba con secret `"***"` (len=3) → 401.
  `backend/api/routes/config.py:config_put_td_keys`.
- **BUG-028** · Hardening preventivo del probe sequencial cuando el usuario
  configura múltiples TD keys (hasta 5 round-robin). Reportado: con keys
  reales de cuentas distintas, primera daba OK y siguientes daban 401.
  Aunque la causa raíz era casi siempre typos en los secretos (TD acepta
  solo 32 chars hex exactos), endurecimos el probe para descartar:
  1. **`test_key_diag`** ahora abre un `httpx.AsyncClient` fresh por
     llamada (en vez de compartir el cliente con el TwelveDataClient
     general) — descarta state leak / connection-pool sharing entre
     keys consecutivas.
  2. **`build_td_probe`** agrega un `asyncio.sleep(0.2)` entre keys
     consecutivas — descarta que TD anti-abuse marque N apikeys
     distintas desde la misma IP en milisegundos como sospechoso.
  Verificado: probe con 5 entries (mismo secret real válido) →
  todas devuelven `ok: true · pass`. Confirma que el scanner no
  introduce el 401, sino que TD lo emite cuando el secret es
  inválido en su lado.
  `backend/engines/data/fetcher.py:test_key_diag` +
  `backend/engines/data/probes.py:build_td_probe`.
- **BUG-027** · Cuando el usuario clickeaba "probar" en una key específica
  (botón individual de la card), el frontend solo actualizaba el badge
  de esa key — las demás cards quedaban en "no probada" aunque el
  backend SIEMPRE prueba todas las keys (Check G itera el `td_probe`
  completo y devuelve resultados de todas). Resultado: tras probar k1,
  k2 quedaba con badge "no probada" hasta clickear "probar todas".
  Fix: `Box3Keys.onProbeOne` ahora hace spread de TODOS los resultados
  del response en `probeResults`, no solo de la key clickeada.
  Verificado: click "probar" en k1 → ambas badges actualizan
  (`k1: ok`, `k2: fail · invalid_key (TD code 401)`).
  `frontend/src/pages/Configuration/boxes/Box3Keys.tsx:onProbeOne`.
- **BUG-026 cierre real** · El classifier de `test_key_diag` no detectaba
  el formato real del error TD. TD responde con HTTP 200 + body
  `{"code": 401, "message": "**apikey** parameter is incorrect...",
  "status": "error"}`. El classifier original buscaba `"api key"` (con
  espacio) en el message — pero TD usa `"apikey"` (una palabra) con
  markdown bold, así no matcheaba y caía al genérico
  `td_error: <message>`. Fix: priorizar `payload.get("code") == 401/429`
  cuando viene en el body (señal más confiable que el HTTP status), +
  agregar `"apikey"` y `"credentials"` al substring match.
  `backend/engines/data/fetcher.py:test_key_diag`.
- **BUG-026** · El probe de TD keys (`POST /validator/connectivity`)
  reportaba sólo `ok: false` cuando una key fallaba — el usuario que
  agregaba 2 keys y veía una en FAIL no tenía cómo saber el motivo
  (key inválida vs rate-limit vs network vs HTTP error). Fix: nuevo
  método `TwelveDataClient.test_key_diag()` que retorna
  `(ok: bool, reason: str | None)` clasificando el fallo:
  `rate_limit (429)`, `invalid_key (401)`, `http_<code>`, `network: <type>`,
  `malformed_response`, `td_error: <message>`. `engines/data/probes.py`
  inyecta `reason` en el campo `error` del payload de Check G. El
  toast del frontend (`Box3Keys.onProbeOne`) ya consume `found.error`
  → ahora muestra `k2 · fail · invalid_key` en vez de `k2 · fail · ?`.
  Verificado: PUT 2 keys (una real, una con secret inválido) →
  `[{key_id:k1, ok:true}, {key_id:k2, ok:false, error:"invalid_key"}]`.
  `backend/engines/data/fetcher.py:test_key_diag` +
  `backend/engines/data/probes.py:build_td_probe`.
- **BUG-025** · El componente `Panel.Exec` del Cockpit (resumen
  ejecutivo · 6 chips: alineación, ATR 15M, vela, resistencias,
  soportes, vol mediana) hardcodeaba `—` aunque hubiera signal
  cargada. Comentario en el código decía "esperando que el backend
  estructure layers para consumo del frontend", pero el backend ya
  devolvía todo lo necesario en `signal.layers.alignment`,
  `signal.layers.trends`, `signal.ind.{price,bb_1h,bb_daily,atr_15m,gap_info}`.
  Fix: leer `signal` del store y mapear cada chip al campo correcto:
  - precio → `ind.price` (con $X.YY format)
  - alineación → `layers.alignment.{n}/3 {dir}`
  - atr 15M → `ind.atr_15m` (`pct% ($abs)`)
  - vela → `ind.gap_info.gap_pct`
  - resistencias / soportes → `ind.bb_1h[0]` / `[2]`
  - vol mediana → `ind.gap_info.vol_x`
  Cada chip degrada a `—` individualmente cuando el campo falta
  (caso BLOCKED/NEUTRAL donde el motor solo provee price).
  Verificado: tras un scan, panel muestra "ÚLTIMO $675.01" +
  "ALINEACIÓN 3/3 BULLISH" en vez de todo en `—`.
  `frontend/src/pages/Cockpit/Panel.tsx:Exec`.
- **BUG-024** · El botón COPIAR del Banner del Cockpit copiaba al
  portapapeles valores fake (`SEÑAL · QQQ · A+ · CALL · score 12.0 ·
  Último: $485.32 · …`) cuando la signal venía sin `chat_format`. Causa:
  el backend solo generaba `chat_format` para el broadcast WS
  `signal.new`, no se persistía en DB; las signals leídas vía
  `/signals/latest` no lo traían, así el frontend caía al
  `CHAT_FORMAT_FALLBACK` que era hardcoded del Hi-Fi v2 con valores
  inventados (485.32, MAs, BB, etc.) que **no tenían relación con la
  realidad del mercado**. Fix:
  1. Backend `_augment_signal` (en `api/routes/signals.py`) regenera
     `chat_format` desde el signal dict en read time vía
     `build_chat_format(sig, candle_timestamp)`. Aplica a /latest,
     /history y /{id}.
  2. Frontend `chatFormat.ts` reemplaza el fallback hardcoded con un
     mensaje honesto "SIN SEÑAL CARGADA · dispará un scan…".
  3. **Cierre real (2da iteración)**: el chat_format inicial mostraba
     `False` (raw bool del campo `signal`) y `Blocked: True` (sin
     motivo). Reescrito `build_chat_format` con bloques claros:
     - HEADER con label legible (SETUP / REVISAR / NEUTRAL / BLOQUEADO).
     - PRECIO  $X.YY (last close 15m enriquecido de DB cuando `ind`
       viene vacío — caso BLOQUEADO/NEUTRAL — para que el usuario
       compare con su gráfico real).
     - BLOQUEO con `conflicto put/call: PUT X vs CALL Y · diff Z`
       desde `layers.risk.conflictInfo`.
     - CONTEXTO + Trends, TRIGGERS, CONFIRMS, RIESGOS no bloqueantes.
     - Meta footer con fixture + engine version.
     `_augment_signal` ahora es async y lee la última candle 15m de
     DB para inyectar `ind.price` cuando no estaba.
  Verificado: clipboard trae `[QQQ] CALL · score 0.0 (—) · BLOQUEADO ·
  PRECIO $674.91 · BLOQUEO conflicto put/call PUT 3.0 vs CALL 4.7 ·
  TRIGGERS Doble techo $675.96, Doble piso $673.34 ·
  Fixture qqq_canonical_v1 v5.2.0`. Coherente: precio 674.91 entre
  soporte 673.34 y resistencia 675.96; bloqueo por conflict balanceado.
  `backend/api/routes/signals.py:_augment_signal` +
  `backend/modules/signal_pipeline/pipeline.py:build_chat_format` +
  `frontend/src/lib/chatFormat.ts`.
- **BUG-023** · La Watchlist no mostraba el % de WR (win-rate) cuando
  el slot tenía un setup. Causa: `Watchlist.buildSlotData` hardcodeaba
  `winRate: null` aunque `Slot.tsx:80` tenía el render `<span>{wr}%</span>`
  listo. La métrica vive en `<fixture>.metrics.json:metrics_training.by_band[BAND].wr_pct`
  (ej. para QQQ band A → 54.9%). Fix:
  1. Nuevo módulo `backend/modules/fixtures/metrics_lookup.py` con
     `get_band_wr_pct(fixtures_dir, fixture_id, band)` + cache LRU.
  2. `_augment_signal` en `api/routes/signals.py` inyecta
     `wr_pct: float | null` en cada signal del response.
  3. Frontend `SignalPayload.wr_pct` + `Watchlist.buildSlotData` ahora
     mapea `winRate: Math.round(sig.wr_pct)` cuando viene.
  Verificado: slot 01 con QQQ band A muestra `9.0 · 55%`.
  `backend/modules/fixtures/metrics_lookup.py` (nuevo) +
  `backend/api/routes/signals.py:_augment_signal` +
  `frontend/src/api/types.ts:SignalPayload` +
  `frontend/src/pages/Cockpit/Watchlist.tsx:buildSlotData`.
- **BUG-022** · El componente `Panel.Chart` del Cockpit era un stub
  permanente con texto "sin datos / datos del chart pendientes" — la
  Lightweight Charts integration estaba documentada como deuda técnica
  (`Watchlist.tsx:11-12`). Quick-win: render OHLC SVG inline desde las
  últimas 50 velas 15m del slot seleccionado. Cambios:
  1. Backend: nuevo endpoint `GET /api/v1/candles/{ticker}?tf=&n=`
     (`backend/api/routes/candles.py`) que lee `read_candles_window` con
     transparent-reads sobre op + archive. Wired en `api/app.py`.
  2. Frontend types: `Candle` y `CandlesResponse` en `api/types.ts`.
  3. Frontend hook: `useCandles(ticker, tf, n)` en `api/queries.ts`
     con `staleTime: 10s`.
  4. Frontend Chart: `Panel.Chart` re-implementado para renderizar
     velas reales — bodies + wicks (verde alcista / rojo bajista) +
     línea de cierres overlay + 5 etiquetas en eje Y. Si no hay datos
     muestra placeholder informativo ("cargando velas…", "sin datos ·
     dispará un scan", etc.).
  Verificado: chart muestra 50 velas QQQ 15m con precio actual 673.57,
  rango 657.56–675.96, trend visible. La integración completa con
  Lightweight Charts queda pendiente para iteración futura (sparkline
  cubre el caso visual mínimo).
  `backend/api/routes/candles.py` (nuevo) +
  `backend/api/app.py` (wire) +
  `frontend/src/api/{types,queries}.ts` +
  `frontend/src/pages/Cockpit/Panel.tsx:Chart`.
- **BUG-021** · El scan manual (`POST /scan/slot/{id}`) no emitía
  `api_usage.tick` por WS — el strip de 5 barras del Cockpit (que muestra
  el consumo por key del KeyPool) se quedaba mudo aunque el scan hubiera
  consumido credits de TwelveData. El usuario no tenía evidencia visual
  de que TD había sido llamado. Fix:
  1. Promovido `_broadcast_api_usage` → `broadcast_api_usage` (público)
     en `engines/data/scan_loop.py`.
  2. `/scan/slot/{id}` lo invoca tras `scan_and_emit` (path OK) y también
     en el path 502 (fetch fail) — los intentos fallidos consumen credits
     igual y deben mostrarse en la UI.
  3. La response del endpoint incluye ahora un objeto `fetch_meta` con
     `{fetched_at, candles_daily_n, candles_1h_n, candles_15m_n}` para
     que la UI muestre cuántas velas se trajeron.
  4. El toast de `ApiBar.handleScan` ahora reporta:
     `scan QQQ (slot 1) · A+ CALL 11.1 · 210D/80H/50m`. Antes era el
     genérico "scan disparado".
  Verificado en vivo: tras click SCAN AHORA, apibar transiciona de
  "K1 · — · 0/8" a "K1 · ahora · 4/8" + 8/800 daily.
  `backend/api/routes/scan.py:scan_slot` +
  `backend/engines/data/scan_loop.py:broadcast_api_usage` +
  `frontend/src/components/AppShell/ApiBar.tsx:handleScan`.
- **BUG-020** · Slots quedaban perpetuamente en `warming_up` en la UI (Box 4
  SlotCard) aunque el backend hubiera transicionado a `active`. El backend
  emitía correctamente el evento WS `slot.status` con `status: "active"`
  tras `mark_warmed`, y el handler actualizaba el zustand store
  `useSlotsStore`, pero `Box4Slots` lee de `useSlots()` (TanStack Query con
  `staleTime: 30s`-`60s`) — la query cache no se invalidaba con el evento
  WS, así el componente seguía pintando el estado viejo hasta el próximo
  refetch automático. El Cockpit Watchlist sí mostraba el cambio porque
  lee del store. Fix: el dispatcher WS de `slot.status` ahora también
  llama `queryClient.invalidateQueries({queryKey: ["slots"]})`. Para que
  esto sea posible fuera de hooks, se extrajo el `queryClient` a
  `frontend/src/api/queryClient.ts` (singleton) que importan tanto
  `main.tsx` como `ws.ts`. Verificado: secuencia `disabled → warming_up
  → active` completa en <500ms en lugar de quedar atascado.
  `frontend/src/api/{queryClient,ws,main}.tsx`.
- **BUG-019** · El botón "SCAN AHORA" del ApiBar fallaba sistemáticamente con
  HTTP 409 ("Slot 2 no está scaneable") cuando el usuario tenía solo slot 1
  operativo. Causa: el `selectedSlotId` default es `2` (legacy del Hi-Fi v2
  donde el segundo slot estaba resaltado), así que el botón pegaba al
  endpoint `/scan/slot/2` aunque slot 2 estuviera DISABLED. El usuario lo
  percibía como "necesita todos los slots activos". Fix:
  1. `AppShell.useBackendWiring` ahora auto-selecciona el primer slot
     operativo (active/warming_up) cuando los slots cargan y el seleccionado
     no es operativo. Cockpit abre directo en el slot que tiene datos.
  2. `ApiBar.handleScan` agrega `resolveScannableSlot()` que respeta el
     seleccionado si es operativo, sino fallback al primer operativo, sino
     toast claro "no hay slots operativos · habilitá uno en Configuración
     Box 4". Toast de éxito incluye el ticker + slot_id que se scaneó.
  `frontend/src/components/AppShell/{AppShell,ApiBar}.tsx`.
- **BUG-018** · `Panel.Banner` crasheaba con `TypeError: label.toLowerCase
  is not a function` cuando había una signal cargada. Causa: el campo
  `signal.signal` en el backend es **boolean** (¿se emitió señal?), no
  string. El frontend lo tipaba como `SignalLabel` ("SETUP"|"REVISAR"|"NEUTRAL")
  y hacía `.toLowerCase()`. Fix: tipo corregido a `boolean`; la etiqueta
  visible se deriva en el componente desde `conf` (`"—"` → NEUTRAL,
  `"REVISAR"` → REVISAR, otras → SETUP). También se agregó `"—"` al union
  de `SignalConfidence` (el backend lo usa para signals NEUTRAL).
  `frontend/src/api/types.ts:{SignalPayload,ScanManualResponse,SignalConfidence}` +
  `frontend/src/pages/Cockpit/Panel.tsx:Banner`.
- **BUG-016** · El auto-scan loop arrancaba en estado `running` (set) por
  default → consumía TD credits desde el primer segundo aunque el usuario
  no lo hubiera pedido. En keys con cupo limitado (free tier 800 cpd / 8 cpm)
  se agotaban en minutos y los scans manuales subsecuentes fallaban con 502.
  Fix: `running = asyncio.Event()` se queda **clear** al arrancar — el loop
  bloquea en `running.wait()` hasta que el usuario active el toggle AUTO
  del Cockpit (`POST /scan/auto/resume`). `backend/main.py:main` línea ~538.
- **BUG-015** · El botón "scan" del Cockpit (`ApiBar.tsx:handleScan`) pegaba
  `POST /scan/manual` con body vacío y siempre devolvía 422 ("scan manual
  requiere body completo") porque ese endpoint exige ticker + fixture +
  3 series de candles + timestamp. Fix: nuevo endpoint
  `POST /scan/slot/{slot_id}` que resuelve fixture y candles del slot del
  registry + data_engine (mismo path que el auto_scan_loop). El frontend
  agrega `useScanSlot()` y lo invoca cuando hay `selectedSlotId` en la
  watchlist; sin slot seleccionado avisa "seleccioná un slot operativo".
  Errores específicos: 404 slot inexistente, 409 slot disabled/degraded,
  503 sin data_engine, 502 fetch falló.
  `backend/api/routes/scan.py:scan_slot` + `frontend/src/api/queries.ts:useScanSlot` +
  `frontend/src/components/AppShell/ApiBar.tsx:handleScan`. Tests:
  `tests/api/test_scan.py::TestScanSlotBug015`.

### Removed

- N/A.

---

## Historial

### Componentes previos al arranque del repo

Las decisiones de arquitectura se tomaron en sesiones de diseño previas al primer commit. Se listan acá para trazabilidad, pero el código aún no existe.

| Componente | Versión diseñada | Notas |
|---|---|---|
| Scoring Engine | 5.2.0 | Contrato inmutable; ver `docs/specs/SCORING_ENGINE_SPEC.md` cuando se sincronice |
| Schema de fixtures | 5.0.0 | Ver `docs/specs/FIXTURE_SPEC.md` |
| Slot Registry | 1.0.0 | 6 slots fijos, hot-reload habilitado (desvío del spec original) |
| Canonical Manager | 1.0.0 | Vive solo en Observatory; scanner no lo aloja |
| FEATURE_DECISIONS.md | 1.1.0 | Última sesión: barrido backend + cierre Cockpit (20 abril 2026) |
| FRONTEND_FOR_DESIGNER.md | 2.0.0 | Cerrado tras decisión estética W |

---

## Convenciones de entradas

Cada release estable incluye:

```
## [X.Y.Z] - YYYY-MM-DD

### Added
- Funcionalidad nueva (lleva entrada por cada feature externa).

### Changed
- Cambio en funcionalidad existente.

### Deprecated
- Funcionalidad que se va a remover en próximos releases.

### Removed
- Funcionalidad removida (coincide con un MAJOR bump según semver).

### Fixed
- Bug fixes.

### Security
- Correcciones relacionadas con seguridad.
```

Entradas bajo `findtheracoon` se acumulan entre releases y se renombran al publicar.

---

## Links

[Unreleased]: https://github.com/REEMPLAZAR_ORG/Scanner-v5/compare/v0.1.0...HEAD
