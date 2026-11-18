"""Modelo de projetos do Kanban."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board
    from app.models.user import User


class Project(Base):
    """Projeto identificado por uma chave estável para a numeração de tasks."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_projects_name_not_blank"),
        CheckConstraint("key ~ '^[A-Z][A-Z0-9_]{0,31}$'", name="ck_projects_key_format"),
        CheckConstraint("next_task_number >= 1", name="ck_projects_next_task_number_positive"),
        CheckConstraint("priority IS NULL OR priority IN ('low', 'medium', 'high')", name="ck_projects_priority"),
        CheckConstraint(
            "status IS NULL OR status IN ('planned', 'in_progress', 'waiting', 'completed')",
            name="ck_projects_portfolio_status",
        ),
        CheckConstraint("portfolio_version >= 1", name="ck_projects_portfolio_version_positive"),
        UniqueConstraint("key", name="uq_projects_key"),
        UniqueConstraint("legacy_app_id", name="uq_projects_legacy_app_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_app_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_projects_owner_id_users", ondelete="RESTRICT"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    milestone_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    milestone_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    links: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb", default=list
    )
    portfolio_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    next_task_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    board: Mapped[Board | None] = relationship(back_populates="project", uselist=False)
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
