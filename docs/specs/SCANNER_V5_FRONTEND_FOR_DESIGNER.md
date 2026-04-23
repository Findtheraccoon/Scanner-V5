# SCANNER_V5_FRONTEND_FOR_DESIGNER.md

> **Propósito:** briefing de diseño visual para el frontend del Scanner v5 live. Dirigido al DESIGNER que va a producir mockups, design system y componentes. Las decisiones estéticas son el foco; el §16 (anexo técnico) aporta el contexto mínimo del backend que el DESIGNER necesita para dimensionar badges, estados push vs pull y microcomportamientos de pilotos.
>
> **Estado (v2.1.0):** las 4 pestañas completamente definidas. El Cockpit queda cerrado tras la sesión del 20-abril; decisiones estéticas + contenido del panel derecho + mecánica del botón Copiar ya resueltas. Se suma anexo técnico §16 con la superficie backend real al 23-abril (healthcheck continuo, watchdog de rotación, histórico Validator, códigos de error, eventos WS).

**Última actualización:** 2026-04-23 · **Versión del briefing:** 2.1.0

---

## 1 · Producto — una pantalla de contexto

Scanner de trading de opciones sobre la bolsa norteamericana. Herramienta profesional de uso intensivo durante el horario de mercado (9:30-16:00 ET). El usuario — un trader de opciones que trabaja con hasta 6 tickers en paralelo (5 preset + 1 libre por default) — lo abre cada mañana, lo usa durante 6 horas, y lo cierra.

**Personalidad del producto:**
- **Serio y preciso** — es herramienta profesional, no consumer app
- **Denso donde hace falta, respirado donde no** — el Cockpit muestra señales en tiempo real; el Dashboard admin muestra estado de sistema; Memento es consulta tranquila
- **Oscuro por default** — el trader tiene el cockpit abierto durante horas en un monitor
- **Sin chrome innecesario** — cero badges "BETA", cero animaciones decorativas, cero iconos coloridos sin función
- **Cuando llega una señal importante, tiene que gritar** — mientras tanto, se mantiene callado

---

## 2 · Referencias visuales

### 2.1 Lenguaje visual base — icomat.co.uk

**Aplica a las 4 pestañas del producto.** Es el lenguaje base del scanner entero.

**Qué extraer:**
- Oscuro, industrial, sobrio, limpio.
- Paleta negra profunda + acentos cromáticos sutiles (un acento único de marca a definir por DESIGNER).
- Tipografías sans-serif sobrias, muchas en minúscula.
- Letterspacing generoso en headers y labels clave.
- Backgrounds discretos (pueden incluir video sutil estilo icomat, a evaluar en Cockpit).
- Cards minimalistas con bordes al 10-15% de opacidad.
- Animaciones discretas en transiciones, no decorativas.

### 2.2 Vocabulario estructural — runpod.io

**Aplica donde la función lo requiere:** Paso 3 de Configuración (canvas de slots con nodo-conexión), Dashboard (iconos de motores/servicios, diagramas de sistema), secciones con mucha densidad informacional.

**Qué extraer:**
- Patrón de nodo-conexión: cards como nodos con pines/conectores editables con drag & drop.
- Iconografía técnica funcional (no decorativa).
- Diagramas de sistema con estados visibles.

### 2.3 Cómo se combinan — decisión W

**No son dos estilos conviviendo.** Es **un solo estilo (icomat)** con vocabulario estructural prestado de Runpod donde la función lo requiere. Los componentes Runpod adoptan la paleta/tipografía/spacing de icomat, no traen los suyos.

Ejemplos:
- El canvas de slots del Paso 3 usa el patrón nodo-conexión Runpod, pero con fondo icomat, tipografía icomat, bordes al 10-15%, acentos del producto (no azul-tech Runpod).
- El Dashboard con motores/slots/tablas usa iconos técnicos Runpod pero en paleta icomat: densidad informacional manejada con jerarquía tipográfica + spacing icomat, no con color saturado.
- El Cockpit no tiene vocabulario Runpod: es icomat puro (poca densidad, disclosure progresiva).
- Memento naturalmente cae en icomat (consulta tranquila, pocos elementos por vista).

### 2.4 Scanner v4.2.1 (HTML monolítico)

Es la herramienta actual de Álvaro. El v5 la reemplaza. El v4.2.1 **no es referencia visual** — sirve solo como referencia conceptual de qué información hay que mostrar (score, confidence, layers de análisis, patterns detectados). El diseño visual actual es funcional pero obsoleto; se rediseña desde cero.

---

## 3 · Estructura del producto — 4 pestañas

El scanner tiene 4 pestañas de nivel superior. Orden visual en la navegación:

1. **Configuración** (setup inicial + ajustes)
2. **Dashboard** (panel admin — estado del sistema)
3. **Cockpit** (pantalla operativa del trader en sesión)
4. **Memento** (consulta de estadísticas y catálogo de patrones)

**Flujo típico de un día:**
- Apertura → Configuración (revisar setup, cargar Config LAST) → salta a Dashboard si todo OK → Cockpit (pantalla activa durante las 6h de sesión) → consulta Memento si quiere revisar performance de un slot → cierre al final del día.

---

## 4 · Pestaña CONFIGURACIÓN

**Rol:** setup inicial y ajustes. Se usa sobre todo al abrir el scanner la primera vez o al cambiar de máquina. Algunas cosas se tocan también durante la sesión (agregar un ticker, recargar una fixture).

**Layout general:** vertical apilado con scroll. 4 pasos uno tras otro, todos visibles simultáneamente. El usuario hace scroll entre ellos. Cada paso es una sección con header propio.

### Paso 1 — Config del usuario

