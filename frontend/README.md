# Frontend

App React del Scanner v5.

**Stack:** Vite 5 + React 18 + TypeScript strict + Tailwind 3 (con plugin custom Phoenix) + Zustand 5 + TanStack Query 5 + React Router 6.
**Toolchain:** pnpm + Biome + Vitest + jsdom + @testing-library/react.

---

## Comandos

```bash
cd frontend
pnpm install        # primera vez

pnpm dev            # vite dev server en http://localhost:5173
pnpm build          # tsc -b && vite build → dist/
pnpm preview        # sirve dist/ para verificar el build de producción

pnpm test           # vitest --run
pnpm test:watch     # vitest watch
pnpm lint           # biome check (lint + format check + organize imports)
pnpm lint:fix       # biome check --write
pnpm format         # biome format --write
```

El dev server proxyea `/api` y `/ws` a `VITE_BACKEND_URL`
(default `http://localhost:8000`), así que basta con tener el backend
corriendo (ver `backend/README.md`) para que la UI se conecte sola sin
CORS ni configuración adicional.

```bash
# arrancar el backend
SCANNER_API_KEYS="sk-dev" \
SCANNER_TWELVEDATA_KEYS="k1:sk-td-1:8:800" \
SCANNER_REGISTRY_PATH="slot_registry.json" \
python backend/main.py

# y en otro terminal el frontend
cd frontend && pnpm dev
```

---

## Estado

Scaffolding inicial **listo** (PR de ejecución del Cockpit Hi-Fi v2 a React).

Lo que está montado:

- **Toolchain:** Vite + React 18 + TypeScript strict (`tsc -b` limpio).
- **Estilos:** tokens Phoenix completos (`src/styles/tokens.css`) + plugin
  Tailwind custom con utilities `glass-*`, `tier-*`, `bookmark-shape`,
  `iridescent-*`, `num-tabular`. CSS del shell + cockpit portados verbatim
  del prototipo `wireframing/Cockpit Hi-Fi v2.html` para preservar 1:1 el
  rendering.
- **Router:** 4 pestañas (`/configuracion`, `/dashboard`, `/cockpit`,
  `/memento`) con `AppShell` compartido (health-line + topbar + apibar +
  Outlet + footer). `/` redirige a `/cockpit`.
- **Cockpit:** watchlist con 6 slots (5 cargados + 1 vacío) + panel
  derecho (banner sticky + resumen ejecutivo + chart estático + detalle
  técnico colapsable). Datos hardcoded del Hi-Fi v2; los selectores CSS
  matchean 1:1.
- **Stub pages** para Configuración / Dashboard / Memento, listos para
  reemplazar cuando lleguen los hi-fi.
- **API client base** (`src/api/client.ts`) con bearer token opcional.
- **Tests smoke (6/6 passing)** que verifican router + stubs + shell + cockpit.

---

## Estructura

```
frontend/
├── public/                    # assets servidos tal cual
├── src/
│   ├── api/                   # cliente HTTP + (futuro) hooks TanStack
│   ├── components/
│   │   └── AppShell/          # health-line + topbar + apibar + footer
│   ├── pages/
│   │   ├── Cockpit/           # watchlist + panel + cockpit.css
│   │   ├── Configuration/     # stub
│   │   ├── Dashboard/         # stub
│   │   ├── Memento/           # stub
│   │   └── _stub/             # plantilla común para los 3 stubs
│   ├── stores/                # (futuro) Zustand
│   ├── styles/
│   │   ├── tokens.css         # paleta Phoenix + radii + tipografías
│   │   ├── global.css         # reset + body atmosphere + health-line
│   │   └── shell.css          # topbar + apibar + footer (compartido)
│   ├── test/
│   │   ├── setup.ts           # @testing-library/jest-dom
│   │   └── router.test.tsx    # smoke del router + páginas
│   ├── main.tsx               # entrypoint (QueryClientProvider + Router)
│   └── router.tsx
├── biome.json
├── index.html
├── package.json
├── postcss.config.js
├── tailwind.config.ts
├── tsconfig*.json
└── vite.config.ts
```

---

## Convenciones

- **TypeScript strict + verbatimModuleSyntax.** `import type { … }` para
  todos los tipos.
- **Imports absolutos** vía alias `@/...` cuando ahorra recorrido (`@/api/client`).
  En pages locales, imports relativos.
- **CSS:** los estilos del Hi-Fi v2 viven verbatim en `tokens.css`,
  `global.css`, `shell.css` y `pages/Cockpit/cockpit.css`. Biome ignora `.css`
  para no reformatear el prototipo del diseñador. Cuando llegue un nuevo
  hi-fi, se porta a un módulo CSS dedicado bajo `pages/<X>/`.
- **Tailwind** se usa para utilities (spacing, layout, color tokens) y el
  plugin custom expone los efectos firmados de Phoenix (glass, tiers,
  bookmark shape, iridescent rotations Houdini).
- **Tests:** smoke + unit con Vitest + RTL. La pantalla del Cockpit se
  testea por landmarks (`aria-label="watchlist"`, `aria-label="detalle"`).
- **WebSocket / API:** placeholder por ahora. Próxima iteración: hooks
  `useSignals()`, `useSlots()`, `useApiUsage()` y conexión a `/ws?token=`
  con auto-reconnect.

---

## Próximos pasos sugeridos

1. **State management con Zustand:** stores `auth`, `slots`, `apiUsage`,
   `signals`. Migrar la fuente de la watchlist desde `pages/Cockpit/data.ts`
   al store.
2. **TanStack Query hooks:** `useEngineHealth`, `useSlots`, `useLatestSignals`.
3. **WebSocket listener:** `useScannerWS()` que mappea los 6 eventos
   (`signal.new`, `slot.status`, `engine.status`, `api_usage.tick`,
   `validator.progress`, `system.log`) a actions de los stores.
4. **Lightweight Charts** en el panel del Cockpit (reemplaza el SVG
   estático del prototipo).
5. **Estados restantes del Cockpit** (warmup, degraded, fatal, scan en
   curso, S+ nueva, AUTO off) → diseñar las variantes en componentes y
   conectarlas al estado global.
6. **Hi-Fi del Dashboard / Configuración / Memento** y luego
   reemplazar los stubs.

---

## Wireframing y previews hi-fi

`frontend/wireframing/` contiene los HTML standalone (sin build) que se
usaron para validar dirección visual antes de scaffoldear. Se mantienen
como referencia viva del look final esperado:

- `Cockpit Wireframes.html` — sketch paper-style mid-fi.
- `Cockpit Hi-Fi v1.html` — primer hi-fi (lima glass).
- `Cockpit Hi-Fi v2.html` — **fuente del scaffold actual** (Phoenix orange,
  glass cromado, iridiscentes Houdini, bookmark de marca-páginas).
- `Cockpit Hi-Fi Phoenix reference.html` — referencia cromática externa.
