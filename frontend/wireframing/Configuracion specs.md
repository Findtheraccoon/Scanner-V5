# Pestaña Configuración — spec funcional

> **Alcance:** este documento describe **qué hace** la pestaña Configuración del frontend del Scanner v5 y **cómo se distribuyen los bloques funcionales** que la componen. No incluye nada visual (colores, tipografías, espaciados, animaciones, layout pixel-perfect). Eso se decide después en el wireframing hi-fi.
>
> **Audiencia:** diseñador (para armar wireframes con la información correcta) e implementador del frontend (para saber qué endpoints / eventos / inputs cablear).
>
> **Referencias:**
> - `docs/specs/SCANNER_V5_FEATURE_DECISIONS.md` §6 — las 4 pestañas en detalle.
> - `docs/operational/FRONTEND_FOR_DESIGNER.md` v2.0.0 — briefing visual del producto.
> - `backend/api/routes/*.py` — endpoints disponibles.
> - `backend/settings.py` — variables de entorno reconocidas por el backend.

---

## 0. Layout general

La pestaña se compone de **5 pasos verticales apilados**, cada uno autosuficiente y con guardado independiente. El orden refleja la secuencia natural de set-up de un usuario nuevo:

| # | Paso | Resumen funcional |
|---|---|---|
| 1 | **Identidad y persistencia local** | Bearer token de acceso a la API · master key Fernet para encriptar secretos · paths del sistema (DB, archive, logs, registry). |
| 2 | **Proveedor de datos** | Configuración de las 5 API keys de TwelveData (key_id, secret, capacidades por minuto y diarias) · probe de conectividad por key y agregado. |
| 3 | **Slot Registry + fixtures** | Asignación de tickers, fixtures y benchmarks a los 6 slots · upload y validación de fixtures · enable/disable individual con hot-reload. |
| 4 | **Persistencia, backup y retención** | Stats de DB · backup remoto a S3-compatible · restore · rotación normal y agresiva · políticas de tamaño máximo. |
| 5 | **Arranque y diagnóstico** | Validator (batería completa o conectividad) · histórico de reportes · flags de arranque · heartbeat · auto-scan al iniciar. |

**Comportamiento general de cada paso:**

- Cada paso es **colapsable** (expande al click; el estado por default es expandido al primer arranque y colapsado en sesiones siguientes).
- Cada paso muestra un **indicador de estado** en su cabecera (configurado / incompleto / con error / probando) para que el usuario vea de un vistazo qué falta sin tener que abrirlos.
- Cada paso con cambios sin guardar muestra un indicador "modificado" en su cabecera.
- Los pasos no son secuencialmente bloqueantes en la UI (se puede saltar al 4 sin haber completado el 2), pero el backend rechaza acciones que requieren prerrequisitos: por ejemplo, "probar key" del Paso 2 sin bearer del Paso 1 → toast "configurar bearer primero".
- El bearer del Paso 1 se autopuebla con el valor que ya esté guardado en `localStorage` (tomado del input compacto del footer del shell).

**Botón global "guardar todo"** al final del Paso 5: aplica los cambios pendientes de los 5 pasos en orden, mostrando feedback por paso. Útil cuando el usuario tocó cosas en varios pasos y quiere persistir todo de una vez. Si alguno falla, se detiene y reporta cuál.

---

## 0.1 Endpoints REST consumidos por la pestaña

| Método | Path | Origen | Uso |
|---|---|---|---|
| `GET` | `/api/v1/engine/health` | Paso 5 | piloto + healthcheck del scoring engine |
| `GET` | `/api/v1/slots` | Paso 3 | lista de los 6 slots con su estado runtime |
| `PATCH` | `/api/v1/slots/{id}` | Paso 3 | enable/disable + cambio de ticker/fixture |
| `POST` | `/api/v1/validator/run` | Paso 5 | dispara batería completa A/B/C/D/E/F/G |
| `POST` | `/api/v1/validator/connectivity` | Paso 2 | probe de las TD keys + S3 |
| `GET` | `/api/v1/validator/reports` | Paso 5 | histórico de reportes con cursor |
| `GET` | `/api/v1/validator/reports/latest` | Paso 5 | último reporte (carga inicial del paso) |
| `GET` | `/api/v1/validator/reports/{id}` | Paso 5 | detalle de un reporte específico |
| `GET` | `/api/v1/database/stats` | Paso 4 | filas op + archive + tamaño + size limit |
| `POST` | `/api/v1/database/rotate` | Paso 4 | rotación normal manual |
| `POST` | `/api/v1/database/rotate/aggressive` | Paso 4 | rotación agresiva (§9.4) |
| `POST` | `/api/v1/database/backup` | Paso 4 | backup S3 (credenciales en body por compat) |
| `POST` | `/api/v1/database/restore` | Paso 4 | restore S3 |
| `POST` | `/api/v1/database/backups` | Paso 4 | lista los backups disponibles en S3 |

