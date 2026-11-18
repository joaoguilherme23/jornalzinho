"""CLI do gerador de noticias Git, executada pelo agendador a cada 30 minutos."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Configuracao, ConfiguracaoInvalida, carregar
from app.core.database import get_engine
from app.models.project import Project
from app.models.git_news import GitNewsCommit, GitNewsCursor
from app.services.git_news import GitNewsService


GIT_NEWS_ADVISORY_LOCK = 2_026_092_506


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Gera rascunhos de noticias a partir dos commits Git.")
    value.add_argument("--check", action="store_true", help="valida configuracao e schema sem ler Git ou chamar o modelo")
    return value


async def _try_lock(connection: Any) -> bool:
    return bool(await connection.scalar(select(func.pg_try_advisory_lock(GIT_NEWS_ADVISORY_LOCK))))


async def _unlock(connection: Any) -> None:
    try:
        await connection.execute(text("SELECT pg_advisory_unlock(:lock_key)"), {"lock_key": GIT_NEWS_ADVISORY_LOCK})
        await connection.commit()
    except BaseException:
        # Se a conexao voltar viva ao pool apos erro no unlock, o lock de sessao
        # permaneceria preso naquele backend PostgreSQL.
        await connection.invalidate()
        raise


async def run(
    *,
    check: bool = False,
    config: Configuracao | None = None,
    settings: Any | None = None,
    writer: Any | None = None,
    engine: AsyncEngine | None = None,
) -> dict[str, Any]:
    """Executa sem importar FastAPI; argumentos permitem testes sem ``.env``."""

    if config is None:
        config = carregar()
    if settings is None:
        from app.services.news_writer import NewsWriterSettings

        settings = NewsWriterSettings()
    engine = engine or get_engine()
    if check:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            mapped_projects = await session.scalar(
                select(func.count()).select_from(Project).where(Project.legacy_app_id.is_not(None))
            )
            cursors = await session.scalar(select(func.count()).select_from(GitNewsCursor))
            registered_commits = await session.scalar(select(func.count()).select_from(GitNewsCommit))
        return {
            "ok": True,
            "enabled": bool(settings.enabled),
            "mapped_projects": mapped_projects or 0,
            "cursors": cursors or 0,
            "registered_commits": registered_commits or 0,
        }
    if not settings.enabled:
        return {"ok": True, "enabled": False, "status": "disabled"}
    if writer is None:
        from app.services.news_writer import OpenAINewsWriter

        # A chave e resolvida somente no caminho habilitado; --check e o
        # estado disabled seguem uteis em ambientes sem segredo.
        settings.require_api_key()
        writer = OpenAINewsWriter(settings)
    async with engine.connect() as lock_connection:
        try:
            acquired = await _try_lock(lock_connection)
            if acquired:
                # Fecha apenas a transacao que adquiriu o lock; o lock e de
                # sessao e continua preso nesta conexao dedicada.
                await lock_connection.commit()
        except BaseException:
            # Um cancelamento pode ocorrer depois de PostgreSQL aceitar o lock
            # e antes de a coroutine receber o resultado. A conexao nao pode
            # voltar ao pool nesse estado incerto.
            await lock_connection.invalidate()
            raise
        if not acquired:
            return {"ok": True, "enabled": True, "status": "locked"}
        try:
            # O lock de sessao fica preso nesta conexao exclusiva; as
            # transacoes de escrita usam outra sessao e nao seguram a web.
            async with AsyncSession(engine, expire_on_commit=False) as session:
                summary = await GitNewsService(
                    session, config=config, settings=settings, writer=writer
                ).run()
            return {
                "ok": not summary.failed,
                "enabled": True,
                "status": "completed" if not summary.failed else "completed_with_errors",
                "repositories": [
                    {
                        "repository_id": item.repository_id,
                        "status": item.status,
                        "commits_seen": item.commits_seen,
                        "news_created": item.news_created,
                        "detail": item.detail,
                    }
                    for item in summary.repositories
                ],
                "batches_created": summary.batches_created,
                "writer_attempts": sum(item.writer_attempts for item in summary.repositories),
                "commits_registered": summary.commits_registered,
                "capped": summary.capped,
            }
        finally:
            # Falha no unlock invalida a conexao; ela nunca volta viva ao pool
            # com um advisory lock de sessao potencialmente retido.
            await _unlock(lock_connection)


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        result = asyncio.run(run(check=arguments.check))
    except ConfiguracaoInvalida as error:
        print(json.dumps({"ok": False, "status": "invalid_configuration", "detail": str(error)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"ok": False, "status": "failed"}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
