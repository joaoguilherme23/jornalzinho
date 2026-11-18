"""Modelos da camada de publicação pública do kanban."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectPublication(Base):
    """Texto e estado de publicação de um projeto existente."""

    __tablename__ = "project_publications"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_project_publications_name_not_blank"),
        CheckConstraint("version >= 1", name="ck_project_publications_version_positive"),
        Index("ix_project_publications_published", "published"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", name="fk_project_publications_project_id_projects", ondelete="RESTRICT"),
        primary_key=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class TaskPublication(Base):
    """Texto e estado de publicação de uma task existente."""

    __tablename__ = "task_publications"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="ck_task_publications_title_not_blank"),
        CheckConstraint("version >= 1", name="ck_task_publications_version_positive"),
        Index("ix_task_publications_published", "published"),
    )

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", name="fk_task_publications_task_id_tasks", ondelete="RESTRICT"), primary_key=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ColumnPublication(Base):
    """Status público de uma coluna que ainda não está concluída."""

    __tablename__ = "column_publications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('planned', 'in_progress', 'waiting')",
            name="ck_column_publications_status",
        ),
    )

    column_id: Mapped[int] = mapped_column(
        ForeignKey("board_columns.id", name="fk_column_publications_column_id_board_columns", ondelete="CASCADE"),
        primary_key=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="planned")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PublicNews(Base):
    """Notícia redigida para o site público, opcionalmente vinculada a um projeto."""

    __tablename__ = "public_news"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="ck_public_news_title_not_blank"),
        CheckConstraint("btrim(body) <> ''", name="ck_public_news_body_not_blank"),
        CheckConstraint("version >= 1", name="ck_public_news_version_positive"),
        Index("ix_public_news_published_at", "published", "published_at"),
        Index("ix_public_news_project_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", name="fk_public_news_project_id_projects", ondelete="RESTRICT"), nullable=True
    )
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
