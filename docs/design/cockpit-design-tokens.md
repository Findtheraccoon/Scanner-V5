# Cockpit — Design Tokens v0.1

> **Propósito:** propuesta inicial de design system para el Cockpit del Scanner v5, destilada de:
> - **icomat.co.uk** (base visual + tipografía + vibe aeroespacial sobrio)
> - **runpod.io** (sistema diagramático: cards con bordes de acento, conectores con pines)
> - **Wireframe A** `frontend/wireframing/Cockpit Wireframes.html` (distribución + acento lima)
> - **Brief v2.1.0** `docs/specs/SCANNER_V5_FRONTEND_FOR_DESIGNER.md`
>
> Este archivo es para revisión de Álvaro. Una vez aprobado, se traduce a `tailwind.config.ts` + variables CSS + componentes shadcn custom.

**Estado:** propuesta · **Fecha:** 2026-04-23 · **Alcance:** Cockpit (pestaña 3). Las otras 3 pestañas se diseñan después reutilizando estos tokens.

---

## 1 · Filosofía destilada

- **Oscuro profundo, fotográfico.** El Cockpit vive en pantalla durante 6h al día — el fondo tiene que descansar la vista y dejar que la tipografía y los datos sean los protagonistas. Negro como el de icomat, no gris oscuro.
- **Jerarquía por peso y tamaño, no por color.** icomat no usa color para jerarquizar — usa el tamaño del display + contraste con el fondo. Replicamos esto: score grande = peso heavy, labels = small + letterspacing amplio + muted.
- **Acento único funcional.** El acento lima `#9cc80a` del wireframe A aparece **solo cuando importa** (CTA primario, banda S, glow de S+, cable activo en el canvas de slots del Paso 3 de Config). El resto del producto es monocromo oscuro.
- **Monospace para valores numéricos.** Todos los precios, scores, timestamps, ratios y porcentajes van en mono — alinea visualmente y transmite "dato técnico confiable".
- **Runpod estructural, icomat visual.** Cuando aparecen cards conectadas (canvas del Paso 3, sistema de motores del Dashboard), usamos el **patrón** de Runpod (card + pines + línea recta) pero con la **paleta** icomat (acento lima en vez de violeta, fondo negro en vez de oscuro-violeta).

---

## 2 · Paleta

### 2.1 Fondos y superficies

| Token | Hex | Uso |
|---|---|---|
| `--bg-0` | `#050505` | Fondo raíz del cockpit (lo que ve el trader la mayor parte del tiempo) |
| `--bg-1` | `#0a0a0a` | Bandas sticky (banner API arriba, banner del panel del slot seleccionado) |
| `--bg-2` | `#111111` | Fondo de cards en estado selected / hover sutil |
| `--bg-3` | `#1a1a1a` | Fondo de `<input>`, dropdowns, modales |

Motivación: los 4 niveles dan profundidad sin salir del negro. icomat trabaja así — fondo absoluto + matices casi imperceptibles en las capas.

### 2.2 Texto

| Token | Hex | Uso |
|---|---|---|
| `--text-0` | `#ffffff` | Texto primario (ticker, score, valores) — 95-100% opacidad |
| `--text-1` | `rgba(255,255,255,0.70)` | Texto secundario (descripciones cortas, sub-labels) |
| `--text-2` | `rgba(255,255,255,0.45)` | Muted (timestamps, metadata, placeholders) |
| `--text-3` | `rgba(255,255,255,0.25)` | Deshabilitado / valores vacíos / separadores textuales |

### 2.3 Bordes y separadores

| Token | Hex | Uso |
|---|---|---|
| `--border-0` | `rgba(255,255,255,0.08)` | Separadores entre secciones, bordes de cards no seleccionadas |
| `--border-1` | `rgba(255,255,255,0.15)` | Cápsulas de nav (icomat-style), bordes de inputs en reposo |
| `--border-2` | `rgba(255,255,255,0.30)` | Borde de card seleccionada cuando no hay banda dominante |