**Componentes:**
- Nombre del Config cargado actualmente (label prominente arriba)
- Botonera: `Cargar` · `Guardar` · `Guardar como` · `LAST`
- Sección plegable **ONLINE BACKUP** (por default cerrada):
  - Dropdown de provider (opciones: AWS S3, Backblaze B2, Cloudflare R2, Custom endpoint)
  - Campo endpoint URL
  - Campo bucket name
  - Campos access key + secret key (ambos enmascarados con toggle mostrar)
  - Botones `Backup ahora` y `Restore desde cloud`
  - Indicador del último backup realizado (timestamp + tamaño)

**Estados:**
- Config con cambios sin guardar → indicador visual junto al nombre (punto rojo o asterisco)
- Config nuevo sin guardar → estado "sin título"
- Backup en progreso → spinner + porcentaje
- Restore exitoso → mensaje confirmatorio + reinicio requerido

### Paso 2 — API Keys

**Componentes:**
- Label de sección: "Proveedores de datos — hasta 5 keys"
- 5 filas/cards, una por key slot:
  - Alias editable (ej. "key principal", "backup")
  - Campo de valor (por default enmascarado `••••••••`, toggle "mostrar")
  - Campo numérico: créditos por minuto (default 8)
  - Campo numérico: créditos diarios máximos (default 800)
  - Toggle activa/inactiva
  - Piloto circular (verde/amarillo/rojo) con estado actual de la key
  - Botón `Test` por key (verifica que el provider responde)
- Sección vacía si menos de 5 keys configuradas: card "+ Agregar key" al final

**Estados:**
- Key no configurada → card en estado "vacía" (placeholder + botón agregar)
- Key configurada inactiva → card gris, toggle apagado
- Key activa operando → card normal con piloto verde
- Key con problema (cupo agotado, auth fallida) → piloto amarillo/rojo + mensaje corto
- Test en curso → spinner en botón

### Paso 3 — Fixtures + Slot Registry

**Componentes principales:** canvas tipo React Flow con 6 slots visibles como nodos.

**Cada nodo (slot):**
- Número prominente (1 a 6)
- Campo de ticker (dropdown con watchlist preset SPY/QQQ/IWM/AAPL/NVDA + campo libre para otros)
- Campo de fixture (dropdown con 3 grupos: canonicals del ticker / fixtures activas del Config actual / "Cargar fixture...")
- Benchmark (texto read-only, se auto-llena desde la fixture)
- Toggle activo/inactivo
- Piloto de estado en tiempo real

**Modal "Cargar fixture":**
- Area drag & drop o botón de file picker
- Acepta: archivo `.json` único, archivo `.metrics.json` opcional por separado, o `.zip` con ambos
- Al seleccionar → preview del contenido + validación
- Si pasa validación → botón `Aplicar` activo
- Si falla → mensaje de error claro (código + descripción humana)

**Estados de cada slot:**
- Vacío (sin ticker asignado) → card fantasma con placeholder "Asignar ticker"
- Configurado inactivo → card gris
- Configurado activo pero esperando arranque → card normal, piloto apagado
- Warming up → piloto amarillo + spinner + porcentaje + label "warming up"
- **Revalidando** → transición que ocurre **automáticamente tras un cambio en el slot** (enable, disable, cambio de fixture). Piloto amarillo con label "revalidando" + spinner fino. Dura unos segundos. El usuario no la dispara manualmente; es consecuencia de cualquier PATCH. Durante esta ventana las señales del slot se pausan.
- Operativo → piloto verde
- DEGRADED → piloto amarillo + código de error expandible
- Error fatal → piloto rojo + código

**Nota técnica para el DESIGNER:** tras cualquier cambio en el registry de slots (enable, disable, cambio de fixture), el sistema corre automáticamente una mini-batería de validación en segundo plano (~2-5 segundos). El warmup y la revalidación pueden encadenarse: al enable → warming up → revalidando → operativo. El diseño debe soportar esta secuencia con transiciones claras entre estados.

**Restricciones visibles en UI:**
- Mínimo 1 slot activo → si el usuario intenta desactivar el último activo, bloqueado con mensaje
- Si el ticker asignado no tiene fixture canonical disponible → mensaje "ticker sin canonical aprobada, asigná una fixture manualmente"

### Paso 4 — Arranque de motores

**Componentes:**
- Lista vertical en orden de dependencias (header: "Arranque del sistema"):
  1. Database Engine
  2. Data Engine
  3. Slot Registry
  4. Scoring Engine
  5. Validator (batería inicial)
- Cada fila: nombre + botón individual `Iniciar` + piloto + estado textual
- Botón global arriba: **`Arrancar todos`** (corre en secuencia respetando dependencias)

**Al correr Validator — sub-panel de progreso:**
- Progress bar general con los 7 tests:
  1. D — Infraestructura
  2. A — Fixtures
  3. B — Canonicals
  4. C — Slot Registry
  5. E — Test end-to-end
  6. F — Parity test
  7. G — Conectividad externa
- Cada test con checkmark al pasar, X al fallar, spinner si en curso
- Al final: mensaje `Sistema operativo. Ir al Cockpit.` o `Sistema con warnings — ver Dashboard` o `Fatal — revisar log`

**Caso Auto-LAST:**
- Si al abrir el scanner hay un LAST válido y completo → Paso 4 se saltea automáticamente, el sistema arranca sin interacción, y el usuario aterriza directo en Cockpit o Dashboard
- Durante el autoarranque: splash screen con logo + progress bar de los motores + Validator

---

## 5 · Pestaña DASHBOARD

**Rol:** panel admin. Estado del sistema, operaciones administrativas. El trader la abre puntualmente durante el día para verificar salud o hacer limpieza; no vive acá en sesión de trading.

**Layout:** vertical apilado con secciones colapsables. Header fijo con Piloto Master.

