<!--
Gracias por el PR. Antes de pedir revisión (o self-review), completá los campos de abajo.
No uses este template si el cambio es puramente cosmético o de docs menores — en ese caso,
escribí un título claro y una línea de descripción y mergeá.
-->

## Qué cambia

<!-- Describí el cambio en 2-3 oraciones. El lector debe entender qué pasa sin abrir el diff. -->

## Por qué

<!-- Contexto: qué problema resuelve, qué decisión previa lo motiva.
     Si responde a un ADR, linkealo. Si afecta FEATURE_DECISIONS, mencionalo. -->

## Tipo de cambio

- [ ] `feat` — funcionalidad nueva
- [ ] `fix` — bug fix
- [ ] `refactor` — reorganización sin cambio de comportamiento
- [ ] `docs` — documentación
- [ ] `test` — tests
- [ ] `chore` — mantenimiento (deps, configs)
- [ ] `perf` — mejora de performance
- [ ] Breaking change — implica bump MAJOR del componente afectado

## Componentes afectados

- [ ] `engines/data` (Data Engine)
- [ ] `engines/scoring` (Scoring Engine)
- [ ] `engines/database` (Database Engine)
- [ ] `modules/validator`
- [ ] `modules/slot_registry`
- [ ] `modules/config`
- [ ] `modules/db`
- [ ] `api` / WebSocket
- [ ] Frontend (pestañas o componentes)
- [ ] Fixtures / canonicals / metrics
- [ ] Infraestructura (build, CI, configs)
- [ ] Solo documentación

## Checklist

### Código
- [ ] Los commits siguen [Conventional Commits](../CONTRIBUTING.md#1--commits--conventional-commits).
- [ ] Los docstrings de funciones públicas nuevas siguen el estilo Google (en español).
- [ ] Type hints en firmas de funciones públicas nuevas.
- [ ] Lint limpio (`ruff check` en backend, `eslint` en frontend).

### Tests
- [ ] Tests nuevos cubren la funcionalidad/fix agregada.
- [ ] Tests de invariantes actualizados si el cambio afecta un contrato.
- [ ] `pytest` corre verde localmente.

### Documentación
- [ ] README del módulo afectado refleja los cambios de interfaz/invariantes, si aplica.
- [ ] `docs/operational/FEATURE_DECISIONS.md` actualizado si el cambio afecta decisiones operativas del producto.
- [ ] Nuevo ADR creado en `docs/adr/` si la decisión merece registro histórico.
- [ ] `docs/adr/README.md` actualizado si se agregó ADR.
- [ ] `CHANGELOG.md` tiene entrada bajo `[Unreleased]` en la sección correspondiente.

### Especiales
- [ ] Si hay código nuevo de error (`ENG-`, `FIX-`, `REG-`, `MET-`), figura en `docs/specs/FIXTURE_ERRORS.md` (o en el TODO de sincronización con Observatory).
- [ ] Si cambia el schema de DB, hay migración Alembic correspondiente.
- [ ] Si cambia un endpoint REST o evento WebSocket, `FEATURE_DECISIONS.md §5.3` refleja el cambio.

## Referencias

<!--
- Issues: #NN
- ADRs: ADR-NNNN
- Specs tocados: archivo.md §sección
-->
