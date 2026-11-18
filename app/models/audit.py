"""Registro imutavel de alteracoes administrativas, sem credenciais."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AdminAuditLog(Base):
    """Audita administracao de contas e vinculos com valores nao sensiveis."""

    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_admin_audit_logs_actor_id_users", ondelete="RESTRICT"), nullable=True
    )
    subject_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_admin_audit_logs_subject_user_id_users", ondelete="RESTRICT"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", name="fk_admin_audit_logs_project_id_projects", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="api")
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