### 2.4 Acento único

| Token | Hex | Uso |
|---|---|---|
| `--accent` | `#a8d820` | Acento lima del wireframe A, ligeramente ajustado para mejor contraste sobre negro (ratio 10.5:1 vs `#9cc80a` que da 9.1:1) |
| `--accent-dim` | `rgba(168,216,32,0.25)` | Glow sutil (borde de card S+, fill de progress bar activa) |
| `--accent-strong` | `#c3f030` | Hover del CTA primario |

**Decisión abierta para Álvaro:** ¿mantenemos el `#9cc80a` exacto del wireframe, o bajamos a `#a8d820` por contraste? Visual casi idéntico, accesibilidad sube.

### 2.5 Pilotos funcionales (estados de sistema)

| Token | Hex | Uso |
|---|---|---|
| `--pilot-ok` | `#22c55e` | Verde operativo (motor corriendo, slot activo). Inspirado en runpod "Ready" |
| `--pilot-warn` | `#f59e0b` | Warmup, DEGRADED (ENG-060), parity drift (ENG-050), VACUUM recomendado |
| `--pilot-err` | `#ef4444` | Error fatal (ENG-001), motor caído |
| `--pilot-idle` | `rgba(255,255,255,0.25)` | Slot inactivo, key no configurada. Monocromo (no color) |

Los pilotos son **los únicos elementos saturados del producto**. Todo lo demás vive en la paleta oscura + acento lima. Eso los hace imposibles de ignorar cuando cambian — que es exactamente lo que querés con un alert operativo.

### 2.6 Bandas de confianza (diegéticas)

Siguiendo el wireframe A, las bandas se resuelven principalmente por **contraste tinta/papel invertido** (blanco/negro) y no con paleta saturada. Solo la `S` usa el acento lima.

| Banda | Tratamiento | Motivación |
|---|---|---|
| `REVISAR` | Border dashed `--text-2` · sin fill · texto `--text-2` | Señal débil — se ve "pendiente", no grita |
| `B` | Fill `--bg-2` · borde `--border-1` · texto `--text-0` | Señal base — discreta |
| `A` | Fill `--text-0` · texto `--bg-0` (invertido) | Primera banda "ganadora" — tipografía en negativo como callout de icomat |
| `A+` | Fill `--text-0` · texto `--bg-0` · border dashed `--accent-dim` 2px ofsetado | Callout + dashed offset estilo diagrama técnico |
| `S` | Fill `--accent` · texto `--bg-0` · border sólido `--text-0` | Primera banda que usa el acento — glow leve |
| `S+` | Fill `--bg-0` · texto `--text-0` · doble ring (inner `--bg-0`, outer `--text-0`) + glow animado `--accent` | Máxima solemnidad — negro metalizado con doble borde + pulse |

**Animación S+:** pulse 1.8s ease-in-out infinite sobre el borde outer + letterspacing del label oscila 0.20em → 0.26em. Sobria — no flash. Patrón `pulseBorder` y `pulseText` del wireframe A, mismos timings.

### 2.7 Direcciones (CALL / PUT)

Se muestran en cápsulas con border `--border-1`, fondo transparente, texto mono `--text-0`. No usan color rojo/verde para evitar chocar con la paleta de pilotos. El trader identifica dirección por la palabra, no por color — es menos invasivo y más riguroso.

---

## 3 · Tipografía

### 3.1 Familias

| Token | Familia | Uso |
|---|---|---|
| `--font-display` | **GT America** o **Söhne** (premium) → fallback **Inter** (gratuito, muy cercano visualmente) | Display grande: ticker del banner, score numérico, título del cockpit |
| `--font-ui` | **Inter** (regular/medium/semibold) | Todo el texto UI: labels, botones, descripciones, badges |
| `--font-mono` | **JetBrains Mono** o **IBM Plex Mono** | **Todos los valores numéricos**: precios, scores, ratios, timestamps, códigos de error |

