# ADR-0006: Migraciones de DB en modo híbrido — `create_all()` + `alembic stamp head`

## Status

**Accepted**

**Fecha:** 2026-04-20
**Autor:** Claude (decisión delegada por Álvaro) + sesión de diseño 20-abril

## Contexto

El Scanner v5 usa SQLite como persistencia primaria (con arquitectura preparada para Postgres en el futuro) y SQLAlchemy 2.0 async como ORM. Alembic está en el stack para migraciones. El producto se distribuye como ejecutable Windows vía Inno Setup y se instala en la máquina del trader — no hay un DBA central, no hay un pipeline de CI/CD que aplique migraciones en un staging antes de prod.

El primer arranque en una máquina nueva (tras instalar) crea la DB desde cero. Hay tres formas clásicas de manejarlo:

1. Migración "genesis" de Alembic que declara todas las tablas desde el día 1. Historial completo.
2. `Base.metadata.create_all()` al primer arranque, Alembic entra en juego cuando haya que modificar. Sin historial inicial.
3. Híbrido: `create_all()` al primer arranque + `alembic stamp head` para marcar la baseline. Historial desde el segundo cambio.

## Decisión

El Scanner v5 implementa la **opción híbrida** (3).

### Flujo en detalle

**Primer arranque en una máquina nueva:**

1. Si la DB (`data/scanner.db`) no existe o está vacía → `Base.metadata.create_all(engine)` crea todas las tablas desde los modelos SQLAlchemy declarados en `backend/modules/db/models.py`.
2. Inmediatamente después → `alembic stamp head` marca la versión baseline en la tabla interna `alembic_version`.
3. El backend arranca normalmente.

**Arranques siguientes (la DB ya existe):**

3. `alembic upgrade head` aplica migraciones pendientes si las hay (desde el punto en que se quedó la DB).

**Modificaciones futuras al schema** (agregar columna, índice, tabla):

4. El desarrollador genera la migración con `alembic revision --autogenerate -m "descripción"`.
5. La migración se commitea en el repo (`backend/alembic/versions/`).
6. El próximo arranque en cualquier máquina la aplica en el paso 3.

### Convenciones

- Modelos SQLAlchemy: `backend/modules/db/models.py` (fuente de verdad del schema hasta la primera migración real).
- Config de Alembic: `backend/alembic.ini`.
- Migraciones versionadas: `backend/alembic/versions/`.
- La primera migración real (cuando aparezca) se llama `0001_<descripcion>` y modifica, no crea tablas base.

## Consecuencias

### Positivas

- **Robustez en distribución:** `create_all()` evita tener que debuggear una migración genesis manual en la máquina de un usuario — si falla algo, es porque SQLAlchemy no puede crear una tabla, que es un error mucho más explícito que una migración de Alembic que se rompe por permisos o por un estado inesperado.
- **Sin duplicación al inicio:** no hay que declarar cada tabla y columna en un archivo `.py` de Alembic si SQLAlchemy puede derivarlo de los modelos. Ahorro de tiempo y de divergencia entre modelos y migración.
- **Alembic queda armado desde el primer arranque:** `alembic stamp head` registra la versión en `alembic_version`, así que la primera migración real se comporta exactamente como cualquier migración subsiguiente.
- **Flujo unificado para desarrolladores:** `alembic revision --autogenerate -m "..."` funciona desde el día 1 sin fricción.

### Negativas / trade-offs

- No hay historial Alembic del schema inicial. Si alguien quiere ver "cómo era la DB en v5.0.0", tiene que leer los modelos de ese commit — no hay una migración `0000_genesis` para inspeccionar.
- Mitigante: los modelos SQLAlchemy en `models.py` están en el repo con historial git; equivalente funcional.
- `alembic history` aparece vacío hasta la primera migración real. Si un desarrollador nuevo corre eso sin contexto, puede confundirse. Mitigado documentando en `CONTRIBUTING.md` y en el README de `backend/modules/db/`.

### Neutras

- Cambiar a migración genesis completa en el futuro (si algún día se quiere) es trivial: generar `alembic revision --autogenerate` sobre una DB vacía, commitear esa migración como `0001_initial_schema`, ajustar el arranque para hacer `upgrade head` siempre en vez de `create_all + stamp`. Migración reversible barata.

## Alternativas consideradas

### Alternativa A: Migración "genesis" completa de Alembic

Escribir `0000_genesis.py` con todas las tablas declaradas manualmente en Alembic. Cualquier máquina nueva corre `alembic upgrade head` y parte del estado 0.
**Por qué no:** trabajo tedioso inicial (cada CREATE TABLE escrito a mano); duplicación entre modelos y migración (ambos declaran las columnas); si se actualizan los modelos y se olvida la migración, la DB queda en estado intermedio que Alembic no sabe reconciliar. Beneficio (historial completo) no justifica el costo en producto distribuido.

### Alternativa B: `create_all()` puro, Alembic sólo cuando haga falta

Sin `alembic stamp head` al arranque inicial. La primera vez que se agregue una columna, hay que hacer el `stamp` manualmente en ese momento + la migración.
**Por qué no:** el paso de `stamp` manual es fácil de olvidar. Cuando se olvida, Alembic cree que la DB está vacía y la primera migración intenta crear tablas que ya existen → error al arranque. La opción híbrida resuelve esto en setup-time automático.

## Referencias

- `docs/operational/FEATURE_DECISIONS.md` §5.7 (Migraciones de DB — híbrido).
- [Alembic — stamp command](https://alembic.sqlalchemy.org/en/latest/cookbook.html#building-an-up-to-date-database-from-scratch)
- [SQLAlchemy 2.0 — Metadata.create_all](https://docs.sqlalchemy.org/en/20/core/metadata.html#sqlalchemy.schema.MetaData.create_all)