**Header fijo:**
- **Piloto Master** global — indicador grande y prominente (verde/amarillo/rojo). Siempre visible.
- Badge con versión del scanner, timestamp actual, tiempo desde arranque

### Sección 1 — Motores y servicios

**Grid de cards**, uno por motor/servicio:
- Database Engine
- Data Engine
- Scoring Engine
- Validator
- Twelve Data connector (salud de conexión al provider)
- S3 connector (si configurado)

**Cada card:**
- Nombre del motor
- Piloto circular de estado
- Timestamp del último heartbeat (relativo: "hace 45s")
- Uso de memoria actual + % del límite (barra pequeña)
- Código de error si no verde (ej. "ENG-050 parity check")
- Botón `Ver log` (abre modal/drawer con los últimos logs del motor)

**Nota técnica para el DESIGNER — piloto del Scoring Engine:** el Scoring Engine corre un mini-test de integridad **cada ~2 minutos** en segundo plano (sin intervención del usuario). Si el test detecta drift, el piloto pasa **verde → amarillo (código ENG-050)** solo; si vuelve a pasar limpio, retorna a verde. Esto implica que el piloto del Scoring puede cambiar de color autónomamente durante la sesión. Para suavizar el impacto visual, la transición debería ser un **fade entre colores**, no un salto duro. Igual comportamiento aplica al Piloto Master del header (agregando un nivel más de amarillo si cualquier motor lo está).

### Sección 2 — Slots

**Grid libre de cards** (uno por slot, layout no secuencial — el trader ve de un vistazo el estado de los 6 slots).

**Cada card de slot:**
- ID slot + ticker + fixture asignada
- Piloto de estado
- Última señal emitida: timestamp + score + confidence
- Estado: operativo / warmup (con %) / DEGRADED (con código) / inactivo

### Sección 3 — Base de datos

**Variante 1 — grid de cards con barras de progreso.**

Card por tabla (signals, heartbeat, system_log, candles_daily, candles_1h, candles_15m):
- Nombre de tabla
- Filas en DB operativa (número)
- Barra de progreso hacia límite de retención (colores según proximidad al límite)
- Filas en archive si aplica
- Peso en disco

**Acción global:** botón `Correr limpieza ahora` que dispara la rotación manual hacia archive.

**Barra de tamaño total de la DB operativa** (arriba del grid de tablas): barra horizontal grande que muestra `tamaño actual MB / límite configurado MB`. Verde hasta ~70%, amarillo 70-90%, rojo >90%.

**Watchdog automático opt-in** — el usuario puede tener activado un watchdog que dispara rotación agresiva al superar el límite de tamaño. Cuando está on:
- Badge en el header de la sección: `Watchdog: ON` (neutro informativo, no alarma).
- La barra de tamaño puede **bajar sola en vivo** cuando el watchdog se dispara (transición animada, no salto).
- Después de una rotación disparada, el sistema puede sugerir un VACUUM: badge amarillo `⚠ VACUUM recomendado — reclamar espacio en disco` con botón `Ejecutar VACUUM ahora` (operación de minutos, UI debe indicar que bloquea escrituras durante el run).

**Sub-sección** (opcional, colapsable): "Últimos backups" con historial del S3 (timestamps + tamaños + botón restore por cada uno).

### Sección 4 — Pruebas de validación

**Botones de acción:**
- `Revalidar sistema` (corre batería completa de Validator)
- `Test API` (solo categoría G — conectividad)

**Último reporte Validator** (siempre visible, persistente):
- Timestamp de última ejecución
- **Trigger del run** (badge pequeño): `startup` · `manual` · `hot_reload` · `connectivity` — indica qué disparó la corrida
- Estado general (verde/amarillo/rojo)
- Tabla con 7 filas (categorías A-G) + resultado individual por cada una
- Log expandible debajo

**Histórico de reportes** (colapsable, debajo del último reporte):
- Botón `Ver histórico` abre drawer/modal con timeline de runs anteriores
- Cada entrada: timestamp + trigger + overall_status (verde/amarillo/rojo) + botón para expandir el detalle completo (mismas 7 filas + log)
- Paginación por cursor (lista infinita con scroll)
- Los reportes viejos (>30 días) viven en archive pero se leen de forma transparente — el usuario no distingue

**NOTA:** el dashboard **no muestra gráfico histórico de heartbeat** — solo estado actual. Los reportes de Validator sí tienen histórico navegable porque son eventos discretos útiles para auditoría post-mortem.

---

## 6 · Pestaña MEMENTO

**Rol:** consulta. Solo lectura. Estadísticas empíricas por slot y catálogo de patrones. El trader entra cuando quiere revisar la performance histórica de un slot o entender mejor qué patrón está detectando el sistema.

**Layout:** 2 secciones colapsables grandes.

### Sección A — Stats por Slot

6 subsecciones colapsables (una por slot activo). **Por default todas colapsadas** — el trader expande la que quiere.

**Al expandir un slot:**
- Header con ticker + fixture + versión
- **Tabla WR por franja:** filas B / A / A+ / S / S+, columnas "WR training %" (con N entre paréntesis) / "WR out-of-sample %" / "cobertura %"
- **Métricas globales:**
  - Spread B→S+ (diferencia de WR entre las franjas extremas, métrica clave de calidad)
  - Progresión monotónica (check sí/no visual: B < A < A+ < S < S+)
  - MFE/MAE promedio por franja si están disponibles
- **Uplift marginal por confirm:** gráfico de barras horizontal pequeño o tabla — FzaRel +12pp, BBinf_1H +8pp, etc.
- **Thresholds check:** tabla de umbrales de la fixture vs consenso empírico, con flag si hay desviación importante
- **Metadata:** dataset period, benchmark, fecha de calibración

