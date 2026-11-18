"""Gera rascunhos de noticias a partir de commits ja sincronizados localmente.

O modulo deliberadamente so le Git. A sincronizacao remota continua sendo
responsabilidade do cron/coletor, para que uma execucao do gerador nunca altere
um clone de trabalho.
"""

from __future__ import annotations

from collections.abc import Iterable, Set
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import subprocess
from threading import Timer
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coletor import ErroGit, _branch_padrao, _git, _ref_da_branch, descobrir_apps
from app.config import Configuracao
from app.models.git_news import GitNewsCommit, GitNewsCursor
from app.models.project import Project
from app.models.publication import ProjectPublication, PublicNews


COMMIT_FIELD_SEPARATOR = "\x1f"
COMMIT_RECORD_SEPARATOR = "\x1e"


class NewsWriter(Protocol):
    async def generate(
        self, *, project_name: str, context: str, commits: list[dict[str, str]]
    ) -> Any: ...


class GitNewsSettings(Protocol):
    auto_publish: bool
    batch_size: int
    max_batches: int
    bootstrap_days: int


@dataclass(frozen=True)
class GitCommit:
    sha: str
    subject: str
    date: str

    def writer_payload(self) -> dict[str, str]:
        """Contrato minimo do redator, sem metadados ou dados pessoais."""

        return {"subject": self.subject}


@dataclass(frozen=True)
class RepositoryRun:
    repository_id: str
    status: str
    commits_seen: int = 0
    news_created: int = 0
    writer_attempts: int = 0
    commits_registered: int = 0
    detail: str | None = None


@dataclass
class GitNewsRun:
    repositories: list[RepositoryRun] = field(default_factory=list)
    batches_created: int = 0
    commits_registered: int = 0
    capped: bool = False

    @property
    def failed(self) -> bool:
        return any(item.status == "error" for item in self.repositories)


def _safe_error(error: Exception) -> str:
    """Retorna uma classificacao sem stderr de Git, payload ou segredo."""

    if isinstance(error, (ErroGit, subprocess.TimeoutExpired, OSError)):
        return "falha ao ler o repositório"
    return "falha ao gerar a notícia"


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    process = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        timeout=30,
        check=False,
    )
    if process.returncode == 0:
        return True
    if process.returncode == 1:
        return False
    raise ErroGit("git merge-base falhou")


@lru_cache(maxsize=1)
def _editorial_catalog() -> dict[str, dict[str, Any]]:
    """Le somente os metadados editoriais que ja sao mantidos pelo mural."""

    source = Path(__file__).resolve().parents[1] / "editorial_catalog.json"
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    apps = data.get("apps") if isinstance(data, dict) else None
    return apps if isinstance(apps, dict) else {}


def _writer_context(repository_id: str, publication: ProjectPublication | None) -> str:
    parts = [
        "Escreva uma notícia pública personalizada somente com base nos commits informados. "
        "Eles registram trabalho no repositório e não comprovam implantação, publicação, "
        "lançamento ou disponibilidade em produção. Não afirme nem insinue esses fatos."
    ]
    if publication and publication.summary:
        parts.append(f"Orientação editorial pública do projeto: {publication.summary.strip()[:2_000]}")
    catalog = _editorial_catalog().get(repository_id)
    if isinstance(catalog, dict):
        description = catalog.get("descricaoEditorial")
        if isinstance(description, str) and description.strip():
            parts.append(f"Descrição editorial: {description.strip()[:1_000]}")
        areas = catalog.get("areas")
        if isinstance(areas, list):
            values = [item.strip() for item in areas if isinstance(item, str) and item.strip()]
            if values:
                parts.append(f"Áreas relacionadas: {', '.join(values[:10])}")
    return "\n".join(parts)


def _parse_commits(raw: str) -> list[GitCommit]:
    commits: list[GitCommit] = []
    for record in raw.split(COMMIT_RECORD_SEPARATOR):
        value = record.strip("\r\n")
        if not value:
            continue
        fields = value.split(COMMIT_FIELD_SEPARATOR)
        if len(fields) != 3:
            continue
        sha, date, subject = (item.strip() for item in fields)
        if sha and date and subject:
            commits.append(GitCommit(sha=sha, date=date, subject=subject))
    return commits