**Decisión abierta:** ¿Inter para display también (gratuito, excelente, se parece mucho al hero de icomat)? O pagamos licencia de GT America / Söhne para el matiz premium? Inter cubre el 95% del vibe — mi recomendación arrancar con Inter y ver si falta algo después.

### 3.2 Escala tipográfica

| Token | Tamaño | Peso | Letterspacing | Case | Uso |
|---|---|---|---|---|---|
| `--t-display-xl` | 44px | 700 | -0.02em | sentence | Ticker grande del banner del panel |
| `--t-display-lg` | 36px | 600 | -0.01em | sentence | Score numérico del banner |
| `--t-display-md` | 28px | 700 | 0 | sentence | Ticker en cards de watchlist |
| `--t-body-lg` | 16px | 500 | 0 | sentence | Valores del resumen ejecutivo |
| `--t-body` | 14px | 400 | 0 | sentence | Texto general |
| `--t-body-sm` | 13px | 500 | 0 | sentence | Valores de detalle técnico |
| `--t-label` | 11px | 500 | **0.18em** | UPPERCASE | Labels de sección (PRECIO, CONTEXTO, VOLUMEN) |
| `--t-label-sm` | 10px | 500 | 0.14em | UPPERCASE | Metadata de card (timestamp) |
| `--t-mono-lg` | 22px | 600 | 0 | — | Score en cards de watchlist |
| `--t-mono` | 13px | 400 | 0 | — | Valores numéricos del resumen + detalle |
| `--t-mono-sm` | 11px | 400 | 0.04em | — | Timestamps, metadata |
| `--t-btn` | 12px | 600 | **0.22em** | UPPERCASE | Botón COPIAR (el CTA primario del banner) |
| `--t-btn-sm` | 11px | 500 | 0.12em | UPPERCASE | Botones secundarios (SCAN AHORA, VER DETALLE) |

**El letterspacing amplio en labels y botones es el gesto icomat más identificable.** Lo aplicamos consistentemente.

---

## 4 · Spacing y radius

### 4.1 Spacing scale (escala en 4px base)

```
xs  = 4px   sm = 8px    md = 12px   lg = 16px
xl  = 24px  2xl = 32px  3xl = 48px  4xl = 64px
```

Usar consistentemente:
- Gap entre cards de watchlist: `sm` (8px)
- Padding interno de cards: `md` (12px) o `lg` (16px) según densidad
- Separación entre bloques del detalle técnico: `lg` (16px)
- Padding del banner del panel: `lg 2xl` (16px 32px)

### 4.2 Radius

| Token | Valor | Uso |
|---|---|---|
| `--r-none` | `0` | Banners, strips horizontales (banner API arriba, ctrl-strip) — icomat no usa radius en estructura principal |
| `--r-sm` | `4px` | Inputs, cápsulas de nav, badges de dirección |
| `--r-md` | `8px` | Cards de watchlist, cards del detalle técnico |
| `--r-lg` | `12px` | Modales, drawers |

Radios **conservadores** — el vibe icomat no es rounded, es más angular/industrial.

---

## 5 · Elementos estructurales

### 5.1 Card de watchlist (columna izquierda del Cockpit)

```
┌─────────────────────────────┐  ← border-1 (0.15 alpha)
│ QQQ                   CALL  │
│                             │
│ 12.0                   A+   │
│                             │
│ 14:30 ET · vela cerrada     │  ← text-2 timestamp
└─────────────────────────────┘
```

- Background: `--bg-0` normal · `--bg-2` cuando `selected`
- Border: `--border-1` normal · `--text-0` 2px cuando `selected` · `--accent` 2.5px pulsante cuando estado `splus`
- Padding: 12px
- Radius: `--r-md` (8px)
- Hover: `--border-1` → `--border-2`, cursor pointer
- Piloto absoluto: top-right, 8px round, fill según `--pilot-*`

### 5.2 Banner del panel derecho (sticky)

