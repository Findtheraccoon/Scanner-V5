# Changelog

Todos los cambios relevantes del proyecto Scanner-v5 se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y el proyecto adhiere a [Semantic Versioning](https://semver.org/lang/es/).

Nótese que este changelog versiona al **scanner como producto** (ej. `v0.1.0 → v0.2.0`). Los componentes internos (Scoring Engine, schema de fixtures, Slot Registry, Canonical Manager) mantienen sus propias cadenas semver independientes, tal como lo define `FEATURE_DECISIONS.md §2.6`.

---

## [Unreleased]

### Added

- Bootstrap inicial del repo.
- Estructura de carpetas según `FEATURE_DECISIONS.md §5.4`.
- Sistema de documentación en 4 niveles (ver `README.md`).
- 7 ADRs retroactivos (`docs/adr/0001` a `docs/adr/0007`) que consolidan las decisiones tomadas durante la sesión de diseño 19–20 abril 2026.
- Templates de GitHub para PRs y issues.
- Convenciones de commits (`CONTRIBUTING.md`).
- Template base para ADRs futuros (`docs/adr/0000-template.md`).

### Changed

- N/A.

### Fixed

- N/A.

### Removed

- N/A.

---

## Historial

### Componentes previos al arranque del repo

Las decisiones de arquitectura se tomaron en sesiones de diseño previas al primer commit. Se listan acá para trazabilidad, pero el código aún no existe.

| Componente | Versión diseñada | Notas |
|---|---|---|
| Scoring Engine | 5.2.0 | Contrato inmutable; ver `docs/specs/SCORING_ENGINE_SPEC.md` cuando se sincronice |
| Schema de fixtures | 5.0.0 | Ver `docs/specs/FIXTURE_SPEC.md` |
| Slot Registry | 1.0.0 | 6 slots fijos, hot-reload habilitado (desvío del spec original) |
| Canonical Manager | 1.0.0 | Vive solo en Observatory; scanner no lo aloja |
| FEATURE_DECISIONS.md | 1.1.0 | Última sesión: barrido backend + cierre Cockpit (20 abril 2026) |
| FRONTEND_FOR_DESIGNER.md | 2.0.0 | Cerrado tras decisión estética W |

---

## Convenciones de entradas

Cada release estable incluye:

```
## [X.Y.Z] - YYYY-MM-DD

### Added
- Funcionalidad nueva (lleva entrada por cada feature externa).

### Changed
- Cambio en funcionalidad existente.

### Deprecated
- Funcionalidad que se va a remover en próximos releases.

### Removed
- Funcionalidad removida (coincide con un MAJOR bump según semver).

### Fixed
- Bug fixes.

### Security
- Correcciones relacionadas con seguridad.
```

Entradas bajo `findtheracoon` se acumulan entre releases y se renombran al publicar.

---

## Links

[Unreleased]: https://github.com/REEMPLAZAR_ORG/Scanner-v5/compare/v0.1.0...HEAD