**Notas:**
- Todos los endpoints requieren bearer token (Paso 1).
- Endpoints de credenciales sensibles (S3, restore) viajan por body — la deuda técnica del módulo `config/` encriptado los reemplazará por una referencia a la config persistida cuando se cablee.

## 0.2 Eventos WebSocket que la pestaña escucha

| Evento | Origen | Uso en Configuración |
|---|---|---|
| `engine.status` | backend | actualiza badges de los motores (data / scoring / database) en el Paso 5 |
| `slot.status` | backend | actualiza el estado runtime de cada slot del Paso 3 sin tener que repollar |
| `validator.progress` | backend | alimenta la progress bar del Paso 5 mientras corre la batería (1 evento por test, fases `running` / `passed` / `warning` / `failed`) |
| `system.log` | backend | si el módulo de logs llega al Dashboard, también se puede mostrar la tail de los últimos 5 logs en el pie de Configuración (opcional, decisión abierta) |
| `api_usage.tick` | backend | refresco en vivo del estado de cada TD key del Paso 2 (último call, créditos consumidos) |

---

## 1. Paso 1 — Identidad y persistencia local

Define **quién accede a esta instalación** y **dónde vive su estado** en disco. Es el primer paso porque sin bearer no se puede tocar ningún otro endpoint.

### 1.1 Bloque "Acceso a la API"

**Inputs:**

| Campo | Tipo | Requerido | Comportamiento |
|---|---|---|---|
| `bearer_token` | password (texto oculto con toggle "mostrar") | Sí | El valor se persiste en `localStorage`. El cliente HTTP del frontend lo inyecta como header `Authorization: Bearer <token>` automáticamente. |

**Botones:**

- **Guardar** — escribe en `localStorage`, dispara reconexión del WebSocket con el nuevo token, dispara refetch de las queries activas (`/engine/health`, `/slots`, etc), muestra toast "token guardado". Mismo handler que el input compacto del footer del shell — los dos comparten estado.
- **Olvidar token** — limpia el `localStorage`, cierra el WebSocket, marca todas las queries como inválidas. Pide confirmación inline ("seguro? cerrarás la sesión"). Toast "sesión terminada".

**Indicador de estado:**

- "configurado" cuando hay token guardado y el último ping al `/engine/health` respondió 200.
- "configurado · sin conexión" cuando hay token pero el último ping falló (network error o 401).
- "incompleto" cuando no hay token guardado.

### 1.2 Bloque "Master key (encriptación de secretos)"

Encripta los 3 secretos del config persistido (TD keys, S3 credentials, bearer token) con Fernet. Sin master key configurada, los demás pasos pueden funcionar pero los secretos quedan en el body de cada request — eso es la deuda técnica actual.

**Estados posibles:**

1. **Sin master key** — el módulo `config/` no tiene clave; el frontend muestra:
   - Texto explicativo del rol de la master key.
   - Botón **"generar nueva master key"** → llama al backend para que cree una en `data/master.key`. Backend devuelve la clave en plaintext una sola vez para que el usuario pueda guardarla en un gestor de contraseñas externo (la pantalla muestra la clave junto a un botón **"copiar al portapapeles"** + un botón **"ya guardé la clave"** que cierra el modal). Después de cerrar el modal, la clave ya no se vuelve a mostrar.
   - Botón **"cargar master key existente"** → input de texto + "guardar". Útil cuando se restauró un backup en otra máquina y se quiere recuperar la misma clave.

2. **Con master key cargada** — el frontend muestra:
   - Etiqueta "master key activa" (sin mostrar el valor).
   - Botón **"regenerar"** → con confirmación doble ("se borrarán los secretos encriptados actuales — seguro?"). Genera una nueva clave y vacía el `UserConfig`. El usuario debe rellenar TD keys y S3 de nuevo.
   - Botón **"exportar a archivo"** → descarga `master.key` para que el usuario lo guarde en un USB / gestor de contraseñas.

**Indicador de estado:**

- "configurado" cuando hay master key activa.
- "incompleto" cuando no la hay.
- No bloquea el avance al Paso 2; los secretos viajarán por body hasta que esté.

### 1.3 Bloque "Paths del sistema"