Todos estos datos salen del archivo de métricas que acompaña a cada fixture. El DESIGNER puede asumir que cada campo está disponible; el diseño define cómo se presenta.

### Sección B — Catálogo de Patrones

3 subsecciones colapsables:

1. **TRIGGERS** — los patrones que disparan señales (doji, hammer, shooting star, engulfings, dobles techo/piso, cruces de MA, rechazos, ORB breakout/breakdown)
2. **CONFIRMS** — los patrones que confirman una señal existente (FzaRel, Bollinger extremos, VolHigh, VolSeq, Gap, SqExp, DivSPY)
3. **RISKS** — patrones que indican riesgo (se muestran como warnings, no restan score)

**Cada tarjeta de patrón:**
- Nombre del patrón
- Tendencia asociada (bullish / bearish / both) — visible como tag
- Peso actual (hardcoded si trigger/risk, de la fixture si confirm)
- Significado — texto descriptivo humano (lo escribe Álvaro, ~2-3 oraciones)
- **Stats globales:** WR @ score ≥ 30, cobertura global (% de señales que incluyen este patrón)

**Diseño visual:** tarjetas informativas, no interactivas. El usuario lee, no ejecuta acciones.

**No incluir en v1:** gráfico descriptivo visual del patrón (ej. dibujo de un "doji" sobre velas japonesas). Se difiere.

---

## 7 · Pestaña COCKPIT

**Rol:** la pantalla operativa del trader. Vive abierta durante las 6 horas de sesión de mercado. Muestra señales en tiempo real, estado de los slots, banner con estado de API keys, gráfico del ticker seleccionado. Es el corazón funcional del producto.

**Nivel de cierre de decisiones: 100% (v2.0.0).** Estética, layout, panel derecho y botón Copiar resueltos.

### 7.1 Layout general

- **Columna izquierda:** watchlist con 6 cards verticales, una por slot
- **Columna derecha (mucho más ancha):** panel de detalle del slot seleccionado, organizado en 3 zonas verticales:
  1. Banner superior con identidad + acción primaria
  2. Resumen ejecutivo (siempre visible)
  3. Detalle técnico (expandible, colapsado por default)
- **Banner superior global del Cockpit:** estado de API keys (5 barras + créditos diarios consolidados)
- **Botonera global:** `Scan ahora` (manual) + toggle `Modo AUTO`

**Selección:**
- Al entrar al Cockpit, primera card seleccionada por default.
- Cuando otro slot emite señal nueva, **el panel NO salta automáticamente** — el trader mantiene el foco donde está; la card del slot que emitió señal se "ilumina" para avisar pero no roba el foco.

### 7.2 Watchlist (columna izquierda) — card por slot

**Cada card:**
- Ticker grande
- Score actual (último calculado)
- Banda de confianza (label + color): REVISAR / B / A / A+ / S / S+
- Dirección (call/put) con icono sutil
- Timestamp de la última señal
- Piloto de estado del slot (si no operativo, se indica ahí)

**Colores de banda — base cromática (sobrios dentro de icomat):**
- **REVISAR** → neutro (gris)
- **B** → azul claro
- **A** → azul más profundo
- **A+** → magenta con glow sutil
- **S** → dorado con glow marcado
- **S+** → negro metalizado con glow + **pulse lento** en la letra "S+" y en los bordes de la card

**Nota sobre la animación S+:** la disonancia intencional se mantiene (la señal S+ debe gritar), pero dentro del lenguaje icomat. Pulse lento y controlado, no flash. Coherente con la sobriedad del producto.

**Bordes de la card:** reflejan el color de la franja actual.

**Estado "slot sin señal reciente":** card en estado neutro, sin color dominante.

### 7.3 Panel derecho — 3 zonas verticales

El panel se organiza en 3 zonas verticales con jerarquía clara.

#### 7.3.1 Banner superior del panel (sticky — siempre visible)

Contiene la identidad y la acción primaria:

- Ticker (grande)
- Banda de confianza (S+/S/A+/A/B/REVISAR) con su color + animación si aplica
- Dirección (CALL/PUT)
- Score numérico
- **Botón `COPIAR`** — acción primaria, visible junto al ticker/banda/score (ver §7.5)

Este banner es la primera cosa que el trader ve al seleccionar una card. Todo lo demás es elaboración de lo que este banner anuncia.

#### 7.3.2 Resumen ejecutivo (siempre visible, debajo del banner)

**~8-10 líneas** con lo indispensable para decidir operar o no:

- Precio actual + Chg% del día
- Alineación 3/3/dir (ej. "3/3 bullish — 15M:bull · 1H:bull · D:bull")
- ATR 15M
- dMA200 (%)
- Flags críticos (si aplican, uno por línea): ⚠️ catalizador · ⚡ squeeze · ↑ ORB · gap · ↗ fuerza relativa extrema
- Vela analizada + timestamps (ej. `vela 14:30 ET · calc +4s`)

Criterio: **decisión en 2 segundos.** Lo que el trader necesita para saber si vale la pena mirar el detalle o pasar al siguiente slot.

#### 7.3.3 Detalle técnico (expandible, colapsado por default)

Botón **"ver detalle técnico"** expande la sección inferior. Estructura **espeja los bloques del texto que copia el botón COPIAR** (mismo orden, misma semántica, distinta presentación). Esto garantiza que el trader mentalmente no cambia de esquema al pasar de la UI al texto pegado en chat:

