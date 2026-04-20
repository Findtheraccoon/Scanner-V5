# ADR-0004: Política de retry con DEGRADED escalonado ante fallos de fetch

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

Durante el ciclo AUTO del scanner (cada cierre de vela 15M), el Data Engine puede encontrarse con errores al consultar a Twelve Data: timeouts, HTTP 500, respuestas con datos faltantes, desconexiones transitorias. El rate limit (HTTP 429) es caso aparte, ya resuelto por el sistema de créditos (espera de renovación + reintento), y queda fuera del alcance de esta decisión.

Los specs viejos del Observatory no definían comportamiento ante fallos de fetch de tickers individuales — asumían contexto offline, donde los datos ya estaban descargados. El scanner v4.2.1 (legacy) maneja errores por ticker de forma muy básica (muestra "Sin datos" en la UI y sigue). El scanner v5, al persistir señales con trazabilidad completa y al correr 6 slots en paralelo, necesita política explícita.

Tres problemas a resolver:

1. **Fallos transitorios del provider** (1-2 segundos de timeout, 500 puntual): deberían recuperarse solos sin perder el ciclo.
2. **Fallos persistentes de un ticker específico** (Twelve Data tiene problemas con un símbolo puntual): no deberían tumbar a los otros 5 slots operativos.
3. **Fallos persistentes del provider en general** (caída total): deberían escalar para que el trader lo note sin que aparezca cada 15 min como evento crítico.

## Decisión

El Data Engine implementa una política **escalonada por ticker** con 3 niveles:

### Nivel 1 — Retry corto

Ante error fetching un ticker en un ciclo AUTO:
- 1 retry rápido con ~1 segundo de espera.
- Si el retry tiene éxito, el ciclo continúa normalmente.

### Nivel 2 — Skip del ciclo

Si el retry también falla:
- El ticker afectado se marca como "skipped en este ciclo".
- Los otros 5 slots completan su scan y emiten señal normalmente.
- Se incrementa el contador de fallos consecutivos del slot.
- Se emite evento `slot.status` con `status: "error"` temporal y mensaje descriptivo, sin cambiar a DEGRADED todavía.

### Nivel 3 — Escalado a DEGRADED

Si un mismo slot acumula **3 ciclos consecutivos fallidos** (aproximadamente 45 min de mercado):
- Slot pasa a estado **DEGRADED** (piloto amarillo).
- Código de error: **`ENG-060`** ("ticker sin datos por N ciclos").
- Se deja de intentar fetchear ese ticker hasta que el trader revise o hasta que el ciclo vuelva a tener éxito (ver abajo).

### Recuperación automática

- Al primer fetch exitoso del ticker afectado, el contador se resetea y el slot vuelve a operativo (verde).
- La recuperación es silenciosa (no requiere intervención del trader), pero queda registrada en `system.log` para auditoría.

### HTTP 429 es ortogonal

Los errores de rate limit tienen su propio flujo (espera de renovación de créditos + reintento transparente en el Data Engine) y no disparan ni incrementan el contador de este ADR.

## Consecuencias

### Positivas

- Fallos transitorios aislados no rompen el ciclo (nivel 1).
- Fallos persistentes de un ticker no afectan a los otros 5 slots (nivel 2).
- Fallos sostenidos escalan de forma visible pero controlada, sin ruido cada 15 minutos (nivel 3).
- Recuperación automática sin intervención del trader.
- Código de error específico (`ENG-060`) permite auditoría y debugging.
- Coherente con la semántica DEGRADED ya usada para otros escenarios (fixture inválida, hash mismatch).

### Negativas / trade-offs

- 3 ciclos es un umbral tentativo; puede requerir ajuste con datos reales de uso. Se deja anotado como pendiente para validar al programar Capa 1.
- Mantener contador por slot es estado adicional en el Data Engine (un slot con 2 fallos seguidos + 1 éxito resetea vs un slot con 2 fallos + 1 skip = qué política exacta). La regla simple es: cualquier éxito resetea, cualquier skip incrementa.
- Si un ticker legítimamente no tiene datos durante 45 min por un evento de mercado real (circuit breaker, halt, delisting), el slot aparece DEGRADED — correcto pero puede confundir sin explicación. Mitigado por el mensaje descriptivo del código `ENG-060`.

### Neutras

- Los otros niveles (429, errores fatales del provider, errores de validación de integridad) ya tienen sus flujos independientes.

## Alternativas consideradas

### Alternativa A: Retry agresivo con bloqueo del ciclo

3 reintentos con backoff exponencial (1s, 2s, 4s). Si al 3er intento falla → el ciclo de ese cierre de 15M se aborta completo, no se emite señal para ningún slot, se espera al próximo cierre.
**Por qué no:** un fallo de un solo ticker tumba el ciclo entero de los 6 slots. Los otros 5 pierden su señal aunque estén bien. Inaceptable para el modelo operativo (trader depende de señales cada 15 min).

### Alternativa B: Retry corto, skip sin escalar

Nivel 1 + 2 sin nivel 3. Ante fallo persistente, el slot sigue en estado warning cada 15 min sin cambio de estado hasta que el trader intervenga manualmente.
**Por qué no:** genera ruido visual repetido. El trader se acostumbra a ignorar warnings, pierde señal real cuando aparezca. La semántica DEGRADED ayuda a distinguir "fallo transitorio" de "fallo sostenido que merece atención".

### Alternativa C: Escalado lineal (warning → DEGRADED → rojo)

Escalar gradualmente: 1 fallo = warning temporal, 3 fallos = amarillo DEGRADED, 6 fallos = rojo error fatal.
**Por qué no:** el paso a rojo requeriría intervención manual para volver (romper la recuperación automática), o agregar lógica de recuperación tras rojo. Complejidad sin beneficio claro. Si el slot está fuera 6 ciclos seguidos (1.5 horas), el trader ya notó el DEGRADED y tomó acción (o aceptó que ese ticker está problemático).

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.1 (Retry policy de Twelve Data).
- `docs/operational/FEATURE_DECISIONS.md` §7 (Códigos de error — `ENG-060`).
- `docs/operational/FEATURE_DECISIONS.md` §9.8 item 16 (pendiente: confirmar umbral de 3 ciclos al programar Capa 1).
- ADR-0003: sistema de warmup + consulta DB local; este ADR aplica a los ciclos AUTO posteriores al warmup.