Rutas de archivo que el backend usa. Editables sólo cuando el backend está apagado (cambiarlas en runtime no tiene efecto hasta el próximo reinicio).

**Inputs read-only en runtime, editables al primer arranque:**

| Campo | Default | Origen | Uso |
|---|---|---|---|
| `db_path` | `data/scanner.db` | `SCANNER_DB_PATH` | DB operativa SQLite |
| `archive_db_path` | `data/archive/scanner_archive.db` | `SCANNER_ARCHIVE_DB_PATH` | DB de archivo (rotación). Vacío = archive deshabilitado. |
| `log_dir` | `LOG` | `SCANNER_LOG_DIR` | Dir de logs rotables del backend + reportes TXT del validator |
| `registry_path` | `slot_registry.json` | `SCANNER_REGISTRY_PATH` | Slot registry persistido |

**Comportamiento:**

- Cada input muestra el path actual en disco. Con backend levantado, el input está deshabilitado y aparece un mensaje "para cambiar: detener el backend, modificar `.env`, reiniciar".
- Botón **"abrir carpeta de datos"** al lado de `db_path` que usa la API del SO (Windows: `explorer.exe`, macOS: `open`, Linux: `xdg-open`) para revelar la ubicación. Útil para debug.
- Botón **"recargar desde .env"** que pide al backend que vuelva a leer su `Settings`. Muestra un toast indicando si tomó cambios o si hay que reiniciar (la mayoría de paths requieren reinicio porque el `db_engine` ya está creado).

**Indicador de estado del bloque:** siempre "informativo" — no bloquea ni se valida; sólo refleja la realidad del backend en runtime.

---

## 2. Paso 2 — Proveedor de datos (TwelveData)

Configura las **5 API keys** que el `KeyPool` rota round-robin para todos los fetches del Data Engine. Backend espera el formato CSV `key_id:secret:credits_per_minute:credits_per_day` en `SCANNER_TWELVEDATA_KEYS` o vía el módulo `config/` encriptado.

### 2.1 Bloque "Lista de keys"

**Una fila por cada key registrada.** El frontend admite hasta 5 keys (límite operativo del producto · spec §3.1) y al menos 1 (sin keys el Data Engine no arranca).

**Campos por fila:**

| Campo | Tipo | Requerido | Validación |
|---|---|---|---|
| `key_id` | texto corto | Sí | único entre las 5 keys, alfanumérico, máx 24 chars. Es el label que aparece en la `apibar` del Cockpit (`KEY 1`, `KEY 2`, etc). |
| `secret` | password (oculto, toggle "mostrar") | Sí | API key real de TwelveData. Mín 16 chars. |
| `credits_per_minute` | numérico (entero) | Sí | rango 1-1000. Default sugerido: 8 (plan free). |
| `credits_per_day` | numérico (entero) | Sí | rango 100-100000. Default sugerido: 800 (plan free). |
| **estado** | badge read-only | — | "ok" / "fail" / "probando" / "no probada" según el último probe. |

**Acciones por fila:**

- **Probar** — dispara probe individual (ver §2.2). Cambia el badge a "probando" mientras dura, después a "ok" o "fail" con mensaje del backend.
- **Eliminar** — confirma inline ("seguro? la key se borra de la rotación") y la quita. Si era la última key, se bloquea con tooltip ("debe quedar al menos 1 key configurada").
- **Mostrar/ocultar secret** — toggle del input de password.

### 2.2 Bloque "Probe de conectividad"

Verifica que cada key responda al endpoint `/quote` de TwelveData con sus credenciales. Sin probe pasado las keys quedan "no probadas" pero igual se persisten — el backend las usa hasta que la primera fetch real falle.

**Comportamiento del probe individual:**

- Llama `POST /api/v1/validator/connectivity` enviando sólo el `key_id` a probar (el endpoint actual prueba todas; mientras no se extienda con filtro, el frontend filtra el response por `key_id`).
- Time-out de 10s. Si excede, badge "fail" con mensaje "timeout".
- Mensaje "ok" cuando la key responde 200; "fail · &lt;código&gt;" con el código real (401 invalid key, 429 rate limit, 5xx upstream).

**Comportamiento del probe agregado:**

- Botón **"probar todas las keys"** al final del bloque.
- Llama `POST /api/v1/validator/connectivity` y mappea el response (lista de `{key_id, ok, error?}`) a los badges de cada fila simultáneamente.
- Mientras dura, todas las filas pasan a "probando" y el botón se deshabilita.
- Al finalizar muestra un toast resumen: "5/5 keys ok" o "3/5 keys ok · 2 con error".

