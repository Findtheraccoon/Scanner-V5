# scanner/ — código del motor del Observatory (versión actual)

Código fuente del motor de scoring del proyecto Observatory, en su
versión vigente. Se consulta como referencia al implementar los
módulos del scanner v5 (backend/engines/scoring/, triggers/,
indicators/, alignment/, confirms/, etc.).

Contenido esperado: módulos Python del Observatory (típicamente
`scoring.py`, `engine.py`, `patterns.py`, `indicators.py`, y los
artefactos de soporte que ese motor consuma — listas de categorías,
schedules de decay, umbrales de detección hardcoded).

**Uso:** archivo de consulta, NO se importa desde el código del
scanner. Cualquier lógica que aplique acá debe portarse explícitamente
al código propio del scanner en `backend/engines/scoring/`,
respetando el contrato definido por `docs/specs/SCORING_ENGINE_SPEC.md`.

**Ciclo de vida:** al publicar el Observatory una versión nueva del
motor, el contenido actual se mueve completo a
`../Legacy/v{major}_{minor}/scanner/` y esta carpeta queda para la
nueva versión.
