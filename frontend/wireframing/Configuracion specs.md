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

## 4. Paso 4 — Persistencia, backup y retención

Controla la **base de datos operativa**, el **archivo histórico**, los **backups remotos a S3** y las **políticas de rotación**. Es el paso "operaciones" — el usuario sólo lo toca una vez al setup y después cuando algo se llena o se rompe.

### 4.1 Bloque "Stats de la base de datos"

Vista en vivo del estado de la DB operativa y del archive. Refrescable (poll cada 30s + manual).

**Datos mostrados (alimentados por `GET /api/v1/database/stats`):**

| Campo | Origen | Formato |
|---|---|---|
| **Tamaño DB operativa** | `size_mb_operative` | "342 MB · de 5000 MB · 6.8% usado" + barra de progreso |
| **Tamaño DB archive** | `size_mb_archive` | "1.2 GB" |
| **Size limit** | `size_limit_mb` | "5000 MB" (numérico, lectura) |
| **Filas por tabla operativa** | `tables_operative` | tabla con `signals`, `heartbeats`, `system_logs`, `validator_reports`, `candles_daily/1h/15m` y filas + retention_seconds |
| **Filas por tabla archive** | `tables_archive` | tabla análoga |
| **Última rotación** | `last_rotation_at` | timestamp + tipo ("normal" / "agresiva" / "shutdown") |

**Acciones:**

- **Refrescar** — botón manual (auto-refresh cada 30s en background).
- **Rotación normal ahora** — `POST /api/v1/database/rotate`. Mueve filas expiradas (según retention policies) a `archive`. Con confirmación inline ("se moverán N filas a archive · seguir?"). Toast "rotación completa: N filas movidas".
- **Rotación agresiva ahora** — `POST /api/v1/database/rotate/aggressive`. Sólo dispara si la DB supera el size limit. Si no, muestra mensaje "no se necesita rotación agresiva (tamaño OK)". Si dispara, retorna `{triggered, size_mb_before, size_mb_after, vacuum_recommended}` y muestra los 3 valores en un toast.
- **VACUUM** — visible sólo cuando la rotación agresiva retornó `vacuum_recommended=true`. SQLite no reclama espacio en disco hasta hacer VACUUM. **Endpoint inexistente** — anotar como deuda técnica del backend (`POST /api/v1/database/vacuum`).

**Indicador visual del bloque:**

- "ok" cuando `size_mb_operative < 80% size_limit_mb`.
- "atención" cuando `size_mb_operative ≥ 80% size_limit_mb` (sugerir rotación).
- "crítico" cuando `size_mb_operative ≥ 95% size_limit_mb` (rotación urgente, banner rojo).

### 4.2 Bloque "Backup remoto S3-compatible"

Configura las credenciales de un bucket S3 (AWS S3, Backblaze B2, Cloudflare R2, MinIO, etc) y permite backup + restore desde la UI.

**Inputs:**

| Campo | Tipo | Requerido | Ejemplo |
|---|---|---|---|
| `endpoint_url` | URL | Sí | `https://s3.amazonaws.com` · `https://s3.us-west-002.backblazeb2.com` · `https://<account>.r2.cloudflarestorage.com` |
| `region` | texto corto | Sí | `us-east-1` |
| `bucket` | texto corto | Sí | `scanner-v5-backups` |
| `access_key` | texto | Sí | clear text — no es secret |
| `secret_key` | password (oculto) | Sí | encriptado por master key (Paso 1) cuando se persiste |
| `prefix` | texto corto | No | `backups/` (default vacío) — útil para compartir bucket con otros productos |

**Botones:**

- **Probar conexión** — llama `POST /api/v1/database/backups` con las credenciales en body como dry-run (sólo lista, no escribe). Si el endpoint responde 200 y devuelve un array (aunque vacío), conexión OK. Si retorna 4xx, toast "credenciales inválidas / bucket inexistente". Si timeout, "no se pudo conectar a `<endpoint_url>`".

- **Backup ahora** — `POST /api/v1/database/backup` con las credenciales en body. El backend hace `VACUUM INTO` + gzip + `upload_fileobj` al bucket. Mientras dura, botón deshabilitado y aparece spinner. Al terminar, toast "backup subido: `s3://<bucket>/<prefix><filename>` · 234 MB". Recarga el listado de backups.

