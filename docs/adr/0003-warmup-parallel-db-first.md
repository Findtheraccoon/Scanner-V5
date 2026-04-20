# ADR-0003: Warmup paralelo full con consulta previa a DB local

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

Al arrancar el sistema (o al hacer Auto-LAST con 6 slots configurados), el Data Engine debe descargar el warmup inicial: velas suficientes para que todos los indicadores del Scoring Engine estén definidos. Según `FEATURE_DECISIONS.md §3.1`, el warmup completo son 210 daily + 80 1H + 50 15M por ticker + benchmarks únicos.

Escenario pesimista: 6 tickers × 3 timeframes + benchmarks = típicamente 18–24 llamadas HTTP a Twelve Data. Con 5 API keys (créditos/min ~8 en plan gratuito, 40 totales/min) el cupo no es el problema, pero la coordinación sí lo es:

- Si se disparan las 24 en paralelo, hay picos de concurrencia que pueden saturar una key si el round-robin la sobrecarga.
- Si se disparan secuenciales por slot, el arranque tarda 20–30 segundos y el trader ve los slots habilitarse uno a uno.

Durante la sesión del 20-abril, Álvaro aportó una observación decisiva que cambia el problema: **la DB local ya guarda velas históricas de tickers usados previamente**, dentro de la ventana de retención (daily 3 años, 1H 6 meses, 15M 3 meses). Por lo tanto, el escenario pesimista (primer arranque con 6 tickers vírgenes) es raro; el caso cotidiano (mismo trader, mismos tickers, reabrir el scanner a la mañana siguiente) requiere muy pocas llamadas reales al provider.

## Decisión

El Data Engine adopta una política de warmup con dos componentes:

### 1. Consulta a DB local antes de fetchear el provider

Antes de llamar a Twelve Data, el Data Engine consulta la DB local y verifica qué velas necesita realmente descargar. Si una vela requerida ya está en DB dentro de la ventana de retención vigente, no se descarga. Solo se pide el **gap real**.

Impacto operativo:

- **Arranque inicial con ticker virgen:** fetch completo 210/80/50 (peor caso, sigue).
- **Re-arranque cotidiano** (mismo ticker, cierre de mercado previo entre sesiones): fetch mínimo — solo velas nuevas del día si las hubiera.
- **Hot-reload activando slot con ticker previamente usado:** probablemente cero fetch de daily/1H; solo velas 15M recientes.

### 2. Arranque paralelo full con `asyncio.gather()`

Las llamadas HTTP que efectivamente se disparen (tras descontar lo que ya está en DB) se ejecutan en paralelo con `asyncio.gather()`. El round-robin proporcional distribuye la carga entre las 5 keys según créditos/min configurados.

Sin coordinación secuencial por slot, sin serialización interna: paralelo full.

## Consecuencias

### Positivas

- Tiempo de arranque mínimo en todos los escenarios.
- En el caso cotidiano, el scanner arranca casi instantáneamente tras el primer día de uso (la DB ya tiene casi todo).
- Hot-reload de slots con tickers conocidos es inmediato.
- Reduce llamadas a Twelve Data → menos presión sobre cupos/min y diarios.
- Simplicidad: `asyncio.gather()` es una línea vs lógica de coordinación compleja.

### Negativas / trade-offs

- En el peor caso (primer arranque real, 6 tickers vírgenes, 24 requests simultáneos), si una key está mal configurada o saturada, se puede ver rate-limiting momentáneo. Se mitiga con la redistribución dinámica del round-robin y el retry policy de ADR-0004.
- La consulta previa a DB agrega ~10-50 ms por ticker antes del fetch. Despreciable.
- Aparece una sub-pregunta no resuelta: cómo detectar gaps precisos en la DB cuando el scanner estuvo offline por varios días, feriados, o half-days. Se registra como pendiente para la implementación de Capa 1.

### Neutras

- Requiere que el Data Engine y la capa de DB estén integrados desde el inicio — no se puede desarrollar Data Engine "puro" sin la DB. Consecuencia menor dado que ambos viven en el mismo proceso.

## Alternativas consideradas

### Alternativa A: Paralelo full sin consulta a DB

Disparar todas las llamadas al provider en cada arranque, sin optimización. Simple, consistente.
**Por qué no:** ignora el ahorro obvio (la DB ya tiene datos), presiona cupos innecesariamente, hace el arranque más lento y más propenso a errores transitorios. La consulta a DB es trivial de implementar.

### Alternativa B: Secuencial por slot

Slot 1 completa warmup → slot 2 arranca → etc. Control total, logs limpios.
**Por qué no:** lento (20-30 s cuando todo es fetch). Sensación de herramienta lenta. Sin beneficio de robustez sobre paralelo + retry.

### Alternativa C: Paralelo por slot, secuencial de timeframes dentro del slot

6 requests simultáneos al inicio (bien debajo del cupo/min combinado de 5 keys). Dentro de cada slot, daily → 1H → 15M secuencial.
**Por qué no:** más código, más coordinación, beneficio marginal. Con la consulta previa a DB, el volumen real de requests es mucho menor que el escenario pesimista que motivaba esta alternativa.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.1 (Consulta a DB local antes de fetch, Arranque paralelo del warmup).
- `docs/operational/FEATURE_DECISIONS.md` §11 desvío #8 (consulta DB local como desvío explícito de specs originales).
- `docs/operational/FEATURE_DECISIONS.md` §9.8 item 15 (pendiente: detección de gaps en DB).
- Referencia de round-robin validado: `scanner_v4_2_1.html` (tres años de operación en producción).
- ADR-0004: política de retry que complementa este flujo cuando hay fallos.
