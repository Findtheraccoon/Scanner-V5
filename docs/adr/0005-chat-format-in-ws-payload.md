# ADR-0005: Generar el bloque `chat_format` en backend y enviarlo en el payload `signal.new`

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Álvaro (decisor) + sesión de diseño 20-abril

## Contexto

El Cockpit del Scanner v5 tiene un botón `COPIAR` que copia al clipboard un bloque de texto multilinea con el resumen completo del estado del slot seleccionado. El bloque está diseñado para pegarse en un chat con un asistente LLM (Claude) y pedir análisis cualitativo antes de ejecutar una operación. Este patrón se usa desde el v4.2.1 (función `genCT` en `scanner_v4_2_1.html`) y es parte de la rutina operativa del trader.

En el v4.2.1, el texto se genera en el frontend (JavaScript) a partir del estado del scanner. En el v5 hay una reestructuración completa del backend y del frontend, por lo que se redefine el patrón.

Dos decisiones entrelazadas a tomar:

1. **Quién arma el texto** (capa A): backend o frontend.
2. **Qué formato tiene el texto** (capa B): el de v4.2.1 tal cual, adaptado, o rediseñado.

### Contexto sobre capa B

El `genCT` del v4.2.1 produce un bloque con varios campos que en v5 ya no existen o cambiaron:

- **Eliminados del motor v5:** multiplicador horario (`time_w`), multiplicador de volumen (`VolMult`), bonus de pivote cercano, risk penalties (ya no afectan score).
- **Franjas nuevas:** `B+` no existe; se reemplaza por la escala `REVISAR / B / A / A+ / S / S+`.
- **Campos nuevos:** `fixture_id` + `fixture_version` + `engine_version` para trazabilidad.

Mantener el formato literal del v4.2.1 requiere eliminar campos muertos; adaptar a v5 requiere además agregar metadata de trazabilidad.

## Decisión

### Capa A — el backend arma el `chat_format`

En cada señal nueva, el backend incluye el campo **`chat_format: string`** dentro del payload del evento WebSocket `signal.new`. El texto viene listo.

El frontend, al detectar un click en el botón `COPIAR`, hace simplemente:

```javascript
navigator.clipboard.writeText(signal.chat_format);
```

Sin procesamiento, sin round-trip HTTP, sin template en frontend.

### Capa B — formato rediseñado (B3)

El template se rediseña respecto al `genCT` del v4.2.1, siguiendo los criterios:

- Organización por **bloques semánticos**, no por campo suelto. Bloques: `PRECIO`, `CONTEXTO`, `VOLUMEN`, `FUERZA RELATIVA`, `NIVELES`, `EVENTOS`, `PATRONES`, `SCORING`, `RESULTADO`, `Meta`.
- **Header único** arriba con score/dir/conf (lo que el LLM y el trader miran primero).
- **Bloques opcionales se eliden** completamente si no aplican (si no hay eventos, no aparece el header "EVENTOS" en blanco).
- **Meta de trazabilidad** al final (engine_version, fixture_id+version, slot_id, timestamps) — presente pero sin contaminar la lectura.
- **ASCII + emojis puntuales** (⚠️ ⚡ ↑ ↓) para estados críticos.
- **Valores alineados en monospace** para lectura rápida.

Template visual completo de referencia en `docs/operational/FRONTEND_FOR_DESIGNER.md` §7.5.

### Consecuencia arquitectónica

El panel de detalle técnico del Cockpit (§6.5 de FEATURE_DECISIONS) **espeja los bloques del `chat_format`** — misma organización semántica en UI maqueta y en texto plano. El trader mentalmente no cambia de esquema entre ver el panel y leer lo que pegó en el chat.

## Consecuencias

### Positivas

- **UX instantánea**: el click en `COPIAR` es inmediato (no hay HTTP request para pedir el texto).
- **Template centralizado en backend**: si mañana se agrega un campo nuevo al motor o se ajusta el formato, se cambia en un solo lugar (Python); el frontend no requiere cambios.
- **Consistencia con el panel de detalle**: el trader reconoce los bloques visuales al pasar al chat.
- **Trazabilidad integrada**: el bloque `Meta` siempre acompaña la señal pegada; el LLM que la reciba sabe exactamente qué versión del motor la generó.
- **Peso agregado mínimo**: ~800 bytes × 1 señal/15min/slot = irrelevante para WebSocket.

### Negativas / trade-offs

- El backend genera texto presentación (rompe levemente el principio de "backend = datos, frontend = formato"). Aceptado porque:
  - El texto NO se muestra en la UI (el panel usa los mismos datos estructurados, no el texto plano).
  - El destinatario real del texto es un consumer externo (un chat LLM), no el frontend.
- Si alguna vez hubiera varios idiomas, el backend tendría que conocer el locale del usuario. Hoy no es requisito (producto en español).
- Cambiar el template requiere redeploy del backend (no es configurable en runtime). Aceptado; los cambios de este template son raros.

### Neutras

- Implementación: una función pura `format_chat_block(signal_output) -> str` en `backend/engines/scoring/` o `backend/api/`. Testeable directo con snapshot tests.

## Alternativas consideradas

### Alternativa A1: Backend endpoint dedicado `GET /api/v1/signals/{id}/chat_format`

El frontend hace HTTP request al presionar el botón, el backend devuelve el texto.
**Por qué no:** agrega round-trip innecesario (~50-200 ms de latencia), ruido en logs de API, complica el frontend (manejar estados de loading del botón). Sin beneficio respecto a la decisión elegida.

### Alternativa A2: Frontend arma el texto desde datos del WebSocket

El payload de `signal.new` lleva todos los campos estructurados (layers, ind, patterns, sec_rel, div_spy, etc.). Un template function en el frontend arma el texto al presionar el botón.
**Por qué no:** duplica lógica de formato (si mañana se cambia el template, hay que actualizar frontend y backend). Riesgo de divergencia entre lo que ve el panel y lo que se pega al chat. El beneficio ("backend no genera texto") es marginal dado el contexto.

### Alternativa B1: Formato literal del v4.2.1, solo eliminando campos muertos

Mantener el formato exacto del `genCT`, solo quitando VolMult/Hora/Bonus/Riesgo que ya no existen.
**Por qué no:** conserva una estructura visual que refleja un motor que cambió. Álvaro (el único usuario) tiene el patrón visual internalizado, pero los bloques semánticos (VOLUMEN, EVENTOS, etc.) son más claros para el LLM que recibe el texto. Adaptar paga la curva de acostumbramiento.

### Alternativa B2: Formato adaptado a v5 sin redeño

Eliminar campos muertos + agregar bloque `META`, pero manteniendo la línea-por-campo del v4.2.1.
**Por qué no:** conserva la curva de lectura del v4.2.1 pero no aprovecha la reestructuración para mejorar claridad. Compromiso intermedio sin ventajas fuertes sobre B3.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §3.6 (Campo `chat_format` en payload del WebSocket).
- `docs/operational/FEATURE_DECISIONS.md` §6.5 (Cockpit — panel derecho con bloques espejados).
- `docs/operational/FRONTEND_FOR_DESIGNER.md` §7.5 (Template completo de referencia para DESIGNER).
- Función original: `scanner_v4_2_1.html` función `genCT` (líneas 666-698).