- **Listar backups** — `POST /api/v1/database/backups` con credenciales. Retorna array ordenado descendente por timestamp. Tabla con: nombre, tamaño, fecha de subida, botón "restaurar" por fila.

- **Restaurar desde backup** — `POST /api/v1/database/restore` con credenciales + key del backup. **Doble confirmación obligatoria** ("se descargará `<filename>` y se creará un sibling de la DB operativa actual · esta operación NO sobrescribe la DB en uso · seguir?"). Toast "restore completado: `<sibling_path>` · cerrar el backend, reemplazar la DB y reiniciar para usar la backup". El backend nunca pisa la DB viva.

**Indicador del bloque:**

- "configurado" cuando hay credenciales guardadas y el último probe pasó.
- "configurado · sin conexión" cuando hay credenciales pero el último probe falló.
- "incompleto" cuando faltan credenciales.
- No bloquea: el sistema funciona perfectamente sin S3.

### 4.3 Bloque "Políticas de retención"

Cuándo y cómo se rotan datos viejos. Estos toggles afectan el comportamiento del Database Engine y el watchdog.

**Inputs:**

| Campo | Tipo | Default | Origen | Comportamiento |
|---|---|---|---|---|
| `rotate_on_shutdown` | toggle | `false` | `SCANNER_ROTATE_ON_SHUTDOWN` | Si `true`, dispara una rotación normal al cerrar el backend (lifespan hook). Útil para que los desarrollos largos no acumulen basura. |
| `db_size_limit_mb` | numérico | `5000` | `SCANNER_DB_SIZE_LIMIT_MB` | Umbral en MB que dispara la rotación agresiva. Cambiarlo es un toggle de qué tan agresivo es el watchdog. |
| `aggressive_rotation_enabled` | toggle | `false` | `SCANNER_AGGRESSIVE_ROTATION_ENABLED` | Activa el watchdog automático. Sin esto, sólo la rotación agresiva manual del 4.1 funciona. |
| `aggressive_rotation_interval_s` | numérico | `3600` | `SCANNER_AGGRESSIVE_ROTATION_INTERVAL_S` | Cada cuánto el watchdog chequea el tamaño. Default 1h — conservador para no martirizar el disco. |

**Política normal (informativa, read-only):** la tabla de retention_seconds por tabla viene de `DEFAULT_RETENTION_POLICIES` del backend y NO es editable desde la UI (decisión de producto: la política se ajusta desde código, no desde Configuración). Se muestra como referencia con valores actuales: `signals=∞`, `heartbeats=24h`, `system_logs=7d`, `validator_reports=30d`, etc.

**Política agresiva (informativa):** ~50% de las normales. También read-only.

**Acciones:**

- **Aplicar cambios** — guarda los 4 inputs en `UserConfig` (módulo `config/`) o pide reinicio del backend si toca settings inmutables (los cambios de `aggressive_rotation_enabled` requieren reiniciar el watchdog — el backend tiene que exponer un endpoint hot-reload `POST /api/v1/config/reload-policies` que **no existe todavía** — anotar deuda técnica).

**Indicador del bloque:** siempre "informativo" — no hay validaciones que fallen, sólo cambios de comportamiento.

### 4.4 Indicador de estado del paso

- "configurado" cuando S3 está OK y al menos `rotate_on_shutdown` o `aggressive_rotation_enabled` está marcado.
- "incompleto" cuando S3 nunca fue probado.
- "atención" cuando la DB operativa supera 80% del size limit.

---

## 5. Paso 5 — Arranque y diagnóstico

Controla **qué corre al iniciar el backend** y **cómo se diagnostican problemas en runtime**. Es el paso operativo del día a día — el usuario lo abre cuando algo no anda.

### 5.1 Bloque "Validator — batería completa"

Corre los 7 checks (D, A, B, C, E, F, G) y persiste el reporte en DB + TXT en `LOG/`. Es la herramienta principal de diagnóstico del producto.

**Estado actual del validator (lectura):**

Datos del último reporte vía `GET /api/v1/validator/reports/latest`:

| Campo | Origen |
|---|---|
| `run_id` | UUID del reporte |
| `trigger` | `startup` / `manual` / `hot_reload` / `connectivity` |
| `started_at` / `finished_at` | timestamps con duración derivada |
| `overall_status` | `pass` / `warning` / `fail` |
| Lista de los 7 tests con su `status` individual | `tests_json` |

**Acciones:**

- **Correr validator ahora** — `POST /api/v1/validator/run`. Bloquea el botón mientras dura (~30-90s típico).
- **Solo conectividad** — `POST /api/v1/validator/connectivity`. Más rápido (~5s), corre solo el check G.

**Progress bar (live):**

Mientras corre la batería, una barra de progreso se alimenta del evento WebSocket `validator.progress`. Cada test emite 2 eventos (start + end). El frontend mantiene un dict `{test_id: status}` y cuenta los completados.

**Visualización en tiempo real:**

- **Lista de los 7 tests** con su nombre y un badge dinámico:
  - `pending` (gris) cuando todavía no llegó el `running` event.
  - `running` (azul, spinner) cuando llegó el primer event.
  - `passed` / `warning` / `failed` (verde / amarillo / rojo) cuando llegó el segundo.
- **Barra de progreso global**: 0/7 → 7/7. La barra se llena con el color del peor estado (verde si todos pass, amarillo si hay warning, rojo si hay fail).
- **Mensaje del último test**: muestra el `message` del backend del test que está corriendo (e.g. "Check F · parity 245/245 matches").

### 5.2 Bloque "Histórico de reportes"

Lista los últimos reportes persistidos para auditoría.

**Componente:** lista colapsable con paginación (cursor pagination del backend vía `GET /api/v1/validator/reports?cursor=<id>&limit=20`).

**Por reporte:**

- timestamp + duración
- `trigger` (badge: startup / manual / hot_reload / connectivity)
- `overall_status` (badge verde / amarillo / rojo)
- 7 mini-badges (uno por test) con el resultado

**Click en un reporte:** abre detalle vía `GET /api/v1/validator/reports/{id}`:

- Metadata completa.
- Por test: nombre, descripción, status, mensaje, duración, errores si los hubo.
- Botón "exportar a TXT" (descarga el reporte formateado igual que el TXT que vive en `LOG/`).

**Filtros (opcionales):**

- Por trigger (multi-select).
- Por status (pass / warning / fail).
- Por rango de fecha.

### 5.3 Bloque "Flags de arranque"

Controla qué corre el backend al iniciar.

**Inputs:**

| Campo | Tipo | Default | Origen | Comportamiento |
|---|---|---|---|---|
| `validator_run_at_startup` | toggle | `true` | `SCANNER_VALIDATOR_RUN_AT_STARTUP` | Si `true`, corre la batería completa al arrancar el backend antes de aceptar requests. |
| `validator_parity_enabled` | toggle | `true` | `SCANNER_VALIDATOR_PARITY_ENABLED` | Habilita el Check F (parity exhaustivo). Costoso (~60-90s). |
| `validator_parity_limit` | numérico | `30` | `SCANNER_VALIDATOR_PARITY_LIMIT` | Cuántas señales del parity sample se chequean (vacío = 245, todas). Trade-off entre tiempo y cobertura. |
| `auto_scan_run_at_startup` | toggle | `true` | nuevo (deuda técnica · "Auto-LAST" del spec §5.2) | Si `true`, el `auto_scan_loop` arranca corriendo. Si `false`, arranca pausado y el usuario tiene que hacer "resume" manual. |
| `heartbeat_interval_s` | numérico | `120` | `SCANNER_HEARTBEAT_INTERVAL_S` | Cada cuántos segundos el backend emite heartbeat + corre healthcheck del scoring. |

**Acciones:**

- **Aplicar al próximo arranque** — guarda en el `.env` o en el `UserConfig` (vía `POST /api/v1/config/save` que **no existe todavía** — deuda técnica). Mensaje "los cambios toman efecto al reiniciar el backend".
- **Reiniciar backend ahora** — botón con doble confirmación. **Endpoint inexistente** — deuda técnica (`POST /api/v1/system/restart`). Hasta que exista, el frontend muestra mensaje "para reiniciar: detener y volver a ejecutar `python backend/main.py`".

### 5.4 Bloque "Estado de los motores"