def _oldest_commit_shas(
    repo: Path, revision: str, *, limit: int, since: datetime | None = None, skip_shas: Set[str] | None = None
) -> tuple[list[str], bool]:
    """Le os SHAs mais antigos da faixa sem materializar todo o historico.

    ``git log --reverse -n`` ainda escolhe os commits mais novos antes de os
    inverter. Aqui ``rev-list --reverse`` e consumido em streaming e interrompe
    o processo assim que o orcamento do ciclo for atingido.
    """

    command = ["git", "-C", str(repo), "rev-list", "--topo-order", "--reverse"]
    if since is not None:
        command.append(f"--since={since.isoformat(timespec='seconds')}")
    command.append(revision)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    timeout = 30
    expired = False

    def stop_for_timeout() -> None:
        nonlocal expired
        expired = True
        if process.poll() is None:
            process.terminate()

    timer = Timer(timeout, stop_for_timeout)
    timer.daemon = True
    timer.start()
    shas: list[str] = []
    skip_shas = skip_shas or set()
    capped = False
    try:
        assert process.stdout is not None
        for _ in range(limit + 1):
            value = process.stdout.readline().strip()
            if not value:
                break
            if value in skip_shas:
                continue
            if len(shas) == limit:
                capped = True
                break
            shas.append(value)
        if capped and process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as error:
        if process.poll() is None:
            process.kill()
            process.wait()
        raise subprocess.TimeoutExpired(command, timeout) from error
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
            process.wait()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
    if expired:
        raise subprocess.TimeoutExpired(command, timeout)
    if not capped and process.returncode != 0:
        raise ErroGit("git rev-list falhou")
    return shas, capped


def read_branch_commits(
    repo: Path,
    ref: str,
    *,
    cursor_sha: str | None,
    bootstrap_days: int,
    limit: int,
    skip_shas: Set[str] | None = None,
) -> tuple[list[GitCommit], bool]:
    """Le commits em ordem cronologica e limita o trabalho de um ciclo.

    Quando o cursor deixou de ser ancestral (por exemplo, force-push), a janela
    recente e relida. A tabela de SHAs impede que essa recuperacao crie noticia
    repetida.
    """

    if limit < 1:
        return [], False
    revision: str
    since: datetime | None = None
    if cursor_sha is None:
        days = max(0, bootstrap_days)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        revision = ref
    elif _is_ancestor(repo, cursor_sha, ref):
        revision = f"{cursor_sha}..{ref}"
    else:
        # Force-push: nao mistura a janela inicial de sete dias com o fluxo
        # incremental. Rele somente o trecho limitado no novo grafo; a tabela
        # de SHAs ja publicados elimina repeticoes.
        revision = ref
    shas, capped = _oldest_commit_shas(repo, revision, limit=limit, since=since, skip_shas=skip_shas)
    if not shas:
        return [], capped
    commits = _parse_commits(_git(
        repo, "log", "--no-walk=unsorted", f"--pretty=format:%H%x1f%aI%x1f%s%x1e", *shas
    ))
    return commits, capped


def _source_batches(commits: Iterable[GitCommit], known_shas: set[str], batch_size: int) -> list[list[GitCommit]]:
    """Mantem o cursor no ultimo commit de cada lote, inclusive duplicados."""

    batches: list[list[GitCommit]] = []
    current: list[GitCommit] = []
    fresh = 0
    for commit in commits:
        current.append(commit)
        if commit.sha not in known_shas:
            fresh += 1
        if fresh >= batch_size:
            batches.append(current)
            current, fresh = [], 0
    if current:
        batches.append(current)
    return batches