```
┌─────────────────────────────────────────────────────────────┐
│ QQQ   [A+]  CALL   12.0        ┌─ SCAN AHORA ──┐ ⊙ AUTO │ COPIAR │
│                    score                                      │
└─────────────────────────────────────────────────────────────┘
```

- Background: `--bg-1`
- Border bottom: `--border-0`
- Padding: `16px 32px`
- Ticker: `--t-display-xl`
- Banda: según §2.6
- Botón `COPIAR`: primary (fill `--accent`, text `--bg-0`), `--t-btn`, radius `--r-sm`
- Botón `SCAN AHORA`: secondary (border `--border-2`, text `--text-0`), `--t-btn-sm`
- Toggle AUTO: `--text-1` label + track `--border-1` + thumb `--accent` cuando on

### 5.3 Resumen ejecutivo (debajo del banner, siempre visible)

Grid 2 columnas · `gap: 6px 32px` · `--t-mono` para valores · `--t-body-sm` para labels en `--text-2`.

```
precio        $485.32  (+0.82%)     │ ATR 15M       0.74% · $3.59
alineación    3/3 bull · 15M·1H·D   │ dMA200        +3.2%
vela          14:30 ET · calc +4s   │ bench (SPY)   +0.41% · div +0.41pp

[⚡ squeeze 1H] [↑ ORB breakout] [⚠ catalizador] [↗ fza rel extrema]
```

Los flags son cápsulas con `--t-label` (mayúsculas + letterspacing pero tamaño 10px para no gritar), border `--border-1`, fondo transparente, padding `2px 8px`.

### 5.4 Detalle técnico (card-grid de Variant B o tabla 2-col de Variant A)

Alvaro eligió Variant A del wireframe como base. El detalle va en **tabla 2 columnas** (`140px | 1fr`) con:
- Headers de bloque (`--t-label`) en columna izquierda, alineados con el contenido
- Valores en columna derecha con líneas en `.line`: `label (text-2) ····· value (text-0)` separador invisible con `justify-content: space-between`
- Border bottom entre bloques: `--border-0` 1px

### 5.5 Banner superior global de API (sticky arriba del Cockpit)

```
┌────────────────────────────────────────────────┬─────────────────┐
│ 5 barras horizontales (créditos/min)            │  Barra diaria   │
│ ┃key1  6/8┃ ┃backup 2/8┃ ┃res-a 0/8┃ ┃—┃ ┃—┃   │  598/2400 ▓▓▒  │
│  hace 3s    hace 47s      —            sin conf │  reset 16:00 ET │
└────────────────────────────────────────────────┴─────────────────┘
```

- 5 barras: grid 5col, cada una con label mono + valor mono + progress bar horizontal fill `--text-0` sobre track `--bg-2`
- Barra diaria: highlight con fondo `--bg-1` + border `--border-1`
- Cuando un key pasa `70%` de créditos/min: fill pasa a `--pilot-warn`
- Cuando pasa `90%`: fill `--pilot-err`

### 5.6 Chart (Lightweight Charts local)

- Container border: `--border-0`
- Candles: up `--text-0` outline + fill transparent, down `--text-0` fill sólido (estilo icomat — sin verde/rojo para no competir con pilotos)
- MAs como líneas con stroke `--text-1` (MA20), `--text-2` (MA40), `--border-2` (MA200)
- BB: fill entre bandas con `rgba(255,255,255,0.03)`, stroke `--text-2`
- Overlay de volumen: bars con opacidad 0.3
- Label "Abrir en TradingView" como text button pequeño arriba a la derecha

**Decisión abierta:** ¿candles up/down en blanco/negro (estilo icomat riguroso) o up=accent / down=texto? Lo primero es más coherente con la paleta, lo segundo es más rápido de leer. Mi recomendación: **blanco/negro** y el trader lee dirección por la banda CALL/PUT en el banner (no por el color del candle).

---

## 6 · Microinteracciones