**Probe de S3 (opcional, embebido aquí porque comparte endpoint):** el endpoint `/validator/connectivity` también prueba S3 si está configurado. Si falla, se dispara un toast warning ("S3 sin conexión — configurar en Paso 4") sin bloquear las keys.

### 2.3 Bloque "Estado en vivo de las keys"

Refleja en tiempo real el uso de cada key, alimentado por el evento WebSocket `api_usage.tick` que el Data Engine emite al cierre de cada ciclo 15M.

**Por key (read-only, una fila resumida):**

- `key_id`
- créditos usados en el último minuto (`used_minute / max_minute` con barra)
- créditos usados en el día (`used_daily / max_daily` con barra)
- timestamp del último call (`hace 3s`, `hace 1m`, etc — formato relativo)
- flag `exhausted` (true cuando la key ya no acepta más fetches en el minuto/día actual)

Es el mismo dato que el Cockpit muestra en su `apibar`, replicado acá para que el usuario pueda diagnosticar problemas de capacity sin salir de Configuración.

### 2.4 Acciones del paso

- **Agregar key** — botón "+ agregar key" al final de la lista. Habilitado sólo si hay menos de 5 keys.
- **Guardar cambios** — persiste las 5 filas vía el módulo `config/` (con master key del Paso 1) o, mientras la deuda esté abierta, vía un endpoint provisorio `PUT /api/v1/config/twelvedata_keys` que el backend tiene que exponer (todavía no existe — anotar como deuda técnica del wiring).
- **Recargar pool** — fuerza al `KeyPool` del backend a leer de nuevo las keys (hot-reload sin reiniciar). Sólo necesario si se editó el config externamente.

**Indicador de estado del paso:**

- "configurado" cuando hay al menos 1 key con probe "ok".
- "probando" cuando hay al menos un probe en curso.
- "con error" cuando todas las keys están en "fail".
- "incompleto" cuando hay 0 keys configuradas.

---

## 3. Paso 3 — Slot Registry + fixtures

Configura los **6 slots paralelos** del scanner: a cada uno se le asigna un ticker, un fixture canonical y un benchmark. El backend persiste todo en `slot_registry.json` y los cambios disparan hot-reload del runtime + revalidación del Validator (checks A/B/C).

### 3.1 Bloque "Tabla de slots"

**6 filas fijas** (slots 1-6, no se pueden agregar ni eliminar — son el límite operativo del producto). Cada fila representa un slot y muestra todo lo necesario para ver y editarlo.

**Columnas por slot:**

| Columna | Tipo | Editable | Origen |
|---|---|---|---|
| `slot_id` | label (`01` a `06`) | No | hardcoded |
| `ticker` | texto corto (input) | Sí | `GET /slots[].ticker` |
| `fixture` | selector (lista de fixtures disponibles) | Sí | listado del Paso 3.2 |
| `benchmark` | selector (default SPY · vacío = usa el del fixture) | Sí | `GET /slots[].benchmark` |
| `enabled` | toggle on/off | Sí | `GET /slots[].enabled` |
| **estado runtime** | badge | No (lectura del WS) | `slot.status` event + `GET /slots[].status` |

**Estados runtime posibles (4):**

- `active` — slot operativo, recibe scans.
- `warming_up` — slot recién enabled, descargando velas. Animación spinner. Toast amarillo en el Cockpit.
- `degraded` — 3 fallos consecutivos de fetch (ENG-060). Badge rojo, tooltip con mensaje del backend.
- `disabled` — slot apagado por el usuario o nunca enabled.

### 3.2 Bloque "Fixtures disponibles"

Lista de los `*.json` que viven en `backend/fixtures/`. Cada fixture es un canonical validado por hash SHA-256 contra `<fixture>.sha256`.

**Por fixture:**

| Campo | Origen |
|---|---|
| `fixture_id` (label) | metadata interna del JSON (`metadata.fixture_id`) |
| `version` | `metadata.fixture_version` |
| `ticker_default` | `ticker_info.ticker` |
| `benchmark_default` | `ticker_info.benchmark` |
| `engine_compat_range` | `metadata.engine_compat_range` |
| `hash_status` | "ok" / "mismatch" / "no canonical" según el SHA-256 |
| `usado por` | lista de los slots que lo tienen asignado (e.g. `slot 01, slot 03`) |

**Acciones por fixture:**

