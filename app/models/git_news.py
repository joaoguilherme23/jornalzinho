"""Estado persistente do gerador de noticias a partir de commits Git."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GitNewsCursor(Base):
    """Ultimo commit percorrido para cada identificador de repositorio."""

    __tablename__ = "git_news_cursors"
    __table_args__ = (
        CheckConstraint("btrim(repository_id) <> ''", name="ck_git_news_cursors_repository_not_blank"),
        CheckConstraint("btrim(last_commit_sha) <> ''", name="ck_git_news_cursors_sha_not_blank"),
    )

    repository_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_commit_sha: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class GitNewsCommit(Base):
    """Commit ja usado em uma noticia, inclusive depois de force-push."""

    __tablename__ = "git_news_commits"
    __table_args__ = (
        CheckConstraint("btrim(repository_id) <> ''", name="ck_git_news_commits_repository_not_blank"),
        CheckConstraint("btrim(commit_sha) <> ''", name="ck_git_news_commits_sha_not_blank"),
        Index("ix_git_news_commits_repository_created", "repository_id", "created_at"),
    )

    repository_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    commit_sha: Mapped[str] = mapped_column(String(128), primary_key=True)
    news_id: Mapped[int] = mapped_column(
        ForeignKey("public_news.id", name="fk_git_news_commits_news_id_public_news", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
