# CLAUDE.md

Contexto persistente para asistentes de Claude Code trabajando en Scanner-V5.
Leer este documento **primero** al arrancar un chat nuevo. Contiene el estado
del código, convenciones, y gotchas aprendidas en sesiones anteriores.

---

## Saludo obligatorio

Al iniciar cualquier chat con Álvaro: **"¡Qué bolá asere! en qué pinchamos hoy?"**
(o variante equivalente). Sin excepciones.

---

## Usuario y workflow

- **Álvaro** — paper trader de opciones (TradingView), habla español.
- **Workflow:** discusión → "ejecuta" → ejecución. **No tomar decisiones
  unilaterales.** Cuando hay una decisión abierta: interrogante + opciones +
  ventajas/desventajas + recomendación, esperar "ejecuta".
- **Estilo:** español técnico, directo, sin relleno. Prefiere 1 manera clara
  sobre acumular configurabilidad.

---

## Qué es Scanner-V5

Scanner de opciones 0DTE/1DTE sobre mercado en vivo, 6 slots paralelos
(default: SPY/QQQ/IWM/AAPL/NVDA + 1 libre). **Greenfield Python** — reemplaza
al scanner v4.2.1 HTML monolítico (referencia conceptual únicamente).

**Relación con Signal Observatory:** proyecto hermano separado. El Observatory
**calibra canonicals** (fuente de verdad), Scanner-V5 **consume, no calibra**.

---

## Jerarquía documental (regla inviolable)

Cuando un spec viejo del Observatory y los 3 docs operativos se contradicen,
los 3 docs operativos **siempre ganan**.

En orden de prioridad:

1. `docs/specs/SCANNER_V5_FEATURE_DECISIONS.md` — fuente de verdad de decisiones (~1450 líneas)
2. `docs/specs/SCANNER_V5_FRONTEND_FOR_DESIGNER.md` — briefing visual
3. `docs/specs/SCANNER_V5_HANDOFF_CURRENT.md` — handoff de producto
4. Este `CLAUDE.md` — contexto de implementación (estado actual del código)

Cuando hay ambigüedad entre spec viejo y Observatory real (`docs/specs/Observatory/Current/scanner/`), **el código de Observatory gana** porque es el que generó el canonical + sample de paridad.

---

## Estado actual de la implementación

**Rama activa:** `claude/review-project-setup-4DnEm` (todo desarrollo va acá). La rama previa `claude/review-project-setup-PqMEL` fue mergeada a main y eliminada; este branch continúa el trabajo sobre Fase 5 del Scoring.

### Completado

| Capa | Módulo | Estado |
|---|---|---|
| 1 (Data Engine) | `backend/engines/data/` — KeyPool, TwelveDataClient stubs, market calendar, integrity, config | ✅ base |
| 3 (Slot Registry) | `backend/modules/slot_registry/` | ✅ base |
| 4 (Scoring Engine) | `backend/engines/scoring/` — Fases 1-4d | ✅ |
| Fixtures | `backend/modules/fixtures/` — loader | ✅ base |

### Scoring Engine — detalle por fase

- **Fase 1:** errors, constants, structure gate, output neutral.
- **Fase 2:** indicadores — SMA, EMA, Bollinger Bands, ATR, volume_ratio, gap_pct. **Rounding a 2 decimales al output** para paridad con Observatory (ver gotcha §Rounding).
- **Fase 3:** alignment gate — `trend_strict` (price>MA20>MA40) + `trend_slope` fallback + `trend_with_fallback` + `compute_alignment` + catalyst override.
- **Fase 4a:** 6 triggers candle-level 15M (Doji BB sup/inf, Hammer, ShootingStar, Rechazo sup/inf) con decay por age.
- **Fase 4b:** Envolvente 1H + Doble techo/piso.
- **Fase 4c:** MA20/40 cross 1H + ORB breakout/breakdown (time gate string compare + volume gate binario).
- **Fase 4d:** wiring completo — triggers + risks + trigger gate + conflict gate dentro de `analyze()`.
- **Extras:** 2 triggers 15M Envolvente (no están en spec §5.1 pero Observatory los emite — ver gotcha §Triggers extras). 4 RISK detectors (volume + BB fakeouts) — emiten pero no suman al score.

**Tests:** 245 passing en `backend/tests/engines/scoring/`.