class GitNewsService:
    """Coordena Git, deduplicacao persistente e a criacao de ``PublicNews``."""

    def __init__(self, session: AsyncSession, *, config: Configuracao, settings: GitNewsSettings, writer: NewsWriter) -> None:
        self.session = session
        self.config = config
        self.settings = settings
        self.writer = writer

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        """Permite leituras antes da escrita sem deixar uma transacao aberta."""

        if not self.session.in_transaction():
            async with self.session.begin():
                yield
            return
        try:
            yield
            await self.session.commit()
        except BaseException:
            await self.session.rollback()
            raise

    async def run(self) -> GitNewsRun:
        result = GitNewsRun()
        batch_size = max(1, self.settings.batch_size)
        max_batches = max(1, self.settings.max_batches)
        applications = descobrir_apps(self.config)
        cursor_rows = (await self.session.scalars(
            select(GitNewsCursor).where(GitNewsCursor.repository_id.in_([item[0] for item in applications]))
        )).all() if applications else []
        cursors = {item.repository_id: item for item in cursor_rows}
        # Repositorios nunca processados vem primeiro; nas proximas rodadas a
        # prioridade gira pelo cursor mais antigo, sem um repo ativo consumir
        # todos os lotes de cada ciclo.
        applications.sort(
            key=lambda item: (
                cursors.get(item[0]) is not None,
                cursors[item[0]].updated_at if item[0] in cursors else datetime.min.replace(tzinfo=timezone.utc),
                item[0],
            )
        )
        remaining_batches = max_batches
        for repository_id, repo in applications:
            if remaining_batches == 0:
                result.repositories.append(RepositoryRun(repository_id, "deferred"))
                continue
            repository_result, capped = await self._run_repository(
                repository_id=repository_id,
                repo=repo,
                batch_size=batch_size,
                max_commits=batch_size * remaining_batches,
            )
            result.repositories.append(repository_result)
            result.batches_created += repository_result.news_created
            result.commits_registered += repository_result.commits_registered
            result.capped = result.capped or capped
            # Conta tambem timeout/429/erro do redator: sem isso um problema de
            # quota permitiria uma chamada por repositorio no mesmo ciclo.
            remaining_batches -= repository_result.writer_attempts
        return result

    async def _run_repository(
        self, *, repository_id: str, repo: Path, batch_size: int, max_commits: int
    ) -> tuple[RepositoryRun, bool]:
        project_row = (await self.session.execute(
            select(Project, ProjectPublication)
            .outerjoin(ProjectPublication, ProjectPublication.project_id == Project.id)
            .where(Project.legacy_app_id == repository_id)
        )).one_or_none()
        if project_row is None:
            return RepositoryRun(repository_id, "unmapped"), False
        project, publication = project_row

        try:
            branch = _branch_padrao(repo)
            ref = _ref_da_branch(repo, branch, self.config.modo) if branch else None
            if not ref:
                return RepositoryRun(repository_id, "no_branch"), False
            ref_sha = _git(repo, "rev-parse", "--verify", ref).strip()
            cursor = await self.session.get(GitNewsCursor, repository_id)
            if cursor is not None and cursor.last_commit_sha == ref_sha:
                return RepositoryRun(repository_id, "unchanged"), False
            known_shas = set((await self.session.scalars(
                select(GitNewsCommit.commit_sha).where(GitNewsCommit.repository_id == repository_id)
            )).all())
            commits, capped = read_branch_commits(
                repo,
                ref_sha,
                cursor_sha=cursor.last_commit_sha if cursor else None,
                bootstrap_days=self.settings.bootstrap_days,
                limit=max_commits,
                skip_shas=known_shas,
            )
        except Exception as error:
            return RepositoryRun(repository_id, "error", detail=_safe_error(error)), False

        batches = _source_batches(commits, known_shas, batch_size)
        created = 0
        writer_attempts = 0
        registered = 0
        try:
            for source_batch in batches:
                candidates = [commit for commit in source_batch if commit.sha not in known_shas]
                if candidates:
                    writer_attempts += 1
                    generated = await self.writer.generate(
                        project_name=publication.name if publication else project.name,
                        context=_writer_context(repository_id, publication),
                        commits=[commit.writer_payload() for commit in candidates],
                    )
                    await self._save_generated_batch(
                        repository_id=repository_id,
                        project_id=project.id,
                        publication=publication,
                        generated=generated,
                        commits=candidates,
                        cursor_sha=source_batch[-1].sha,
                    )
                    known_shas.update(commit.sha for commit in candidates)
                    created += 1
                    registered += len(candidates)
                else:
                    await self._advance_cursor(repository_id, source_batch[-1].sha)
            if not commits:
                # Uma branch rebobinada para fora da janela foi lida com sucesso.
                await self._advance_cursor(repository_id, ref_sha)
        except Exception as error:
            return RepositoryRun(
                repository_id,
                "error",
                commits_seen=len(commits),
                news_created=created,
                writer_attempts=writer_attempts,
                commits_registered=registered,
                detail=_safe_error(error),
            ), capped

        return RepositoryRun(
            repository_id,
            "processed",
            commits_seen=len(commits),
            news_created=created,
            writer_attempts=writer_attempts,
            commits_registered=registered,
        ), capped

    async def _advance_cursor(self, repository_id: str, sha: str) -> None:
        async with self._transaction():
            cursor = await self.session.scalar(
                select(GitNewsCursor).where(GitNewsCursor.repository_id == repository_id).with_for_update()
            )
            if cursor is None:
                self.session.add(GitNewsCursor(repository_id=repository_id, last_commit_sha=sha))
            else:
                cursor.last_commit_sha = sha
            await self.session.flush()

    async def _save_generated_batch(
        self,
        *,
        repository_id: str,
        project_id: int,
        publication: ProjectPublication | None,
        generated: Any,
        commits: list[GitCommit],
        cursor_sha: str,
    ) -> None:
        """Persiste noticia, SHAs e cursor juntos; falha nao consome commits."""

        async with self._transaction():
            duplicates = set((await self.session.scalars(
                select(GitNewsCommit.commit_sha).where(
                    GitNewsCommit.repository_id == repository_id,
                    GitNewsCommit.commit_sha.in_([commit.sha for commit in commits]),
                )
            )).all())
            fresh = [commit for commit in commits if commit.sha not in duplicates]
            if fresh:
                auto_publish = bool(self.settings.auto_publish and publication and publication.published)
                now = datetime.now(timezone.utc)
                news = PublicNews(
                    title=generated.title,
                    summary=generated.summary,
                    body=generated.body,
                    project_id=project_id,
                    published=auto_publish,
                    published_at=now if auto_publish else None,
                    version=1,
                )
                self.session.add(news)
                await self.session.flush()
                self.session.add_all(
                    GitNewsCommit(repository_id=repository_id, commit_sha=commit.sha, news_id=news.id)
                    for commit in fresh
                )
            cursor = await self.session.scalar(
                select(GitNewsCursor).where(GitNewsCursor.repository_id == repository_id).with_for_update()
            )
            if cursor is None:
                self.session.add(GitNewsCursor(repository_id=repository_id, last_commit_sha=cursor_sha))
            else:
                cursor.last_commit_sha = cursor_sha
            await self.session.flush()