| Bloque | Contenido |
|---|---|
| **PRECIO** | último, chg día, ATR 15M, dMA200 |
| **CONTEXTO** | alineación detallada, MAs diarias (20/40/200), BB 1H |
| **VOLUMEN** | ratio 15M, ratio 1H, proyección de vela actual, secuencia (↑ creciente / ↓ declinante) |
| **FUERZA RELATIVA** | vs benchmark con diff%, DivSPY si aplica |
| **NIVELES** | soportes/resistencias con etiquetas (PD/R1/S1/etc.) |
| **EVENTOS** | catalizador, squeeze, ORB, gap (bloque se elide completo si no hay eventos activos) |
| **PATRONES** | lista con timeframe · dirección · categoría · peso · decay |
| **SCORING** | estructura ✓/✗ · triggers N(suma) · confirms M(suma) tras dedup · bloqueo · conflicto |
| **RESULTADO** | score · dirección · confianza · señal |
| **Meta** | engine_version · fixture_id + version · slot_id · timestamps completos |

**Nota visual:** cada bloque con su header tipográfico en mayúsculas + letterspacing generoso (patrón icomat). Separadores sutiles entre bloques. Valores numéricos en monospace para alineación visual.

#### 7.3.4 Gráfico del ticker (debajo del detalle técnico, o en panel paralelo si el ancho lo permite)

- Librería: **Lightweight Charts servida localmente** (NO embed de TradingView).
- Velas + overlays de indicadores clave (MAs, Bollinger Bands, volumen).
- Botón **"Abrir en TradingView"** como escape — abre el ticker en pestaña nueva del navegador del usuario (link directo con el símbolo).

### 7.4 Banner superior global de API calls

**Visible permanentemente** arriba del Cockpit (encima de watchlist + panel). Muestra en tiempo real el estado de los créditos de las API keys.

**Dos bloques:**

**Bloque A — "Créditos por minuto":**
- **5 barras horizontales**, una por API key configurada
- Cada barra:
  - Label corto (alias de la key)
  - Texto "X/Y" — usados en el minuto actual / máximo por minuto
  - Barra de progreso que se llena hacia el máximo
  - Timestamp de la última llamada ("hace 3s")
- Si una key no está configurada → slot vacío con placeholder
- Si una key está inactiva → barra gris
- Si una key tiene problema → barra con acento de advertencia

**Bloque B — "Créditos diarios":**
- **Una barra grande** con el consumo diario consolidado de todas las keys activas
- Texto "X/Y usados del día"
- **Reset al final del día de mercado** (no medianoche UTC)
- Indicador visual de proximidad al límite (verde → amarillo → rojo según proximidad)

### 7.5 Botón `COPIAR` (en banner superior del panel derecho)

**Ubicación:** dentro del banner superior del panel derecho (§7.3.1), junto a ticker + banda + dirección + score. Es el primer elemento interactivo que el trader ve al seleccionar una card.

**Función:** copia al clipboard un bloque de texto multilinea con el resumen completo del estado actual del slot seleccionado, formato estructurado, listo para pegar en un chat con un asistente LLM (Claude) y pedir análisis cualitativo antes de ejecutar la operación.

**Mecánica:** el bloque de texto viene **ya armado desde el backend** en cada señal nueva. El frontend solo hace `navigator.clipboard.writeText()` al click — sin latencia, sin procesamiento.

**UI del botón:**
- Sobrio, destacado pero no agresivo. Etiqueta `COPIAR` (mayúsculas + letterspacing).
- Al presionar → feedback visual inmediato (checkmark + cambio de etiqueta a "✓ COPIADO" por 2 segundos).
- El botón está disponible siempre que haya señal cargada en el panel (incluso señales REVISAR/NEUTRAL — no solo SETUP).

**Formato del texto copiado** (referencia para el DESIGNER, no es decoración del botón):

```
═══════════════════════════════════════
SEÑAL · QQQ · A+ · CALL · score 12
═══════════════════════════════════════

PRECIO
Último:     $485.32
Chg día:    +0.82%
ATR 15M:    0.74% ($3.59)
dMA200:     +3.2% ($470.12)

CONTEXTO
Alineación: 3/3 CALL  (15M:bull · 1H:bull · D:bull)
MAs diarias: 20=$483 · 40=$478 · 200=$470
BB 1H:      $482.1 / $484.5 / $486.9

VOLUMEN
15M:        1.8× mediana del día
1H:         1.4× mediana del día
Vela curso: 2.1× proyectado (fracción 0.66)
Secuencia:  ↑ creciente

FUERZA RELATIVA
vs SPY:     +0.87%
DivSPY:     QQQ=+0.82% · SPY=+0.41%

NIVELES CLAVE
R: $487.2 (PD) · $489.5 (R1)
S: $483.8 (S1) · $481.1 (PD)

EVENTOS
⚡ Squeeze BB 1H   ancho p12 → expansión
↑ ORB Breakout    rango $484.1-$485.8
⚠️ Catalizador    chg > 1.5×ATR

PATRONES (3)
• [15M] Doji BB inf      bull · trigger · w:2
• [15M] ORB Breakout     bull · trigger · w:2
• [1H]  BBinf_1H         bull · confirm · w:3

SCORING
Estructura: ✓
Triggers:   2 señales  (suma 4.0)
Confirms:   1 señal    (suma 3.0)   tras dedup por categoría
Bloqueo:    —
Conflicto:  —

RESULTADO
Score:      12.0
Dirección:  CALL
Confianza:  A+
Señal:      SETUP

───────────────────────────────────────
Meta
Engine:     5.2.0
Fixture:    qqq_v5_2_0 v5.2.0
Slot:       1
Vela:       2026-04-20 14:30 ET
Cálculo:    2026-04-20 14:30:04 ET
```

Este bloque es para referencia del DESIGNER: **la estructura del panel de detalle técnico (§7.3.3) debe espejar este mismo ordenamiento** para que el trader reconozca visualmente los bloques cuando alterna entre UI y texto pegado.

### 7.6 Scan manual y Modo AUTO

