# ADR-0002: Razonar y persistir en Eastern Time con tz-aware explícito

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

El Scanner v5 opera exclusivamente sobre el mercado de opciones US, cuya sesión activa es 9:30–16:00 ET. Todas las decisiones del motor dependen del horario ET: cierre de vela 15M, gate horario del ORB (≤10:30 ET), reset diario de créditos API, bloqueos horarios de la metodología (primer 15 min, dead zone 13:00–14:00 ET, last hour en 0DTE).

La máquina del trader puede estar en cualquier zona. El caso operativo principal es Montevideo (UTC-3), con diferencias de 1 o 2 horas respecto a ET según daylight saving time.

Ecosistema existente:

- **Scanner v4.2.1** (legacy): opera en ET naive, sin tzinfo explícita.
- **Signal Observatory** (backtest): también en ET naive.
- **Twelve Data** (provider): devuelve timestamps como strings naive `"YYYY-MM-DD HH:MM:SS"` en zona del símbolo (ET para tickers US).

Ninguno de los 3 docs operativos ni los specs del Observatory fijan la convención de zona horaria del scanner live. Decidir ahora evita bugs silenciosos de conversión horaria.

## Decisión

El backend del Scanner v5 razona y persiste **exclusivamente en Eastern Time con tz-aware explícito**.

Reglas concretas:

1. Todos los objetos `datetime` en el código usan `zoneinfo.ZoneInfo("America/New_York")` (disponible nativo en Python 3.11).
2. La DB guarda timestamps **con tzinfo** (nunca naive).
3. El Data Engine, al ingesar datos de Twelve Data (strings naive), convierte a tz-aware antes de pasar cualquier dato al resto del sistema.
4. El frontend recibe timestamps tz-aware por la API y los muestra tal cual — la UI se ve en ET, aunque la máquina del trader esté en otra zona.
5. Daylight Saving Time (segundo domingo de marzo, primer domingo de noviembre en US) queda resuelto automáticamente por `zoneinfo`.
6. **Nunca** se usan timestamps naive dentro del backend. Un `datetime.now()` sin tz es un bug.

Si en el futuro se necesita UTC para algún caso externo (backup portable entre zonas, integración con API que lo exige), la conversión se hace **en la frontera** — no como convención interna.

## Consecuencias

### Positivas

- Alineación total con el ecosistema existente (v4.2.1 + Observatory ya razonan en ET).
- DST lo resuelve `zoneinfo` automáticamente — cero bugs dos veces al año.
- El producto es literalmente un scanner del mercado US; ET es la zona natural operativa, no un detalle de implementación.
- Comparaciones de horario (cierre de vela, ORB gate, reset diario) son directas sin conversión.
- Debugging: los logs muestran horas que el trader reconoce de inmediato.

### Negativas / trade-offs

- Si algún día se agrega un ticker de otra zona (raro para opciones US), requeriría un segundo manejo de tz. No es preocupación hoy.
- Convención no universal (UTC sería el default estándar en sistemas genéricos). Mitigado: este producto NO es genérico, es específico de mercado US.
- Backups portables entre zonas: si un trader migra su Config+DB a otra máquina, las horas no cambian (sigue siendo ET) — eso es correcto funcionalmente pero el usuario debe entenderlo.

### Neutras

- Performance: `zoneinfo` es nativo y rápido; no hay impacto vs naive.

## Alternativas consideradas

### Alternativa A: UTC en DB, ET en lógica

DB guarda `timestamp_utc` con `Z`. El código convierte a ET al comparar contra cierres de vela, ORB gate, reset diario. Frontend convierte UTC → ET al renderizar.
**Por qué no:** convención estándar ("UTC en DB") tiene sentido para sistemas multi-zona. Este producto es mono-zona por diseño. Cada comparación horaria requeriría conversión — un olvido silencioso = bug de 4-5 horas sin señal obvia.

### Alternativa B: Doble columna (UTC + ET) en tablas que lo requieren

Redundancia explícita: `candle_timestamp_utc` + `candle_timestamp_et` en signals, candles_15m, etc.
**Por qué no:** storage y ancho de banda duplicado por un campo. Riesgo de desincronización entre columnas si no se fuerzan escrituras atómicas. Complejidad sin beneficio sobre A o sobre la decisión elegida.

### Alternativa C: Naive con convención documentada

Como el v4.2.1 actual — sin tzinfo, asumiendo ET implícito por contexto.
**Por qué no:** funciona pero es frágil. Cualquier feature futura que toque otra zona (log timestamps del sistema, backup S3, etc.) abre bugs silenciosos. `zoneinfo` es nativo y barato.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §4.11 (Zona horaria ET con tz-aware).
- [Python zoneinfo docs](https://docs.python.org/3/library/zoneinfo.html)
- IANA timezone database, entrada `America/New_York`.
