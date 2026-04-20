# Contribuir a Scanner-v5

Guía de convenciones operativas del repo. Leer antes del primer PR.

---

## 1 · Commits — Conventional Commits

Todos los commits siguen el formato [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):

```
<tipo>(<scope>): <descripción imperativa breve>

<cuerpo opcional, explicando el porqué y trade-offs>

<footer opcional con referencias a issues/ADRs>
```

### Tipos válidos

| Tipo | Uso |
|---|---|
| `feat` | Funcionalidad nueva visible al usuario o a consumidores del API |
| `fix` | Corrección de bug |
| `docs` | Cambios en documentación (ADRs, READMEs, specs) |
| `refactor` | Cambio de código que no altera comportamiento observable |
| `test` | Agregar o modificar tests |
| `chore` | Mantenimiento: deps, configs, scripts |
| `perf` | Mejora de performance sin cambio de comportamiento |
| `style` | Cambios de formato (linter, whitespace) sin cambio de código |
| `build` | Cambios en el sistema de build (pyproject.toml, package.json, Inno Setup) |
| `ci` | Cambios en configuración de CI (cuando exista) |

### Scopes válidos

Los scopes mapean a componentes del repo. Lista cerrada:

- `data-engine` · `scoring` · `database-engine` — motores
- `validator` · `slot-registry` · `config` · `db` — módulos
- `api` · `ws` — capa de red
- `frontend` · `cockpit` · `dashboard` · `memento` · `config-ui` — frontend
- `fixtures` · `canonicals` · `metrics` — artefactos de scoring
- `adr` · `docs` — documentación
- `build` · `ci` — infraestructura
- `repo` — cambios transversales sin scope más específico

### Ejemplos

```
feat(data-engine): add round-robin proportional key rotation

Implementa distribución proporcional entre las 5 API keys según
créditos/min configurados, con redistribución dinámica si una key se agota.
Validado en producción en v4.2.1 durante 3 años. Ver ADR-0003.
```

```
fix(scoring): handle division by zero in FzaRel calc (ENG-020)

Cuando benchmark tiene volumen 0 en daily, el cálculo de divergencia
causaba ZeroDivisionError. Ahora se captura y se devuelve ENG-020.
```

```
docs(adr): add ADR-0008 for sibling metrics file naming
```

```
refactor(db): extract rotation logic to database engine
```

### Regla sobre breaking changes

Un commit con breaking change lleva `!` después del scope y una sección `BREAKING CHANGE:` en el footer:

```
feat(api)!: rename /signals/latest to /signals/current

BREAKING CHANGE: frontend consumers must update the endpoint.
```

Breaking changes implican bump MAJOR en el componente afectado y entrada visible en CHANGELOG.

---

## 2 · Branches

- `main` — siempre deployable. Protegida.
- `dev/<scope>-<short-description>` — trabajo en curso. Ej: `dev/data-engine-initial-skeleton`.
- `fix/<short-description>` — bug fixes puntuales.
- `docs/<short-description>` — cambios solo de docs.

Rebase sobre `main` antes de abrir PR. No mergeamos con commits de merge (squash o rebase-merge).

---

## 3 · Pull Requests

Todo cambio pasa por PR, incluso cuando el repo sea single-contributor. El PR sirve para:

- Revisarse uno mismo antes de mergear.
- Dejar traza auditable de qué cambió y por qué.
- Forzar el checklist.

El template está en `.github/pull_request_template.md`. Checklist resumido:

- [ ] Los commits siguen Conventional Commits.
- [ ] Tests agregados o modificados cubren el cambio.
- [ ] Docstrings Google-style en funciones públicas nuevas.
- [ ] README del módulo actualizado si cambia la interfaz o las invariantes.
- [ ] ADR creado si se toma una decisión arquitectónica nueva.
- [ ] `FEATURE_DECISIONS.md` actualizado si el cambio afecta contratos del producto.
- [ ] Entrada en `CHANGELOG.md` bajo `[Unreleased]`.
- [ ] `.gitignore` chequeado si se generan artefactos nuevos.

---

## 4 · ADRs — Architecture Decision Records

Cuando se toma una decisión arquitectónica con peso histórico, se documenta como ADR. Un ADR es un archivo Markdown atómico con contexto, decisión, consecuencias y alternativas.

### Cuándo hace falta un ADR

Criterios para saber si una decisión merece ADR:

- **Sí** si afecta el contrato entre componentes (motor ↔ fixture, backend ↔ frontend, etc.).
- **Sí** si establece una convención transversal (zona horaria, auth, naming).
- **Sí** si justifica un desvío respecto a un spec pre-existente.
- **No** si es una decisión interna de implementación sin efecto fuera del módulo (ej. qué estructura de datos usar para un caché interno).
- **No** si el cambio es trivial o puramente estilístico.

Criterio operacional: si dentro de 6 meses alguien se va a preguntar "¿por qué hicimos X?", eso merece ADR.

### Cómo crear uno