| Evento | Animación |
|---|---|
| Selección de card de watchlist | `bg` + `border-color` transition 150ms ease-out |
| Cambio de estado de piloto (verde↔amarillo) | `bg-color` transition **500ms ease-in-out** (fade suave, no salto — por el healthcheck autónomo del §16.4) |
| Señal S+ emitida | Pulse 1.8s infinite en borde outer de la card + letterspacing del label (según §2.6) |
| Botón COPIAR presionado | `bg` pasa a `--accent-strong` + label "COPIAR" → "✓ COPIADO" por 1400ms |
| Toggle AUTO | `background` + `thumb position` transition 200ms |
| Scan en curso | Progress bar indeterminada 800ms loop en el banner API |
| WS desconectado | Icono esquina con `pilot-warn` + label "reconectando…" fade in 300ms |

Todas las animaciones usan `ease-in-out` o `ease-out`, nunca `ease-in` (ese genera sensación de "reluctancia"). Duraciones entre 150ms y 500ms — nada más largo excepto el pulse S+ (1.8s por diseño).

---

## 7 · Traducción a Tailwind (preview)

```ts
// tailwind.config.ts (fragmento)
export default {
  theme: {
    colors: {
      bg: { 0: '#050505', 1: '#0a0a0a', 2: '#111111', 3: '#1a1a1a' },
      text: {
        0: '#ffffff',
        1: 'rgba(255,255,255,0.70)',
        2: 'rgba(255,255,255,0.45)',
        3: 'rgba(255,255,255,0.25)',
      },
      border: {
        0: 'rgba(255,255,255,0.08)',
        1: 'rgba(255,255,255,0.15)',
        2: 'rgba(255,255,255,0.30)',
      },
      accent: { DEFAULT: '#a8d820', dim: 'rgba(168,216,32,0.25)', strong: '#c3f030' },
      pilot: { ok: '#22c55e', warn: '#f59e0b', err: '#ef4444', idle: 'rgba(255,255,255,0.25)' },
    },
    fontFamily: {
      display: ['Inter', 'system-ui', 'sans-serif'], // o GT America si pagamos
      ui: ['Inter', 'system-ui', 'sans-serif'],
      mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
    },
    // spacing, borderRadius, fontSize, letterSpacing se expanden desde §4 y §3.2
  },
};
```

---

## 8 · Preguntas abiertas para Álvaro

1. **Acento exacto:** ¿`#9cc80a` del wireframe o `#a8d820` por contraste accesible?
2. **Display font:** ¿Inter (gratuito, 95% del vibe) o pagamos GT America / Söhne para el matiz premium?
3. **Candles del chart:** ¿blanco/negro rigurosos (estilo icomat) o up=accent / down=texto?
4. **Intensidad del pulse S+:** el wireframe A tiene un pulse 1.8s. ¿Te cuadra el timing o querés más lento/más rápido?
5. **Fondo absoluto negro (`#050505`) o muy leve desaturado (`#080a0c` con tinte azul imperceptible tipo runpod)?** El primero es más icomat, el segundo es más runpod. Mi recomendación: `#050505` (icomat wins según el brief).

---

## 9 · Próximos pasos (cuando esto se apruebe)

1. Convertir este md a `tailwind.config.ts` + `src/styles/tokens.css` con CSS variables.
2. Scaffolding Vite + instalación del stack (shadcn, TanStack Query, Zustand).
3. Construcción del shell del Cockpit:
   - Layout de 3 zonas (banner API global + watchlist izq + panel derecho)
   - Banner del panel con ticker + banda + botones
   - Watchlist con 6 cards mockeadas
   - Estado `splus` con pulse animado
4. Conexión al backend (REST + WS `signal.new` + `api_usage.tick` + `slot.status`).
5. Chart con Lightweight Charts + datos del slot seleccionado.
6. Iteración visual en vivo con Álvaro.

---

**Fin de `cockpit-design-tokens.md v0.1`.**
