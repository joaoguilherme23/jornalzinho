"""Ambiente Alembic assíncrono, sem URL ou credenciais no arquivo ini."""

from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.settings import Setting
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    """Executa migrations dentro da transação da conexão fornecida."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Gera SQL sem abrir conexão usando a URL tipada de Setting."""

    context.configure(
        url=Setting().DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Abre um engine transitório para a execução CLI online."""

    settings = Setting()
    connectable = create_async_engine(
        settings.DATABASE_URL,
        connect_args=settings.database_connect_args,
        poolclass=pool.NullPool,
        hide_parameters=True,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Prefere conexão síncrona injetada por testes a criar um novo engine."""

    supplied_connection: Any = config.attributes.get("connection")
    if supplied_connection is not None:
        do_run_migrations(supplied_connection)
        return

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