1. Copiar `docs/adr/0000-template.md` a `docs/adr/NNNN-slug-corto.md`. Número = siguiente disponible (4 dígitos con ceros).
2. Llenar contexto, decisión, consecuencias, alternativas.
3. Empezar en estado `Proposed`. Cuando se acepta, cambiar a `Accepted` y fecha.
4. **Una vez `Accepted`, el ADR es inmutable.** Si la decisión cambia, se escribe un ADR nuevo que la supersede y se agrega el link `Supersedes: NNNN` en el status del viejo.
5. Actualizar el índice en `docs/adr/README.md`.
6. Referenciar el ADR en el commit y/o en PR.

---

## 5 · Tests

Convenciones de testing:

- `pytest` + `pytest-asyncio` en backend, `vitest` en frontend.
- Nombres descriptivos: `test_data_engine_retries_failed_ticker_up_to_3_times_before_degrading`, no `test_retry`.
- Un test = un comportamiento. Varios asserts son válidos si refieren al mismo comportamiento.
- Tests de invariantes para cada motor/módulo (contratos no negociables).
- Tests de integración mock-first: cada motor se testea aislado mockeando sus dependencias directas.
- Parity tests (capa 2 Validator) viven en `backend/fixtures/parity_reference/`.

Target mínimo de coverage: no se define número duro. Sí se exige que invariantes documentadas en specs tengan test correspondiente.

---

## 6 · Código

### Idioma

- **Código** (nombres de variables, funciones, módulos): inglés.
- **Documentación y comentarios explicativos**: español (sigue convención del equipo).
- **Docstrings**: español. El producto es mono-usuario (Álvaro); no hay contributor anglófono que leer docstrings técnicos.
- **Mensajes de log**: español, para facilitar debugging del usuario final.
- **Mensajes de error visibles al usuario**: español.
- **Mensajes de error internos** (ej. detalles de stack traces para logs): español.

### Docstrings — estilo Google

```python
def analyze(
    ticker: str,
    candles_daily: list[dict],
    candles_1h: list[dict],
    candles_15m: list[dict],
    fixture: dict,
    spy_daily: list[dict] | None = None,
    sim_datetime: str | None = None,
    sim_date: str | None = None,
    bench_daily: list[dict] | None = None,
) -> dict:
    """Ejecuta el scoring completo sobre las velas de un ticker.

    Función pública del Scoring Engine. Stateless, pura, determinística.
    Nunca lanza excepciones hacia el caller: todos los fallos se materializan
    como output estructurado con error=True y error_code.

    Args:
        ticker: Símbolo del activo (ej. "QQQ"). Solo para trazabilidad.
        candles_daily: Velas diarias ordenadas antigua→reciente. Mínimo 40.
        candles_1h: Velas 1H del ticker. Mínimo 25 para warmup.
        candles_15m: Velas 15M del ticker. Mínimo 25 para warmup.
        fixture: Configuración validada del ticker. Ver FIXTURE_SPEC.md.
        spy_daily: Velas daily de SPY. Requerido si fixture usa DivSPY.
        sim_datetime: Timestamp simulado "YYYY-MM-DD HH:MM:SS" ET para ORB gate.
        sim_date: Fecha simulada para slicing sin look-ahead.
        bench_daily: Velas daily del benchmark. Requerido si FzaRel > 0.

    Returns:
        Dict con estructura fija. Siempre incluye: ticker, engine_version,
        fixture_id, fixture_version, score, conf, signal, dir, blocked,
        error, error_code, layers, ind, patterns, sec_rel, div_spy.

    Raises:
        Nothing. Errores operativos se devuelven como {"error": True, ...}.

    Example:
        >>> result = analyze("QQQ", daily, h1, m15, fixture)
        >>> result["conf"]
        'A+'
    """
```

### Type hints

- Obligatorios en firmas de funciones/métodos públicos.
- Recomendados en funciones internas largas o con lógica compleja.
- Preferir los tipos builtins modernos de Python 3.11: `list[dict]`, `str | None`, etc. No `List[Dict]` de `typing`.

### Linting / formatting

Herramientas decididas: `ruff` (linting + formatting, reemplaza flake8 + black). Configuración en `pyproject.toml`. Frontend: `prettier` + `eslint`.

---

## 7 · Flujo típico de una feature

1. Discutir feature con Álvaro → confirmar con "ejecuta".
2. Si requiere decisión arquitectónica nueva → escribir ADR primero.
3. Crear branch `dev/<scope>-<feature>`.
4. Implementar código con docstrings y type hints.
5. Escribir tests que cubran invariantes y casos borde.
6. Actualizar README del módulo si cambia la interfaz pública.
7. Actualizar `FEATURE_DECISIONS.md` si el cambio afecta decisiones operativas.
8. Agregar entrada en `CHANGELOG.md` bajo `[Unreleased]`.
9. Abrir PR con el template completo.
10. Self-review del PR + merge.

---

## 8 · Referencias

- [Conventional Commits](https://www.conventionalcommits.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Semantic Versioning](https://semver.org/)
- [Architecture Decision Records](https://adr.github.io/)
- [Google Python Style Guide — Docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