**Botón `Scan ahora`:**
- Corre scan sobre todos los slots excepto los vacíos
- No hay scan individual por slot
- Durante el scan → indicador de progreso (~0.5-1 segundo total)
- Al terminar → las cards de watchlist se actualizan con las señales nuevas

**Toggle `Modo AUTO`:**
- ON → las cards se actualizan automáticamente al cierre de cada vela de 15M (9:45, 10:00, 10:15…). Es el modo por default durante la sesión.
- OFF → las cards solo se actualizan al presionar `Scan ahora`. El trader congela la vista.
- Indicador visual del estado (ON/OFF) visible junto al toggle, sin ambigüedad.

**Decisión técnica abierta (no bloquea al DESIGNER):** la semántica backend del toggle AUTO se define en fase de implementación — puede ser (a) solo visual (el backend sigue scanneando, el frontend filtra las actualizaciones), o (b) real (endpoint que pausa el loop). El diseño visual del toggle y sus dos estados es el mismo en ambos casos.

### 7.7 Lo que NO tiene el Cockpit

- **Sin feed cronológico** de señales pasadas (eso vive en Memento o en endpoints REST del backend)
- **Sin métricas del día agregadas** (P&L, R-ratio, etc.) — esas viven en un journal HTML externo separado
- **Sin chat integrado** con asistente LLM — el flujo es "copiar → pegar en app externa"
- **Sin sistema de alertas push** (notificaciones del OS, email, SMS) — todo es pull/visual dentro del cockpit

---

## 8 · Estados globales a diseñar

El DESIGNER debe producir mockups para cada pestaña en los siguientes estados:

### 8.1 Estado "operativo normal"
Todo funcionando, pilotos en verde, señales emitiéndose.

### 8.2 Estado "warmup"
Slot(s) descargando data histórica. Mostrar claramente el spinner + % de progreso en la card del slot afectado.

### 8.3 Estado "DEGRADED" parcial
Al menos un motor o slot en amarillo. El resto funciona. Piloto master amarillo. Mostrar dónde está el problema sin ser alarmista.

### 8.4 Estado "error fatal"
Un motor cayó (ej. Data Engine rojo por problema con provider). Scan no corre. Piloto master rojo. El trader necesita ver el problema y la acción recomendada.

### 8.5 Estado "loading"
Durante arranque automático (Auto-LAST) o tras una operación larga (restore desde S3, backup, Revalidar sistema). Splash screen / progress bar / feedback claro.

### 8.6 Estado "scan en curso"
Durante el segundo de scan (manual o automático). Indicador sutil de que algo se está procesando, las cards se actualizan al terminar.

### 8.7 Estado "señal S+ recién emitida"
Caso especial: una card pasa a S+ por primera vez en la sesión. Animación intensa en la letra "S+" + bordes de card + atrae la vista sin robar el foco si el trader está viendo otro slot.

### 8.8 Estado "modo AUTO apagado"
Toggle OFF. El banner de API cuenta lento. Las cards se actualizan solo al presionar scan manual. Indicar claramente que AUTO está apagado.

---

## 9 · Sistema de tipografía — criterios

Referencias de fuentes a evaluar por DESIGNER:
- **Sans-serif sobria** para texto general — familias como Inter, DM Sans, Geist Sans, Söhne (si licencia lo permite)
- **Monospace** para valores numéricos en el cockpit (scores, precios, timestamps) — JetBrains Mono, IBM Plex Mono, Geist Mono
- **Letterspacing generoso** en headers y labels clave (referencia icomat)
- **Preferencia por minúsculas** en labels cortas y categorías (referencia icomat)

Sin fuentes decorativas. Sin scripts. Sin serifs (el producto no tiene ese tono).

---

## 10 · Paleta de color — criterios

### Base
- **Fondo:** muy oscuro (negro o casi negro, puede tener textura video sutil estilo icomat, a evaluar)
- **Texto primario:** blanco puro o casi blanco
- **Texto secundario:** blanco al 60-70% de opacidad
- **Bordes/separadores:** blanco al 10-15%

### Pilotos (funcionales, no decorativos)
- **Verde operativo:** verde saturado pero no chillón (tipo `#22c55e` o similar)
- **Amarillo warning:** amarillo-naranja (tipo `#f59e0b`)
- **Rojo error:** rojo saturado (tipo `#ef4444`)
- **Gris inactivo:** gris frío neutro

### Bandas de confianza (colores de marca del producto)
- **REVISAR** — gris neutro
- **B** — azul claro
- **A** — azul más profundo
- **A+** — magenta con glow sutil
- **S** — dorado con glow marcado
- **S+** — negro metalizado con glow intenso + animación

La paleta de bandas de confianza es **diegética** — parte del producto, el trader aprende a leer las señales por color. Debe funcionar tanto para daltónicos (reforzar con iconos + labels, no depender solo de color) como visualmente distintiva.

### Acentos
Un acento cromático de marca a definir por el DESIGNER — se usa puntualmente (CTAs primarios, foco de elementos interactivos). Referencia icomat: suele ser un acento saturado pero sobrio.

---

## 11 · Componentes compartidos a diseñar

El DESIGNER debe producir los siguientes componentes reutilizables como parte del design system:

- **Card genérica** (variantes: motor/servicio, slot, tabla DB, patrón de Memento)
- **Piloto circular** (3 colores + estado warmup con spinner)
- **Barra de progreso horizontal** (variantes: créditos, retención DB, warmup, scan)
- **Dropdown técnico** (ticker, fixture, provider)
- **Toggle** (activo/inactivo, modo AUTO)
- **Botón primario / secundario / terciario / peligro** (jerarquía clara)
- **Badge de estado** con código de error (ej. "ENG-050")
- **Modal/drawer** para logs y detalle técnico expandido
- **Tooltip** sobrio
- **Tab navigation** entre las 4 pestañas principales
- **Splash/loading** para arranque Auto-LAST
- **Banner API horizontal** (Cockpit, componente custom)

