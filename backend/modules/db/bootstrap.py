"""Inicialización de la DB — `create_all` + `alembic stamp head` o upgrade.

Implementa ADR-0006 (Alembic híbrido):

- **Primer arranque** (DB vacía) → `Base.metadata.create_all()` desde
  los modelos + `alembic stamp head` para marcar la baseline. Deja la
  DB consistente sin necesidad de una migration genesis.
- **Arranques siguientes** → `alembic upgrade head` aplica las migrations
  pendientes.

El módulo provee un único entrypoint `init_db(engine, alembic_cfg=None)`.
Si `alembic_cfg` es `None`, solo se hace `create_all()` sin stamping
(útil para tests con SQLite `:memory:`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from modules.db.models import Base


async def init_db(
    engine: AsyncEngine,
    *,
    alembic_cfg_path: Path | None = None,
) -> None:
    """Inicializa la DB desde cero o aplica migraciones pendientes.

    Args:
        engine: `AsyncEngine` ya construido (ver `session.make_engine`).
        alembic_cfg_path: ruta al `alembic.ini`. Si `None`, se salta
            Alembic (útil para tests con `:memory:`).
    """
    async with engine.begin() as conn:
        tables = await conn.run_sync(_existing_tables)
        if not tables:
            await conn.run_sync(Base.metadata.create_all)
            if alembic_cfg_path is not None:
                await conn.run_sync(_alembic_stamp_head, alembic_cfg_path)
        elif alembic_cfg_path is not None:
            await conn.run_sync(_alembic_upgrade_head, alembic_cfg_path)


def _existing_tables(sync_conn: Any) -> list[str]:
    """Helper sync para `conn.run_sync` — lista tablas existentes."""
    return inspect(sync_conn).get_table_names()


def _alembic_stamp_head(sync_conn: Any, cfg_path: Path) -> None:
    """Marca la baseline de Alembic como `head`."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(cfg_path))
    cfg.attributes["connection"] = sync_conn
    command.stamp(cfg, "head")


def _alembic_upgrade_head(sync_conn: Any, cfg_path: Path) -> None:
    """Aplica migraciones pendientes hasta `head`."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(cfg_path))
    cfg.attributes["connection"] = sync_conn
    command.upgrade(cfg, "head")
