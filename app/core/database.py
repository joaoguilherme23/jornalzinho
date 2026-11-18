"""Engine e dependencia de sessao assincrona, sem DDL no startup."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.core.settings import Setting


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    # A conexao e criada sob demanda pelas rotas, health ou CLI.
    settings = Setting()
    return create_async_engine(
        settings.DATABASE_URL,
        connect_args=settings.database_connect_args,
        pool_pre_ping=True,
        hide_parameters=True,
    )


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSession(get_engine(), expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        engine = get_engine()
        get_engine.cache_clear()
        await engine.dispose()