Vista informativa que duplica la del footer del shell, con más detalle. Útil para diagnóstico rápido.

**Por motor (3 motores: data, scoring, database):**

- Badge de status (`green` / `yellow` / `red` / `paused`) — alimentado por WebSocket `engine.status` + `GET /api/v1/engine/health` al cargar.
- Último mensaje recibido del motor.
- Último `error_code` si lo hay.
- Timestamp del último heartbeat.

**Acción:**

- **Ver último healthcheck** — abre el JSON del último `/engine/health` con todos los detalles (uptime, last_heartbeat_at, parity_match_rate del scoring, etc).

### 5.5 Indicador de estado del paso

- "ok" cuando los 3 motores están green y el último reporte del validator es `pass`.
- "atención" cuando hay al menos un motor en yellow o el último reporte tiene `warning`.
- "con error" cuando hay un motor en red o el último reporte falló.

---

## 6. Apéndice — contratos

Esta sección lista de manera compacta los **contratos técnicos** que la pestaña Configuración consume. Sirve de checklist para el implementador del frontend.

### 6.1 Endpoints REST

Todos requieren `Authorization: Bearer <token>`. Errores comunes (no listados por endpoint): `401` sin/con token inválido, `503` si el motor responsable no está inicializado.

| # | Método | Path | Body / Query | Response 200 |
|---|---|---|---|---|
| 1 | `GET` | `/api/v1/engine/health` | — | `{status, scoring{status,error_code?,parity_match_rate?}, data{status,message?}, database{status,message?}, validator{status,message?}, engine_version, uptime_seconds, last_heartbeat_at}` |
| 2 | `GET` | `/api/v1/slots` | — | `[{slot_id, ticker, status, fixture_id?, benchmark?, enabled, message?, error_code?}, ... × 6]` |
| 3 | `GET` | `/api/v1/slots/{id}` | path `id` | objeto individual del item 2 |
| 4 | `PATCH` | `/api/v1/slots/{id}` | `{enabled, ticker?, fixture?, benchmark?}` | `{slot_id, status, message?}` (con `200` y `slot.status` broadcast por WS) · `400` fixture inválido · `404` slot inexistente · `503` data engine no inicializado |
| 5 | `POST` | `/api/v1/validator/run` | — | `{run_id, trigger:"manual", started_at, finished_at, overall_status, tests:[{test_id,status,message,duration_ms}, ... × 7]}` |
| 6 | `POST` | `/api/v1/validator/connectivity` | — | `{run_id, trigger:"connectivity", overall_status, td_keys:[{key_id,ok,error?}], s3:{ok,error?}}` |
| 7 | `GET` | `/api/v1/validator/reports/latest` | — | mismo shape que `/run` |
| 8 | `GET` | `/api/v1/validator/reports` | query `cursor?, limit?, trigger?, status?` | `{items:[...], next_cursor?}` (cursor pagination) |
| 9 | `GET` | `/api/v1/validator/reports/{id}` | path `id` | reporte completo |
| 10 | `GET` | `/api/v1/database/stats` | — | `{tables_operative:[{name,rows,retention_seconds,last_rotated_at?}], tables_archive:[...], size_mb_operative, size_mb_archive, size_limit_mb, last_rotation_at?}` |
| 11 | `POST` | `/api/v1/database/rotate` | — | `{moved:{<table>:N}, archive_size_mb_after}` |
| 12 | `POST` | `/api/v1/database/rotate/aggressive` | — | `{triggered, size_mb_before, size_mb_after, rotation, vacuum_recommended}` · `400` con `:memory:` · `503` sin archive |
| 13 | `POST` | `/api/v1/database/backup` | `{endpoint_url, region, bucket, access_key, secret_key, prefix?}` | `{key, size_bytes, etag?}` |
| 14 | `POST` | `/api/v1/database/restore` | `{...creds, key}` | `{sibling_path, size_bytes}` |
| 15 | `POST` | `/api/v1/database/backups` | `{...creds}` | `[{key, size_bytes, last_modified}, ...]` (orden desc) |
| 16 | `POST` | `/api/v1/scan/manual` | `{ticker, slot_id?, fixture, candles_daily, candles_1h, candles_15m, candle_timestamp, spy_daily?, bench_daily?, sim_datetime?, sim_date?}` | `{id?, conf, signal, dir, score, ticker, slot_id?, candle_timestamp, chat_format?}` (Cockpit lo consume — relevante en Configuración solo si se quiere botón "test scan"). |
| 17 | `GET` | `/api/v1/scan/auto/status` | — | `{paused: bool}` |
| 18 | `POST` | `/api/v1/scan/auto/{pause,resume}` | — | `{paused: bool}` |

