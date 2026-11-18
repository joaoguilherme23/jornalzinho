"""Vinculos de acesso de usuarios a projetos."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProjectMember(Base):
    """Papel atual de um usuario dentro de um projeto."""

    __tablename__ = "project_members"
    __table_args__ = (
        CheckConstraint("role IN ('manager', 'member', 'viewer')", name="ck_project_members_role"),
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        Index("ix_project_members_user_project", "user_id", "project_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_project_members_user_id_users", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", name="fk_project_members_project_id_projects", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
