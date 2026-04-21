# Scanner-v5

Scanner de trading de opciones (0DTE/1DTE) sobre mercado US en vivo. Procesa hasta 6 tickers en paralelo (5 preset por default — SPY/QQQ/IWM/AAPL/NVDA — + 1 slot libre para configurar) con un motor de scoring plug-and-play, una fixture por ticker, y una UI operativa dividida en 4 pestañas.

**Estado:** diseño cerrado (abril 2026). Desarrollo greenfield — no porta código del scanner v4.2.1, solo concepto.

---

## Arranque rápido

Para quien se suma al repo por primera vez:

1. **Leer primero:**
   - `docs/operational/HANDOFF_CURRENT.md` — briefing compacto.
   - `docs/operational/FEATURE_DECISIONS.md` — fuente de verdad de decisiones de producto y arquitectura.
2. **Para diseño visual:** `docs/operational/FRONTEND_FOR_DESIGNER.md`.
3. **Para decisiones puntuales históricas:** `docs/adr/`.
4. **Para contratos técnicos:** `docs/specs/` (copias sincronizadas desde el Observatory).

---

## Estructura del repo

```
Scanner-v5/
├── backend/                        # Python 3.11 + FastAPI
│   ├── engines/                    # Motores vivos (procesos con ciclo de vida)
│   │   ├── data/                   # Data Engine — fetch + integridad + API keys
│   │   ├── scoring/                # Scoring Engine — motor puro stateless
│   │   └── database/               # Database Engine — supervisor rotación + backup
│   ├── modules/                    # Módulos invocados (sin ciclo de vida)
│   │   ├── validator/              # Validator Module — 7 tests al arranque + on-demand
│   │   ├── slot_registry/          # Slot Registry — 6 slots fijos, hot-reload
│   │   ├── config/                 # Config loader/saver del usuario
│   │   └── db/                     # Capa de persistencia SQLAlchemy
│   ├── api/                        # FastAPI + WebSocket endpoints
│   ├── fixtures/                   # Canonicals embebidos + dataset de parity
│   ├── tests/
│   └── pyproject.toml
├── frontend/                       # React + TypeScript + Vite
├── docs/
│   ├── adr/                        # Architecture Decision Records (auditoría)
│   ├── operational/                # Docs operativos vivos (decisiones + handoff)
│   ├── specs/                      # Contratos técnicos (copias del Observatory)
│   └── architecture/               # Diagramas SVG
├── data/                           # SQLite DBs (gitignored)
├── LOG/                            # Logs rotables (gitignored)
└── scripts/                        # Utilidades de mantenimiento
```

---

## Stack

**Backend:** Python 3.11, FastAPI, Uvicorn single-worker, SQLAlchemy 2.0 async, Alembic, Loguru, pytest, `uv`.

**Frontend:** React + TypeScript, Vite, Tailwind, shadcn/ui, Zustand, TanStack Query, React Flow (nodo-conexión), Lightweight Charts (gráficos financieros), Vitest, `pnpm`.

**Data:** Twelve Data como provider (5 API keys con round-robin proporcional).

**Deployment:** alfa en dev local; release como `.exe` Windows empaquetado con Inno Setup.

---

## Convenciones

- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/). Ver `CONTRIBUTING.md`.
- **Versionado:** semver por componente (engine, fixture, registry, canonical_manager, scanner). Ver `CHANGELOG.md`.
- **Decisiones:** se registran como ADRs en `docs/adr/` usando el template `0000-template.md`. Una vez `Accepted`, son inmutables.
- **Idioma:** código en inglés; documentación y comentarios de contexto en español.

---

## Auditoría y trazabilidad

El proyecto mantiene **4 niveles de documentación** distintos, que no se mezclan:

| Nivel | Dónde vive | Qué contiene |
|---|---|---|
| Decisiones operativas | `docs/operational/` | Fuente de verdad viva de decisiones de producto y arquitectura |
| Decisiones históricas atómicas | `docs/adr/` | ADRs inmutables con contexto, alternativas y consecuencias |
| Contratos técnicos | `docs/specs/` | Specs formales del motor, fixtures, registry (copias del Observatory) |
| Código autodocumentado | `backend/` y `frontend/` | Docstrings Google-style + README por módulo |

Cada PR debe actualizar lo que corresponda según el tipo de cambio. Ver checklist en `.github/pull_request_template.md`.

---

## Referencias

- Signal Observatory — proyecto hermano de backtesting. Fuente de verdad empírica de canonicals.
- Scanner v4.2.1 HTML — herramienta actual; referencia conceptual únicamente.
