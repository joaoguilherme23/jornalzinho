"""User and revocable credential models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.idempotency import IdempotencyRequest
    from app.models.task import Comment, Task, TaskHistory


class User(Base):
    """Person with an individual account for the internal board."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_users_name_not_blank"),
        CheckConstraint("btrim(email) <> ''", name="ck_users_email_not_blank"),
        CheckConstraint("email = lower(email)", name="ck_users_email_normalized"),
        CheckConstraint("global_role IN ('admin', 'user')", name="ck_users_global_role"),
        UniqueConstraint("email", name="uq_users_email"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # The service stores normalized lowercase email values before persistence.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    global_role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="user")
    reported_tasks: Mapped[list[Task]] = relationship(
        back_populates="reporter", foreign_keys="Task.reporter_id"
    )
    assigned_tasks: Mapped[list[Task]] = relationship(
        back_populates="assignee", foreign_keys="Task.assignee_id"
    )
    comments: Mapped[list[Comment]] = relationship(back_populates="author")
    task_history: Mapped[list[TaskHistory]] = relationship(back_populates="actor")
    idempotency_requests: Mapped[list[IdempotencyRequest]] = relationship(back_populates="user")


class Session(Base):
    """Revocable credential; never persist a raw session or refresh token."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_sessions_token_hash_sha256"),
        CheckConstraint("expires_at > created_at", name="ck_sessions_expiry_after_creation"),
        UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        Index("ix_sessions_user_id_expires_at", "user_id", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_sessions_user_id_users", ondelete="RESTRICT"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class RetiredRefreshToken(Base):
    """Hash anterior identifica a sessao somente para logout, nunca para refresh."""

    __tablename__ = "retired_refresh_tokens"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_retired_refresh_tokens_sha256"),
        Index("ix_retired_refresh_tokens_session_id", "session_id"),
        Index("ix_retired_refresh_tokens_expires_at", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", name="fk_retired_refresh_tokens_session_id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