---

## 12 · Responsive y dimensiones

- **Plataforma primaria:** desktop Windows (monitor 1920x1080 o 2560x1440 típicamente)
- **Ancho mínimo soportado:** 1440px
- **Sin responsive mobile** en v1 (el trader opera desde desktop — mobile es post-v5)
- **Layouts flexibles** para acomodar monitores más anchos (hasta 3840px ultrawide) sin perder usabilidad
- **Modo fullscreen** del Cockpit soportado (el trader puede querer maximizar el cockpit)

---

## 13 · Entregables esperados del DESIGNER

1. **Design system** (tokens de color, tipografía, spacing, radios, shadows)
2. **Mockups de las 4 pestañas** en estado "operativo normal"
3. **Mockups de estados críticos** (los 8 de sección 8)
4. **Componentes** (sección 11)
5. **Prototipo interactivo** (Figma prototype) del flujo principal: apertura → autoarranque → Cockpit → señal S+ emitida
6. **Especificaciones detalladas** (medidas, colores, interacciones) entregadas en formato exportable para el developer

---

## 14 · Qué NO debe hacer el DESIGNER

- **No** diseñar esquema de onboarding / tutorial / welcome — el producto es profesional, Álvaro conoce su herramienta
- **No** agregar gamificación (badges, achievements, streaks, etc.)
- **No** proponer temas claros además del oscuro (v1 solo oscuro)
- **No** agregar ilustraciones decorativas, mascotas, iconos coloridos sin función
- **No** proponer animaciones de scroll parallax, transiciones de página largas, efectos decorativos — animaciones sutiles y funcionales únicamente
- **No** modificar decisiones funcionales (estructura de pestañas, componentes obligatorios, flujos) — esos son contrato; el diseño visual es libre dentro de ese contrato
- **No** mezclar dos estilos separados (icomat y Runpod como estéticas alternativas). El producto es **un solo estilo (icomat)** con vocabulario estructural Runpod donde aplica — traducido a la paleta/tipografía icomat siempre.

---

## 15 · Contacto y workflow

- **Cliente:** Álvaro (decisor final en todas las decisiones estéticas)
- **Ciclo de feedback:** DESIGNER entrega primera ronda → Álvaro revisa → iteración
- **Prioridades:** legibilidad > estética, densidad funcional > minimalismo gratuito, sobriedad > efectos

---

**Fin del briefing principal.** El §16 que sigue es un anexo técnico con el contexto mínimo del backend que el DESIGNER necesita para dimensionar badges, estados push vs pull y microcomportamientos.

---

## 16 · Anexo técnico — superficie backend al 23-abril

**Propósito:** el DESIGNER no tiene que leer código, pero sí necesita saber **qué información está disponible, en qué forma (push vs pull) y qué códigos caben en un badge.** Este anexo aporta ese contexto mínimo sin exigir jerga de implementación.

### 16.1 Push vs pull — qué se actualiza solo y qué se consulta

El backend emite **6 eventos en tiempo real** que el frontend recibe por WebSocket. Saber qué vista depende de cuál evento es clave para decidir animaciones, transiciones y refresh rates.

| Evento | Vista que alimenta | Frecuencia típica |
|---|---|---|
| `signal.new` | Watchlist del Cockpit (card pasa a nueva banda) + panel derecho si el slot está seleccionado | 1 cada 15 min por slot activo durante sesión de mercado |
| `slot.status` | Piloto + label de card en Dashboard y watchlist del Cockpit | Puntual (warmup, enable/disable, degraded, recovery) |
| `engine.status` | Piloto Master del Dashboard + pilotos individuales de motor | Cada 2 min (heartbeat + healthcheck del Scoring) |
| `api_usage.tick` | Banner superior global del Cockpit — 5 barras + barra diaria | Cada cierre de ciclo (15 min en AUTO, o al `Scan ahora`) |
| `validator.progress` | Progress bar del Paso 4 de Configuración + sub-panel del Validator | Por cada test A-G (2 eventos: started/finished) |
| `system.log` | Drawer "Ver log" de cada motor en Dashboard | Por cada entrada nueva de log |

**Todo lo demás se consulta bajo pedido** (pull) cuando el usuario abre una pestaña, presiona un botón o expande una sección:
- Histórico de señales (Memento, REST).
- Histórico de reportes Validator (Dashboard §4, REST).
- Stats de DB (Dashboard §3, REST + refresh manual).
- Lista de backups S3 (Dashboard §3, REST + refresh manual).
- Stats por slot de Memento (REST al expandir cada slot).

**Implicación para el DESIGNER:** las vistas que dependen de WS necesitan **indicador de conexión WS** en alguna esquina discreta del cockpit — si la conexión cae, el trader debe saberlo para no confiar en data stale. Un icono pequeño "conectado / reconectando / desconectado" es suficiente.

### 16.2 Endpoints REST disponibles

Resumen de qué API se consume para cada pestaña. El DESIGNER no necesita memorizarlos, pero sí saber que todos estos datos existen y se pueden mostrar.

| Pestaña | Datos consumidos (pull) |
|---|---|
| **Configuración** | Config activo + lista de Configs guardados · slots configurados · fixtures disponibles · canonicals por ticker · API keys actuales · estado de cada motor para arranque secuencial |
| **Dashboard** | Estado de cada motor + memoria + último heartbeat · stats por tabla DB · tamaño total DB · último reporte Validator · histórico Validator paginado · lista de backups S3 |
| **Cockpit** | Última señal por slot · config de slots activos · banner API en vivo |
| **Memento** | Métricas por slot (WR, spread, uplift por confirm, thresholds) · catálogo de patrones con stats globales |

### 16.3 Códigos de error conocidos — diccionario para badges

