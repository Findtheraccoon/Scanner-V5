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

> **Pendientes (B2 – B6):** TwelveData (Paso 2), Slot Registry + fixtures (Paso 3), Backup + retención (Paso 4), Validator + arranque (Paso 5), Apéndice de contratos.
