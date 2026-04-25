# Frontend

**Stack:** React + TypeScript + Vite + Tailwind + shadcn/ui + Zustand + TanStack Query + React Flow + Lightweight Charts.
**Gestor de dependencias:** `pnpm`.
**Testing:** Vitest.

## Estado

Scaffolding pendiente. Cuando arranquemos la capa frontend, se genera con Vite:

```bash
cd frontend
pnpm create vite@latest . --template react-ts
pnpm install
```

A continuación se agregan las dependencias específicas del stack (Tailwind, shadcn/ui, Zustand, TanStack Query, React Flow, Lightweight Charts).

### Wireframing y previews hi-fi

`frontend/wireframing/` contiene los HTML standalone (sin build) que se usan para validar dirección visual antes de scaffoldear:

- `Cockpit Wireframes.html` — sketch paper-style mid-fi con 2 variantes (A densa / B holgada) y 5 estados. Solo referencia de **distribución**, no canónico estéticamente.
- `Cockpit Hi-Fi v1.html` — primer hi-fi del Cockpit (variante A) con los 5 design tokens aplicados (acento lima glass `#9cc80a`, Söhne→Inter, candles up=lima/down=blanco, pulse 4s, base `#050505`/`#0a0a0a`). 5 estados alternables (normal / warmup / degraded / splus / error) con persistencia en localStorage. PR #31.

## 4 pestañas del producto

1. **Configuración** — setup inicial + ajustes (4 pasos verticales).
2. **Dashboard** — panel admin del sistema.
3. **Cockpit** — pantalla operativa del trader.
4. **Memento** — consulta analítica.

## Lenguaje visual

**icomat base + Runpod estructural donde aplica.** Ver ADR-0007 y `docs/operational/FRONTEND_FOR_DESIGNER.md`.

- Paleta negra profunda + acento cromático único.
- Tipografías sobrias, minúscula, letterspacing generoso.
- Patrones Runpod (nodo-conexión, iconos técnicos, diagramas) traducidos a paleta icomat.
- Animaciones sobrias dentro del lenguaje icomat.

## Layout mínimo

- Ancho mínimo: 1440px (desktop only en v5).
- Modo oscuro único (v5 no tiene modo claro).
- Fullscreen del Cockpit soportado.

## Estructura propuesta (al generar scaffold)

```
frontend/
├── src/
│   ├── components/     # Componentes compartidos (cards, pilotos, botones)
│   ├── pages/          # Una por pestaña
│   │   ├── Configuration/
│   │   ├── Dashboard/
│   │   ├── Cockpit/
│   │   └── Memento/
│   ├── stores/         # Zustand stores (auth, slots, signals, api_usage)
│   ├── api/            # TanStack Query hooks + WebSocket listeners
│   └── styles/         # Tokens del design system
├── public/
└── package.json
```

## Referencias

- `docs/operational/FRONTEND_FOR_DESIGNER.md` v2.0.0 — briefing visual completo.
- `docs/operational/FEATURE_DECISIONS.md` §6 — las 4 pestañas en detalle.
- ADR-0007 — decisión estética W.