### 6.2 Endpoints faltantes (deuda técnica del backend)

Endpoints que la pestaña Configuración necesita para funcionar al 100% y que **todavía no existen**. Cada uno se cablea con un mensaje "no implementado · contactar backend" en el frontend hasta que se agreguen.

| Método | Path | Necesario para | Notas técnicas |
|---|---|---|---|
| `POST` | `/api/v1/fixtures/upload` | Paso 3.3 — upload de fixture nuevo | multipart o body JSON; valida estructura Pydantic + SHA-256 + `engine_compat_range` ⊇ engine actual; persiste en `backend/fixtures/`; no pisa fixtures con el mismo `fixture_id` (responde 409 si ya existe). |
| `DELETE` | `/api/v1/fixtures/{fixture_id}` | Paso 3.2 — eliminar fixture | rechaza con `409` si algún slot lo tiene asignado. |
| `POST` | `/api/v1/database/vacuum` | Paso 4.1 — recuperar espacio post rotación agresiva | bloqueante; SQLite `VACUUM` directo; toma minutos en DB grandes. |
| `PUT` | `/api/v1/config/twelvedata_keys` | Paso 2.4 — guardar 5 keys | encripta `secret` con master key; persiste en `UserConfig`; hot-reload del `KeyPool`. |
| `PUT` | `/api/v1/config/s3` | Paso 4.2 — guardar credenciales S3 | encripta `secret_key` con master key; persiste en `UserConfig`. |
| `PUT` | `/api/v1/config/startup_flags` | Paso 5.3 — guardar 5 flags de arranque | persiste en `UserConfig`; algunos requieren reinicio (mensaje "se aplicará al próximo arranque"). |
| `POST` | `/api/v1/config/reload-policies` | Paso 4.3 — hot-reload del watchdog tras cambiar `aggressive_rotation_interval_s` | reinicia el task del watchdog sin reiniciar el backend. |
| `POST` | `/api/v1/config/master-key/generate` | Paso 1.2 — generar nueva master key | retorna la clave en plaintext una sola vez; persiste en `data/master.key`. |
| `POST` | `/api/v1/config/master-key/load` | Paso 1.2 — cargar master key existente | acepta la clave en body; valida que pueda desencriptar el `UserConfig` actual. |
| `POST` | `/api/v1/system/restart` | Paso 5.3 — reiniciar backend desde la UI | ejecuta `os.execv` o equivalente; el frontend reconecta automáticamente con backoff. |
| `GET` | `/api/v1/system/open-folder` | Paso 1.3 — botón "abrir carpeta de datos" | invoca el SO (Windows: `explorer.exe`, macOS: `open`, Linux: `xdg-open`); responde `200 {opened: true}` o `501` si no se puede. |

**Settings que faltan en `Settings` (Pydantic):**

- `auto_scan_run_at_startup: bool = True` — el "Auto-LAST" del spec §5.2. Hoy el `auto_scan_loop` arranca corriendo siempre.

### 6.3 Eventos WebSocket consumidos

Conexión: `/ws?token=<bearer>`. Auto-reconnect con backoff `1/2/4/8/16s` (ya implementado en `useScannerWS`).

