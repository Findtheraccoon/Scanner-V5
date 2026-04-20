# Architecture Decision Records (ADR)

Registro histórico de decisiones arquitectónicas del Scanner v5. Cada ADR documenta una decisión concreta con su contexto, alternativas evaluadas y consecuencias. **Una vez aceptados, los ADRs son inmutables** — si una decisión cambia, se escribe un ADR nuevo que la supersede.

Para crear un ADR nuevo: copiá `0000-template.md` a `NNNN-slug-corto.md` (siguiente número disponible, 4 dígitos) y rellenalo. Ver proceso completo en `CONTRIBUTING.md §4`.

---

## Índice

| # | Título | Estado | Fecha |
|---|---|---|---|
| [0001](./0001-auth-api-bearer-token.md) | Autenticación API mediante bearer token autogenerado y encriptado en Config | Accepted | 2026-04-20 |
| [0002](./0002-timezone-et-tz-aware.md) | Razonar y persistir en Eastern Time con tz-aware explícito | Accepted | 2026-04-20 |
| [0003](./0003-warmup-parallel-db-first.md) | Warmup paralelo full con consulta previa a DB local | Accepted | 2026-04-20 |
| [0004](./0004-retry-policy-eng060.md) | Política de retry con DEGRADED escalonado ante fallos de fetch | Accepted | 2026-04-20 |
| [0005](./0005-chat-format-in-ws-payload.md) | Generar el bloque `chat_format` en backend y enviarlo en el payload `signal.new` | Accepted | 2026-04-20 |
| [0006](./0006-alembic-hybrid-stamp.md) | Migraciones de DB en modo híbrido — `create_all()` + `alembic stamp head` | Accepted | 2026-04-20 |
| [0007](./0007-visual-style-w-icomat-base.md) | Lenguaje visual — icomat como base, Runpod como vocabulario estructural | Accepted | 2026-04-20 |

---

## Por estado

### Accepted (inmutables)

0001, 0002, 0003, 0004, 0005, 0006, 0007

### Proposed (en discusión)

Ninguno.

### Superseded

Ninguno.

### Deprecated

Ninguno.

---

## Decisiones arquitectónicas previas sin ADR propio

Las siguientes decisiones se tomaron en las sesiones de diseño iniciales (pre-20-abril) y quedaron registradas exclusivamente en `docs/operational/FEATURE_DECISIONS.md`. Se mantienen ahí como fuente viva. Si alguna de estas decisiones se vuelve controvertida o requiere revisión, se promueve a ADR formal.

- Arquitectura de 7 capas del backend.
- Scoring Engine stateless/puro/determinístico (§2.1 FEATURE_DECISIONS).
- 6 slots fijos en el Slot Registry.
- Hot-reload por slot habilitado (desvío del spec original — §11 item 1).
- Trazabilidad completa Opción C con snapshot gzip (§11 item 4).
- Fixtures activas dentro del Config del usuario (§11 item 7).
- Canonical Manager exclusivo del Observatory (§11 item 6).
- Canonicals coexisten múltiples por ticker (§11 item 5).
- Sibling `.metrics.json` separado del JSON de fixture (§11 item 3).
- Warmup 210/80/50 (§11 item 2).
- Stack técnico completo (§5).
- Estructura del repo monorepo (§5.4).

Criterio para promover a ADR: cuando la decisión deba ser defendida frente a una propuesta de cambio, cuando haya que explicar "por qué no lo hicimos de otra manera", o cuando un consumer externo (DESIGNER, auditoría, otro developer) necesite el contexto histórico.

---

## Formato

Todos los ADRs siguen el template `0000-template.md`, con secciones:

- **Status** (Proposed / Accepted / Deprecated / Superseded).
- **Contexto** — qué situación hace necesaria la decisión.
- **Decisión** — qué se elige, explícitamente.
- **Consecuencias** — positivas, negativas/trade-offs, neutras.
- **Alternativas consideradas** — 2-4 opciones que se evaluaron y por qué no se eligieron.
- **Referencias** — links a specs, otros ADRs, issues.