### Pendiente

- **Fase 5** (Scoring): portar los 10 confirms con pesos del fixture + cálculo final del score + asignación de banda. Una vez hecho, correr parity test contra sample de Observatory.
- **Fase 6** (Scoring): conflict gate refinado (ya hay versión básica en Fase 4d).
- **Capa 2:** Validator module.
- **Capa 5:** persistencia SQLAlchemy + FastAPI endpoints + WebSocket.
- **Frontend:** React + TS (aún no iniciado en esta rama).

### Divergencias conocidas con Observatory (a atender en Fase 5+)

1. `vol_sequence` del Observatory aún no portado (vol_declining risk usa aproximación).
2. `volume_ratio` — mío usa ventana fija 20 velas, Observatory usa mediana intraday del día.
3. ATR — mío usa Wilder clásico, Observatory usa media simple de TRs (divergencia documentada en `indicators/atr.py`).
4. Pivot fakeouts requieren portar `find_pivots()` de Observatory.

---

## Gotchas críticas (errores cometidos y corregidos)

**NO repetir estos errores.** Cada uno requirió un commit de corrección.

### 1. H-02 "volumen fuera del score"

El hallazgo H-02 se refiere a **eliminar `volMult` (parámetro de peso que multiplicaba el score)**, NO a eliminar gates binarios de volumen. El gate `volume_ratio >= 1.0` del ORB **debe estar presente** — es paridad con Observatory `engine.py`. Verificado: `orb.py:112`.

**Lección:** "parámetro de peso" ≠ "gate binario (fire/no fire)". El primero se eliminó, el segundo se mantiene.

### 2. Alignment semantics (Option B)

Observatory usa: `trend_strict(price, ma20, ma40)` + `trend_slope(candles, ma20)` con shift de 5 velas + `trend_with_fallback`.

- Valores: `"bullish" | "bearish" | "neutral"` (para tendencia por TF), `"bullish" | "bearish" | "mixed"` (para alignment). **NUNCA `"up"/"down"/"flat"`** — esa fue mi primera versión incorrecta.
- **Catalyst override:** si `has_catalyst AND t_15m == t_1h AND t_15m != "neutral"`, el gate pasa aunque daily sea neutral.
- Minimum 25 velas para slope fallback, shift de 5.

### 3. Loop range en detección de triggers candle

Observatory: `for i in range(min(max_age+1, n-1))` — **NO `n`**. La diferencia: `n-1` garantiza que siempre haya una `pv = candles[idx-1]` disponible para Envolvente.

**Lección:** los triggers de 1 vela (Doji, Hammer, Star) funcionan con `n`, pero cuando se añade Envolvente al mismo loop hay que usar `n-1`.

### 4. Triggers extras 15M Engulfing

Spec §5.1 lista 14 triggers canónicos. Observatory `patterns.py` emite además **Envolvente alcista/bajista 15M con decay** (no en la tabla del spec). Están en el sample que generó el canonical, entonces el engine **debe** emitirlos. Total: 14 + 2 = **16 triggers detectores**.

### 5. ORB time gate — string compare

Observatory usa:
```python
_hhmm = sim_datetime[11:16]  # "HH:MM" de "YYYY-MM-DD HH:MM:SS"
_orb_in_first_hour = _hhmm <= "10:30"
```

**Los segundos se ignoran** — `"10:30:59"` es válido (mi primera versión lo rechazaba por comparación numérica). Implementado en `orb.py:_is_orb_time_valid`.

### 6. Rounding a 2 decimales

Observatory redondea al output de cada indicador. Mi paridad requiere:
- SMA/EMA/BB (middle, upper, lower)/ATR/volume_ratio/gap_pct → `round(..., 2)` al retornar.
- **Recurrencias (EMA, Wilder ATR):** mantener `prev` **sin redondear** internamente, solo redondear en la salida. Si redondeas `prev`, el error se compone.

### 7. RISK detectors no suman al score

Por H-04, los 4 detectores de RISK (vol_bajo_rebote, vol_declinante, BB sup/inf fakeout) emiten patterns con `cat="RISK"` y `sg="WARN"`, peso negativo **informativo** únicamente. **No contribuyen al score final**. Solo aparecen en `patterns[]` y `layers.risk`.