| Evento | Shape del payload | Uso en Configuración |
|---|---|---|
| `engine.status` | `{engine: "data"\|"scoring"\|"database"\|"validator", status: "green"\|"yellow"\|"red"\|"paused", message?: string, error_code?: string}` | Paso 5.4 — badges de los 3 motores actualizados sin repollar. `paused` se convierte en sub-estado `dataPaused` del store. |
| `slot.status` | `{slot_id: number, status: "active"\|"warming_up"\|"degraded"\|"disabled", message?: string, error_code?: string}` | Paso 3.1 — badge runtime de cada slot. |
| `validator.progress` | `{run_id: string, trigger: "startup"\|"manual"\|"hot_reload"\|"connectivity", test: string, status: "running"\|"passed"\|"warning"\|"failed", message?: string}` | Paso 5.1 — barra de progreso live + 7 mini-badges. 2 events por test (start + end). |
| `api_usage.tick` | `{key_id, used_minute, max_minute, used_daily, max_daily, last_call_ts: ISO\|null, exhausted: bool}` | Paso 2.3 — refresco en vivo del uso de cada TD key. |
| `system.log` | `{level: "info"\|"warning"\|"error", message: string, source?: string}` | (opcional) Paso 5 — tail de los últimos N logs. Hoy la pestaña no lo consume; el Dashboard sí lo hará cuando llegue. |
| `signal.new` | `{...SignalPayload}` | No consumido por Configuración (lo consume el Cockpit). |

### 6.4 Comportamiento: hot-reload vs reinicio del backend

Para que el wireframe sepa qué labels mostrar al usuario en cada cambio:

**Cambios que toman efecto inmediatamente (sin reinicio):**

- Paso 1.1 — bearer token: hot-reload del cliente HTTP + WS al guardar.
- Paso 2 — TD keys (vía `KeyPool.reload()`).
- Paso 3 — slots: enable/disable + warmup + revalidation A/B/C.
- Paso 4.1 — rotaciones manuales (operación puntual).
- Paso 4.2 — backup / restore S3 (operación puntual).
- Paso 4.3 — `db_size_limit_mb` (lectura en cada chequeo del watchdog).
- Paso 5.1 — correr validator manual.

**Cambios que requieren reinicio del backend:**

- Paso 1.3 — paths del sistema (`db_path`, `archive_db_path`, `log_dir`, `registry_path`). El `db_engine` ya está creado.
- Paso 4.3 — `aggressive_rotation_enabled` (toggle del watchdog · habrá hot-reload con el endpoint `/config/reload-policies` cuando exista).
- Paso 5.3 — todos los flags de arranque (`validator_run_at_startup`, `validator_parity_*`, `auto_scan_run_at_startup`, `heartbeat_interval_s`).
- Paso 1.2 — regenerar master key (los secretos del `UserConfig` se invalidan; reload del config al volver a arrancar).

**Cambios que requieren acción manual fuera del backend:**

- Paso 3.3 — upload de fixture (hasta que exista `/fixtures/upload`): copiar `.json` y `.sha256` a `backend/fixtures/` + reiniciar backend.

### 6.5 Persistencia local vs persistencia en backend

Para que el wireframe sepa dónde "vive" cada cosa:

| Configuración | Persistencia | Notas |
|---|---|---|
| Bearer token | `localStorage` del browser | No viaja al backend; sólo se inyecta como header. |
| Master key | `data/master.key` en disco del backend | El backend la lee al startup; el frontend nunca la ve después de generarla. |
| TD keys (5) | `UserConfig` encriptado (`data/user_config.json` o equivalente) | `secret` encriptado con master key. |
| S3 credentials | `UserConfig` encriptado | `secret_key` encriptado con master key. |
| Slot registry | `slot_registry.json` (fuente de verdad · spec §3.3) | Plain JSON · sin secretos. |
| Fixtures | `backend/fixtures/*.json` + `*.sha256` | Plain JSON · validados por hash. |
| Flags de arranque | `.env` o `UserConfig` | Decisión abierta de producto: hoy van en `.env`, deberían migrar a `UserConfig` para que la UI los pueda persistir. |
| Políticas de retención | mismo lugar que flags | idem. |

---

## Cierre

El documento cubre los **5 pasos verticales** de la pestaña Configuración con todos los inputs / botones / validaciones necesarios para implementar el wireframe hi-fi del diseñador y, después, el componente React.

**Próximo paso recomendado del producto:** que el diseñador arme el hi-fi standalone (formato `frontend/wireframing/Configuracion Hi-Fi v1.html`) usando este spec como contrato funcional + el lenguaje visual Phoenix del Cockpit Hi-Fi v2 como referencia estética.

**Próximo paso recomendado del backend:** cerrar las **11 deudas técnicas** listadas en §6.2 antes de que el frontend implemente la pestaña — sin esos endpoints, varias funciones de Configuración no se pueden cablear de manera real (sólo placeholders).
