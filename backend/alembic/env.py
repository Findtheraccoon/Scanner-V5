"""Alembic env.py — entrypoint de las migraciones.

Soporta dos modos de operación:

1. **Offline:** genera SQL sin conectarse a una DB (útil para revisar
   qué aplicaría antes de ejecutar).
2. **Online:** aplica migraciones contra una DB real. Acepta una
   `Connection` externa vía `config.attributes["connection"]` (flujo
   usado por `bootstrap.init_db` para correr stamp/upgrade dentro de
   la misma transacción async que el `create_all`).

Target metadata = `modules.db.models.Base.metadata`.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure `backend/` está en sys.path para que funcione `from modules...`.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from modules.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Modo offline — genera SQL sin conexión real."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Modo online — aplica contra una DB.

    Si el caller pasó una `connection` vía `config.attributes`, la usa
    directamente (flujo de `bootstrap.init_db`). Caso contrario, crea
    un engine desde la URL del `.ini`.
    """
    connection = config.attributes.get("connection", None)
    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