Cuando un piloto no es verde, el componente badge muestra un código técnico + descripción corta. La lista de códigos posibles hoy:

| Código | Gravedad | Significado humano | Dónde puede aparecer |
|---|---|---|---|
| `ENG-001` | Rojo | Motor crasheó, no puede operar | Piloto Master + piloto del motor caído |
| `ENG-050` | Amarillo | Parity check del Scoring detectó drift | Piloto Scoring Engine (Dashboard) |
| `ENG-060` | Amarillo | Slot degraded tras 3 fallos consecutivos de fetch | Piloto de card de slot (Dashboard + Cockpit) |
| `REG-011` | Amarillo | Fixture sin campo obligatorio | Modal de carga de fixture (Paso 3 Config) |
| `REG-012` | Amarillo | Fixture incompatible con ticker | Modal de carga de fixture (Paso 3 Config) |
| `REG-013` | Amarillo | Benchmark inválido | Modal de carga de fixture (Paso 3 Config) |
| `REG-020` | Rojo | Canonical hash no coincide (fixture corrupta) | Validator Check B + card de slot afectado |
| `FIX-xxx` | Amarillo | Errores genéricos de carga de fixture (archivo malformado, JSON inválido, etc.) | Modal de carga de fixture (Paso 3 Config) |

**Implicación para el DESIGNER:**
- Badge de código debe soportar strings de hasta **~20 caracteres** (`ENG-060 · Slot degraded` o similar).
- Convención: prefijo del código en fuente monospace, descripción en sans-serif. Color del badge según gravedad (amarillo/rojo).
- Todos los códigos son expandibles — al hover/click muestran el mensaje completo en tooltip o drawer.

### 16.4 Estados autónomos del sistema (sin intervención del usuario)

Hay 3 situaciones en las que el sistema **cambia de estado solo**, sin que el trader haga nada. El diseño debe contemplar transiciones suaves en estos casos:

1. **Scoring Engine healthcheck** (§5 Sección 1): piloto del Scoring puede oscilar verde ↔ amarillo ENG-050 cada ~2 min según mini parity test.
2. **Slot degraded** (§5 Sección 2): tras 3 fallos consecutivos de fetch, un slot pasa a DEGRADED (amarillo ENG-060). Si recupera, vuelve a verde solo.
3. **Watchdog agresivo** (§5 Sección 3): si está activado, puede disparar rotación sola al cruzar el límite de tamaño DB. La barra de tamaño baja en vivo.

Todas estas transiciones deberían usar **fade entre colores** (~300-500ms), no saltos duros. El usuario no está mirando el Dashboard en todo momento — cuando vuelva debe ver el nuevo estado sin que "parpadee" delante suyo.

### 16.5 Nota sobre credenciales sensibles (ONLINE BACKUP y API keys)

En v1 del frontend, los campos de secret key / access key / API key se envían al backend cuando el usuario los guarda. El backend los persiste **encriptados en disco** (no en texto plano) con una master key local.

Implicaciones para el DESIGNER:
- Los campos deben tener toggle "mostrar/ocultar" como ya está en el spec.
- Cuando el usuario vuelve a abrir la pestaña, el valor **no se muestra aunque presione "mostrar"** — queda enmascarado con `••••••••` y un hint "credencial guardada — editá para reemplazar". Esto es por seguridad (el backend no devuelve secretos ya persistidos, solo los acepta al guardar).
- Si el usuario presiona un campo "mostrar" sobre un valor que **acaba de tipear** (antes de guardar), ve el valor en claro normalmente. La ocultación aplica solo post-persistencia.

### 16.6 Convenciones temporales

- **Zona horaria:** todos los timestamps visibles al usuario son **ET (Eastern Time)**, no UTC ni local. El trader opera en horario de mercado US. Convención: mostrar `14:30 ET` o `2026-04-23 14:30 ET`.
- **Reset del contador diario de API** (Cockpit banner): a las **16:00 ET** (cierre de mercado), no a medianoche UTC.
- **Warmup / revalidación / scan:** duraciones típicas son **segundos a decenas de segundos** — progress bars y spinners, no operaciones largas.
- **Backup S3 / VACUUM / Restore:** operaciones de **minutos** — progress bar grande + mensaje claro de que bloquea otras operaciones durante el run.

---

## 17 · Changelog del briefing

**v2.1.0 — 2026-04-23**
- Agregado §16 anexo técnico completo (push vs pull, endpoints, códigos de error, estados autónomos, convenciones temporales).
- §4 Paso 3 · agregado estado "revalidando" tras cambios en el registry de slots.
- §5 Sección 1 · nota sobre healthcheck continuo del Scoring Engine (piloto puede cambiar solo cada 2 min).
- §5 Sección 3 · barra de tamaño total DB + nota sobre watchdog agresivo opt-in + badge VACUUM recomendado.
- §5 Sección 4 · histórico de reportes Validator (drawer navegable) + trigger badge en el último reporte.
- §7.6 · clarificación del toggle Modo AUTO + nota sobre decisión técnica abierta (visual vs real).

**v2.0.0 — 2026-04-20**
- Briefing principal cerrado: estilo (icomat + Runpod estructural), 4 pestañas completas, Cockpit v2 con panel derecho de 3 zonas + botón COPIAR.

---

**Fin de `SCANNER_V5_FRONTEND_FOR_DESIGNER.md` v2.1.0.**

**Nota final para el lector:** las decisiones estéticas del briefing principal (§1–§15) están cerradas. El anexo técnico §16 es contexto informativo sobre el backend — no cambia decisiones de diseño ya tomadas, solo las dota de fundamento operativo. Si aparece una duda estética nueva durante la ejecución del diseño, DESIGNER la consulta con Álvaro en el ciclo de feedback.