### 8. Git: squash-merges se ven como "commits nuevos" en main

GitHub squash-merge cambia el SHA. Cuando mergeás tu branch viejo a main vía PR, main obtiene un commit "nuevo" (squash) con el mismo código pero SHA distinto. Si después trabajás en la misma branch con correcciones, al intentar re-mergear git marca conflictos porque no reconoce que esos squashes son tu propio código viejo.

**Resolución segura para esta branch específica:** `git merge origin/main -X ours --no-ff`. Es seguro **SOLO** cuando verificás que todos los commits nuevos de main son squash-merges de esta misma branch (mismo autor, mismo contenido aplastado). Si main tiene trabajo ajeno, **NO usar `-X ours`** — resolver a mano.

---

## Observatory como autoridad de paridad

El código de Observatory vive en `docs/specs/Observatory/Current/scanner/`:
- `scoring.py` — pipeline principal
- `engine.py` — gates, time filters, ORB logic
- `patterns.py` — detección de triggers (es la fuente canónica)
- `indicators.py` — indicadores (SMA/EMA/BB/ATR/volume)

**Sample canonical QQQ:** `backend/fixtures/parity_reference/` — 30 sesiones 2025, 245 señales. Se generó con este código exacto. Cualquier divergencia entre mi engine y el sample = bug en mi port.

**Regla:** si hay duda sobre semántica (rounding, string vs numeric compare, ranges de loop, qué patterns emitir), **leer Observatory primero**, preguntar al usuario solo si sigue habiendo ambigüedad.

---

## Convenciones de código

- **Python 3.11**, type hints estrictos, Pydantic v2 con `frozen=True, extra="forbid"` para modelos públicos.
- **Tests:** pytest, fixture-free cuando sea posible, factories locales.
- **Docstrings:** español, pegados al "por qué" y a la paridad Observatory cuando aplique. Referenciar líneas exactas cuando es port literal.
- **Comments:** solo cuando el WHY no es obvio. NO narrar el WHAT.
- **Imports:** absolutos desde `backend/` (ej. `from engines.scoring.alignment import ...`), nunca relativos.
- **Rounding:** helpers como `round(x, 2)` al output, `prev` interno sin redondear en recurrencias.

---

## Git workflow

- **Todo desarrollo:** rama `claude/review-project-setup-4DnEm`. Nunca push directo a main.
- **Antes de commit:** correr `cd backend && python -m pytest tests/ -q` y asegurar que pasa.
- **Commit messages:** español, conventional commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`). Scope entre paréntesis (`feat(scoring):`).
- **Footer:** incluir `https://claude.ai/code/...` como manda la configuración del repo.
- **Nunca:**
  - `--no-verify` para saltear hooks.
  - `--amend` a commits ya pusheados.
  - `reset --hard` o `push --force` sin pedir permiso.
  - `add -A` o `add .` — listar archivos explícitos.

---

## Comandos útiles rápidos

```bash
# Tests scoring completos
cd backend && python -m pytest tests/engines/scoring/ -q

# Tests con verbose y último fallo
cd backend && python -m pytest tests/engines/scoring/ -xvs

# Lint
cd backend && ruff check .

# Ver estado vs main
git log --oneline origin/main..HEAD
git log --oneline HEAD..origin/main
```

---

## Qué hacer al arrancar un chat nuevo

1. Saludar con la frase obligatoria.
2. Leer este `CLAUDE.md` completo (ya lo estás haciendo).
3. Leer `docs/specs/SCANNER_V5_HANDOFF_CURRENT.md` para contexto de producto.
4. Si se va a tocar scoring: leer `docs/specs/SCORING_ENGINE_SPEC.md` + `docs/specs/Observatory/Current/scanner/scoring.py` + `patterns.py` + `engine.py`.
5. Correr los tests antes de tocar nada para verificar baseline verde.
6. Para el próximo paso del scoring (Fase 5 — confirms), leer `docs/specs/Observatory/Current/scanner/scoring.py` secciones de confirms y los pesos del fixture canonical.
7. **No avanzar sin "ejecuta".** Proponer, esperar, ejecutar.

---

**Fin del contexto. Cuando leas esto por primera vez en un chat nuevo: saludar, confirmar que lo leíste mencionando 1-2 gotchas específicas, y preguntar en qué pinchamos hoy.**
