# ADR-0007: Lenguaje visual — icomat como base, Runpod como vocabulario estructural

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

El Scanner v5 tiene 4 pestañas frontend con funciones distintas:

- **Configuración:** setup inicial, API keys, canvas de asignación de slots con nodo-conexión, arranque de motores. Alta densidad informacional en el Paso 3.
- **Dashboard:** panel admin del sistema. Estado de motores, slots, tablas de DB, validaciones. Densidad alta.
- **Cockpit:** pantalla operativa del trader durante 6 horas de sesión. Foco, minimalismo, disclosure progresiva. Una señal a la vez, lo importante arriba.
- **Memento:** consulta analítica. Stats por slot, catálogo de patrones. Baja densidad, lectura tranquila.

Durante las sesiones de diseño se consideraron dos referencias visuales distintas:

- **[runpod.io](https://runpod.io):** UI técnica con nodo-conexión, iconos de sistema, diagramas estructurales, cards densas, paleta fría azul-tech.
- **[icomat.co.uk](https://icomat.co.uk):** estética oscura industrial, sobria y limpia, paleta negra con acentos sutiles, tipografías sobrias en minúscula, letterspacing generoso, backgrounds discretos, cards minimalistas.

Versiones previas del `FRONTEND_FOR_DESIGNER.md` (v1.0.0) dejaban abiertas 5 dudas estéticas que bloqueaban la entrega al diseñador. La más importante era "cómo se combinan ambas referencias" — con opciones X (Cockpit icomat + resto Runpod), Y (todo icomat), Z (híbrido por pestaña).

Durante la sesión del 20-abril, Álvaro planteó una formulación distinta que cierra las 5 dudas de una vez.

## Decisión

El lenguaje visual del Scanner v5 se define como:

> **icomat es el lenguaje base del producto entero** (las 4 pestañas).
> **Runpod aporta vocabulario estructural** (patrones de nodo-conexión, iconos de sistema, diagramas) **donde la función lo requiere**.
> **No son dos estilos conviviendo.** Es **un solo estilo** (icomat) con componentes estructurales prestados de Runpod **traducidos a la paleta/tipografía icomat**.

### Implementación concreta

**Aplicación transversal (las 4 pestañas):**
- Paleta negra profunda + blanco/blanco atenuado + un acento cromático único de marca (a definir por DESIGNER).
- Tipografías sans-serif sobrias. Headers y labels en minúscula con letterspacing generoso.
- Bordes al 10-15% de opacidad.
- Cards minimalistas.
- Backgrounds discretos (pueden incluir video sutil estilo icomat, a evaluar en Cockpit).
- Animaciones funcionales, nunca decorativas.

**Componentes estructurales Runpod (donde aplica):**
- **Paso 3 Configuración:** canvas nodo-conexión para asignación de slots. Usa el patrón Runpod pero con fondo, tipografía y colores icomat.
- **Dashboard:** iconos técnicos de motores/slots/servicios, diagramas de estado. Densidad manejada con jerarquía tipográfica + spacing icomat, no con color saturado.
- **Cockpit y Memento:** no tienen vocabulario Runpod. Icomat puro.

**Animaciones de bandas de confianza (Cockpit):**
- REVISAR / B / A / A+: glows progresivamente más fuertes, dentro del lenguaje sobrio icomat.
- S: dorado con glow marcado.
- S+: negro metalizado + glow + **pulse lento** (no flash) en la letra "S+" y en los bordes de la card. Disonancia intencional aceptada — la señal S+ debe gritar — pero dentro del lenguaje sobrio del producto.

## Consecuencias

### Positivas

- **Coherencia total:** el producto se siente "una cosa" aunque cada pestaña tenga función distinta.
- **Densidad no compromete estética:** Dashboard/Configuración mantienen el lenguaje base con vocabulario estructural prestado; no hay cambio de "modo visual" al navegar entre pestañas.
- **DESIGNER recibe un briefing único:** icomat base + Runpod como patrón estructural subordinado. No tiene que elegir entre dos estéticas ni inventar un híbrido.
- **Cierre de las 5 dudas de la sesión:** la formulación resuelve densidad, animaciones, ámbito, y elimina la tensión Runpod vs icomat al declarar que no son opciones paralelas.
- **Extensible:** si aparece una pestaña o componente nuevo, la regla es clara: usa icomat; si requiere patrón estructural, toma el de Runpod y tradúcelo.

### Negativas / trade-offs

- Pone trabajo adicional al DESIGNER: tiene que entender las dos referencias y "traducir" el vocabulario Runpod (colores azul-tech, tipografías técnicas) al idioma icomat (paleta negra, tipografía sobria). Mitigado: es trabajo creativo normal, no carga excesiva.
- Runpod ya no aparece en las 4 pestañas de forma uniforme (decisiones previas mencionaban Runpod en varias). Se reemplaza por "Runpod solo donde la función lo pide". Requiere reescribir partes del briefing al DESIGNER.
- Riesgo de inconsistencia si el DESIGNER interpreta mal el "traducir". Mitigado: icomat.co.uk queda como referencia primaria explícita; Runpod secundaria solo para patrones estructurales.

### Neutras

- Animaciones S+/S/A+/A quedan definidas pero pueden refinarse con el DESIGNER.

## Alternativas consideradas

### Alternativa X: Cockpit 100% icomat + resto 100% Runpod

Dos estéticas separadas por pestaña, contraste deliberado entre operación contemplativa (Cockpit) y admin denso (resto).
**Por qué no:** rompe la sensación de producto único. El trader cambia de "modo visual" al ir de Cockpit a Dashboard — disruptivo en sesiones largas. Pone el peso de la coherencia en el DESIGNER (tiene que hacer dos design systems).

### Alternativa Y: Todo el scanner 100% icomat, sin Runpod

Coherencia total, pero Dashboard y Configuración Paso 3 quedan sin herramientas para manejar la densidad.
**Por qué no:** el canvas de slots de Paso 3 literalmente necesita un patrón nodo-conexión; inventarlo desde icomat puro es trabajo extra sin referencia clara. Dashboard con 6 motores + 6 slots + 6 tablas DB pide iconografía funcional; icomat puro lo haría muy espaciado o confuso.

### Alternativa Z: Híbrido por pestaña — icomat Cockpit + Memento, Runpod Configuración + Dashboard

Por función: pestañas "operativas/contemplativas" en icomat, pestañas "de control/densas" en Runpod.
**Por qué no:** variante más fina de X, mismos problemas. El trader sigue viendo dos estéticas al navegar. No resuelve la pregunta de por qué icomat para Memento sí y no para Configuración (ambas tienen tarjetas, pocas acciones, contemplativas).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §6.5 (Pestaña Cockpit — Decisión estética del producto W).
- `docs/operational/FRONTEND_FOR_DESIGNER.md` §2 (Referencias visuales — icomat base + Runpod estructural).
- [icomat.co.uk](https://icomat.co.uk) — referencia estética primaria.
- [runpod.io](https://runpod.io) — referencia de patrones estructurales.
