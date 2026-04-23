# Scanner-v5

Scanner de trading de opciones (0DTE/1DTE) sobre mercado US en vivo. Procesa hasta 6 tickers en paralelo (5 preset por default — SPY/QQQ/IWM/AAPL/NVDA — + 1 slot libre para configurar) con un motor de scoring plug-and-play, una fixture por ticker, y una UI operativa dividida en 4 pestañas.

**Estado (abril 2026):**
- **Backend:** completo a spec §3 + §9.4 + Fase 5.4 cerrada al 100%. **1055 tests passing**, parity **245/245** contra canonical QQQ del Observatory.
- **Frontend:** pendiente. Backend ya expone todos los endpoints (REST + WS) necesarios.
- **Distribución Windows:** pendiente `modules/config/` encriptado para las credenciales S3 + API keys Twelve Data.

---

## Arranque rápido

### Correr el backend

```bash
cd backend
pip install -e ".[dev]"

# Mínimo (sin scan loop real, sin validator):
SCANNER_API_KEYS="sk-dev" python main.py

# Full (con Twelve Data + slot registry + validator al arranque):
SCANNER_API_KEYS="sk-dev" \
  SCANNER_TWELVEDATA_KEYS="k1:sk-td-1:8:800" \
  SCANNER_REGISTRY_PATH="slot_registry.json" \
  python main.py
```

Al arrancar, el backend corre el Validator con las 7 baterías (D→A→B→C→E→F→G), persiste el reporte en DB + TXT en `LOG/`, emite progreso por WS y sube en `http://127.0.0.1:8000`.

### Correr tests

```bash
cd backend
python -m pytest tests/ -q                  # suite rápida (1055 tests, ~25s)
python -m pytest tests/ -m slow -v          # parity 100% exhaustivo (~2min)
ruff check .                                # lint
```

### Leer primero

1. **Docs operativos:**
   - `docs/operational/HANDOFF_CURRENT.md` — briefing compacto.
   - `docs/operational/FEATURE_DECISIONS.md` — fuente de verdad de decisiones.
2. **Contexto del código:** `CLAUDE.md` en la raíz (estado del código + gotchas + convenciones).
3. **Diseño visual:** `docs/operational/FRONTEND_FOR_DESIGNER.md`.
4. **Decisiones históricas:** `docs/adr/` (7 ADRs).
5. **Contratos técnicos:** `docs/specs/` (copias del Observatory).

---

## Estructura del repo

```
Scanner-v5/
├── backend/                        # Python 3.11 + FastAPI (✅ implementado)
│   ├── engines/                    # Motores vivos (procesos con ciclo de vida)
│   │   ├── data/                   # Data Engine — KeyPool + TwelveData + scan loop
│   │   ├── scoring/                # Scoring Engine — motor puro + healthcheck continuo
│   │   └── database/               # DB Engine — heartbeat + rotación + archive + watchdog
│   ├── modules/                    # Módulos invocados (sin ciclo de vida)
│   │   ├── validator/              # Validator — batería D/A/B/C/E/F/G + TXT log + REST
│   │   ├── slot_registry/          # Slot Registry — 6 slots, enable/disable, hot-reload
│   │   ├── signal_pipeline/        # analyze → persist → broadcast (con flag persist)
│   │   ├── fixtures/               # Loader de fixtures + canonical hash
│   │   ├── config/                 # (pendiente) Config encriptado
│   │   └── db/                     # SQLAlchemy async + helpers + backup/restore S3
│   ├── api/                        # FastAPI + 6 eventos WS + auth Bearer
│   ├── fixtures/                   # Canonical QQQ + parity reference
│   ├── tests/                      # 1055 tests + 1 slow (parity 100%)
│   └── pyproject.toml
├── frontend/                       # (pendiente) React + TypeScript + Vite
├── docs/
│   ├── adr/                        # 7 ADRs aprobados
│   ├── operational/                # Docs operativos vivos
│   ├── specs/                      # Contratos técnicos + Observatory reference
│   │   └── Observatory/Current/    # qqq_1min/daily + spy_daily JSON del replay
│   └── architecture/
├── data/                           # SQLite DBs operativa + archive (gitignored)
├── LOG/                            # Logs rotables (gitignored)
├── CLAUDE.md                       # Contexto de código para asistentes
└── scripts/
```

## Endpoints REST del backend

| Método | Path | Uso |
|---|---|---|
| `GET` | `/api/v1/engine/health` | Piloto del scoring engine |
| `GET` | `/api/v1/signals/latest` | Última señal por slot |
| `GET` | `/api/v1/signals/history` | Histórico cursor-based (transparent op+archive) |
| `GET` | `/api/v1/signals/{id}` | Señal completa + snapshot base64 |
| `POST` | `/api/v1/scan/manual` | Dispara scan on-demand |
| `GET/PATCH` | `/api/v1/slots` / `/api/v1/slots/{id}` | List + enable/disable + warmup |
| `POST` | `/api/v1/validator/run` | Batería completa |
| `POST` | `/api/v1/validator/connectivity` | Solo Check G (TD + S3) |
| `GET` | `/api/v1/validator/reports{,/latest,/{id}}` | Histórico de reportes |
| `POST` | `/api/v1/database/rotate{,/aggressive}` | Rotación manual + §9.4 |
| `GET` | `/api/v1/database/stats` | Tabla por tabla + tamaño op |
| `POST` | `/api/v1/database/{backup,restore,backups}` | S3-compatible (AWS/B2/R2/custom) |
| `WS` | `/ws?token=...` | 6 eventos push (signal.new, slot.status, engine.status, api_usage.tick, validator.progress, system.log) |

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
