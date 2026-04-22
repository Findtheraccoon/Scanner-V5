# docs/specs/Observatory/Current/Replay/ — código del replay del Observatory

Módulo del Observatory que toma la base de datos histórica (velas 1-minuto de QQQ + otros tickers) y **dosifica cada vela 15M al scanner como si fuera tiempo real**. Es lo que se usó para generar el canonical QQQ y el sample de paridad de 245 señales.

## Propósito para el Scanner-V5

Este código es **material de referencia** para resolver las divergencias pendientes de la Fase 5.4 del scoring engine. El parity test actual (`backend/fixtures/parity_reference/parity_qqq_regenerate.py`) matchea 189/245 señales; los 56 remanentes se explican por ambigüedades en la convención de agregación de velas 1H y el cálculo de decay/age de triggers — convenciones que este replay hace explícitas.

## Qué buscar acá

Al estudiar este módulo para cerrar las 56 divergencias, enfocarse en:

1. **Cómo construye `candles_1h` al momento T:** ¿usa la parcial de la hora en curso? ¿agrega desde 15M? ¿separa MA20/MA40 del último close?
2. **Cómo calcula `age` en triggers:** al detectar un patrón de hace N velas 15M, ¿cómo cuenta esas N al momento de evaluar? (Ver mismatches tipo `trigger_sum expected=2.0 actual=2.1`.)
3. **Qué datos le llega al scanner cada step:** `candles_15m`, `candles_1h`, `candles_daily` con qué convención de parciales.
4. **Cómo itera las sesiones:** step de 15M, 1M, por minuto exacto de close, etc.

## Uso en Scanner-V5

**No importar este código.** Es de consulta únicamente. Cualquier lógica aplicable debe portarse explícitamente a `backend/engines/scoring/` respetando el contrato de `docs/specs/SCORING_ENGINE_SPEC.md`.

## Ciclo de vida

Al publicar Observatory una versión nueva del replay, el contenido actual se mueve a `../../Legacy/v{major}_{minor}/Replay/` y esta carpeta queda para la nueva versión.

## Estado

Directorio creado el 2026-04-22. Pendiente de subida del código por Álvaro.