- **Ver detalle** — abre un panel lateral con el JSON pretty-printed (read-only) y los campos críticos (confirm_weights, score_bands, detection_thresholds).
- **Eliminar** — sólo si `usado por = []`. Confirma inline. Si está asignado, el botón está deshabilitado con tooltip.

### 3.3 Bloque "Upload de fixture"

Permite agregar fixtures nuevos al backend sin tener que pasar por el filesystem manualmente.

**Componente:**

- Drop zone + file picker que acepta archivos `.json`.
- Al seleccionar un archivo, el frontend:
  1. Lee el JSON localmente y valida estructura (Pydantic schema mismo que el backend usa para `Fixture`).
  2. Computa SHA-256 local del payload.
  3. Lo envía vía `POST /api/v1/fixtures/upload` con multipart o body. **Endpoint inexistente — deuda técnica del wiring**: el backend hoy lee `backend/fixtures/` desde disco al startup. Hasta que el endpoint exista, el frontend muestra un mensaje "para agregar fixture: copiar el `.json` y `.sha256` a `backend/fixtures/` y reiniciar".
- Si el upload existe: muestra preview de la metadata (`fixture_id`, `version`, `ticker_default`, `engine_compat_range`) y un botón **"confirmar y subir"**.
- Validación: si el `engine_compat_range` no incluye la versión del engine actual (`/engine/health.engine_version`), bloquea la subida con mensaje "fixture incompatible — engine actual: 5.2.0 · rango exigido: ≥6.0.0".

### 3.4 Bloque "Acciones por slot"

**Por cada fila de la tabla 3.1:**

- **Habilitar** (cuando `enabled=false`):
  1. Frontend llama `PATCH /api/v1/slots/{id}` con `{enabled: true, ticker, fixture, benchmark?}`.
  2. Backend valida el fixture (REG-011/012/013), persiste el JSON, marca el slot `warming_up` y broadcast `slot.status`.
  3. Backend lanza warmup task en background (`DataEngine.warmup([ticker])`) → al terminar, marca `active` y broadcast.
  4. Backend lanza también `Validator.run_slot_revalidation()` (checks A/B/C limitados al slot tocado).
  5. UI muestra el slot con badge `warming_up` (con tiempo estimado, ~30s típico).

- **Deshabilitar** (cuando `enabled=true`):
  1. Frontend llama `PATCH /api/v1/slots/{id}` con `{enabled: false}`.
  2. Backend marca `disabled`, broadcast, dispara revalidation A/B/C.
  3. UI refleja inmediatamente; el slot deja de recibir scans.

- **Editar ticker / fixture / benchmark sin tocar el flag** — sólo permitido cuando el slot está `disabled` (cambiar ticker en vivo es destructivo). Si el usuario intenta cambiar ticker con el slot enabled, el frontend pregunta "para cambiar el ticker hay que deshabilitar primero · seguir?" y si confirma, deshabilita → cambia → re-habilita en 3 calls atómicos.

**Comportamiento de errores:**

- Si el `PATCH` retorna 400 (fixture inválido, ticker malformado), toast con el mensaje + el slot queda en su estado previo.
- Si retorna 503 (data_engine no disponible), toast "data engine no inicializado — esperá que arranque" + el slot queda en su estado previo.
- Si la warmup task falla (rate limit de TD durante el fetch), backend broadcasts `slot.status=degraded ENG-060` y la UI lo refleja en el badge.

### 3.5 Bloque "Slot registry — vista canvas (opcional)"

> **Decisión abierta:** el spec menciona una visualización "estilo Runpod nodo-conexión" para esta sección. Es la única parte del producto que considera ese lenguaje visual. Si se implementa, vive en este bloque y reemplaza la tabla de 3.1 cuando el usuario clickea "vista canvas". Si no, queda fuera del MVP.

**Comportamiento si se implementa:**

- 6 nodos (uno por slot) conectados al Data Engine + al Scoring Engine.
- Click en un nodo abre un panel lateral con los mismos controles que la fila de la tabla (3.1) — son dos vistas equivalentes del mismo dato.
- Las conexiones tienen estado visual: "fluyendo" (animación) cuando hay un scan reciente, "estática" cuando el slot está disabled o degraded.
- Botón "vista tabla" / "vista canvas" para alternar.

**Indicador de estado del paso (3 en total):**

- "configurado" cuando hay al menos 1 slot enabled con badge `active` o `warming_up`.
- "incompleto" cuando todos los slots están `disabled`.
- "con error" cuando hay al menos un slot `degraded`.

---

> **Pendientes (B4 – B6):** Persistencia + backup S3 + retención (Paso 4), Validator + arranque (Paso 5), Apéndice de contratos.
