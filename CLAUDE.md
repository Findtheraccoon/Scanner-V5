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
| 4 (Scoring Engine) | `backend/engines/scoring/` — Fases 1-5 + parity harness | ✅ |
| Fixtures | `backend/modules/fixtures/` — loader | ✅ base |

### Scoring Engine — detalle por fase

- **Fase 1:** errors, constants, structure gate, output neutral.
- **Fase 2:** indicadores — SMA, EMA, Bollinger Bands, ATR, volume_ratio, gap_pct. **Rounding a 2 decimales al output** para paridad con Observatory (ver gotcha §Rounding).
- **Fase 3:** alignment gate — `trend_strict` + `trend_slope` fallback + `trend_with_fallback` + `compute_alignment` + catalyst override.
- **Fase 4:** 16 triggers + 4 risks + trigger gate + conflict gate dentro de `analyze()`.
- **Fase 5.1:** 10 detectores de confirms (BB sup/inf 1H/D, VolHigh, VolSeq, SqExp, Gap, FzaRel, DivSPY) con descripciones bit-a-bit Observatory.
- **Fase 5.2:** port Observatory indicators — `today_candles` + `vol_ratio_intraday` (median), `vol_sequence` dict, `bb_width` squeeze dict, `gap` dict, `find_pivots` + `key_levels`. Resuelve divergencias #1, #2, #4 con Observatory.
- **Fase 5.3:** wiring completo en `analyze()`:
  - **5.3a** · `ind_builder.py:build_ind_bundle()` agrupa indicadores consumidos por confirms.
  - **5.3b** · `confirms/categorize.py` (dedup + pesos fixture) + `bands.py` (resolve_band) + `errors.py:build_signal_output()` + wire paso 8-11 en analyze. Score = trigger_sum + confirm_sum (H-02).
  - **5.3c** · Tests de integración con monkeypatch de detectores.
- **Fase 5.4:** parity harness — `backend/engines/scoring/aggregator.py` (1min→15M/1H) + `backend/fixtures/parity_reference/parity_qqq_regenerate.py` (runner E2E). **Baseline 189/245 matches (77%)**.

**Tests:** 643 passing en `backend/tests/engines/scoring/`.

### Módulos nuevos del Scoring Engine (Fase 5)

| Archivo | Rol |
|---|---|
| `engines/scoring/aggregator.py` | Agrega velas 1-minuto a 15M/1H open-stamped, con flag `include_partial` |
| `engines/scoring/bands.py` | `resolve_band(score, fixture) → (conf, signal)` vía `fixture.score_bands` |
| `engines/scoring/ind_builder.py` | `build_ind_bundle(daily, 1h, 15m, spy, bench, sim_date) → IndBundle` |
| `engines/scoring/indicators/gap.py` | Observatory `gap()` dict `{pct, significant, dir}` |
| `engines/scoring/indicators/pivots.py` | `find_pivots()` + `key_levels()` |
| `engines/scoring/confirms/categorize.py` | `categorize_confirm()` + `apply_confirm_weights()` (dedup por categoría) |
| `engines/scoring/confirms/bollinger.py`, `volume.py`, `squeeze.py`, `gap.py`, `relative_strength.py` | Detectores de confirms por familia |
| `fixtures/parity_reference/parity_qqq_regenerate.py` | Runner parity E2E (Opción B) contra `data/parity_qqq_candles.db` |

### Pendiente

- **Fase 5.4 restantes:** cerrar los 56 mismatches del parity (requiere estudiar el código del replay Observatory en `docs/specs/Observatory/Current/Replay/` para entender convención exacta de 1H aggregation + decay age).
- **Capa 2:** Validator module.
- **Capa 5:** persistencia SQLAlchemy + FastAPI endpoints + WebSocket.
- **Frontend:** React + TS (aún no iniciado en esta rama).

### Divergencias conocidas con Observatory — estado post-Fase 5.2/5.4

1. ~~`vol_sequence` port~~ → **Resuelto Fase 5.2b.**
2. ~~`volume_ratio` mediana intraday~~ → **Resuelto Fase 5.2a** (nuevo `vol_ratio_intraday`; el `volume_ratio_at` legacy sigue disponible pero no se usa en el pipeline principal).
3. **ATR Wilder vs Observatory mean:** pendiente. No afecta confirms críticos (Gap usa `atr_pct` que da similar magnitude). Documentada en `indicators/atr.py`.
4. ~~Pivot fakeouts~~ → **Resuelto Fase 5.2e** (`find_pivots` + `key_levels`).
5. **Convención 1H aggregation:** ambigua al momento. Mis tests con `include_partial=False` rompen más de lo que arreglan (189→160). Resolución requiere el código del replay Observatory. Ver divergencias documentadas en `backend/fixtures/parity_reference/README.md`.
6. **Decay age en triggers 15M:** mismatches como `trigger_sum expected=2.0 actual=2.1` sugieren off-by-1 en cálculo de age de velas pasadas. Requiere el replay para ver cuántas velas atrás mira Observatory exactamente.

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

### 8. Parity replay mode — daily incluye la sesión del día

El sample canonical QQQ fue generado por Observatory en **replay mode** (post-cierre de sesión). Al procesar señal a las `2025-02-28 10:30`, Observatory ya tiene la vela daily CERRADA de `2025-02-28` disponible. Esto significa:

- `candles_daily` incluye `dt <= date` (inclusive el día de la señal), NO `dt < date`.
- `a_chg` y `spy_chg` usan el close FINAL del día actual, alineados temporalmente.
- En live production esto sería look-ahead; para paridad con el sample hay que replicar el replay.

El runner `parity_qqq_regenerate.py` implementa esta convención en su `slice_for_signal`. **No cambiar sin regenerar el sample.**

### 9. Aggregation 15M vs 1H asimétrica

- **15M:** bucket open-stamped `[T, T+14]`. La última vela al momento T es **parcial** (close = 1min de T). El sample `price_at_signal` matchea ese close.
- **1H:** bucket open-stamped `HH:00`. La convención exacta para el cálculo de MA20/MA40 al momento T sigue siendo ambigua — experimentalmente, incluir la parcial da 189/245 matches y excluirla da 160/245. El replay Observatory aclarará la convención real.

### 10. Git: squash-merges se ven como "commits nuevos" en main

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
