from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    CheckConstraint,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, deferred
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.project import Project
    from app.models.task import Task


class ChangeRequest(Base):
    __tablename__ = "change_requests"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_change_requests_version_positive"),
        CheckConstraint(
            "project_kind IN ('existing','novo_projeto','outro')",
            name="ck_change_requests_project_kind",
        ),
        CheckConstraint(
            "request_type IN ('correcao','dado_novo','melhoria','funcionalidade','novo_projeto','outro')",
            name="ck_change_requests_type",
        ),
        CheckConstraint(
            "urgency IN ('travando','importante','seria_bom')",
            name="ck_change_requests_urgency",
        ),
        CheckConstraint(
            "status IN ('em_avaliacao','ajuste','aprovado','recusado')",
            name="ck_change_requests_status",
        ),
        CheckConstraint("length(btrim(name)) >= 2", name="ck_change_requests_name"),
        CheckConstraint(
            "length(btrim(description)) >= 5", name="ck_change_requests_description"
        ),
        CheckConstraint(
            "length(btrim(purpose)) >= 5", name="ck_change_requests_purpose"
        ),
        CheckConstraint(
            "origin IN ('internal','public')", name="ck_change_requests_origin"
        ),
        UniqueConstraint("task_id", name="uq_change_requests_task"),
        UniqueConstraint("protocol", name="uq_change_requests_protocol"),
        UniqueConstraint(
            "public_idempotency_hash", name="uq_change_requests_public_idempotency"
        ),
        Index("ix_change_requests_requester_created", "requester_id", "created_at"),
        Index("ix_change_requests_project_status", "project_id", "status"),
        Index("ix_change_requests_protocol", "protocol"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requester_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    area: Mapped[str | None] = mapped_column(String(120))
    project_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    project_name: Mapped[str | None] = mapped_column(String(200))
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    type_detail: Mapped[str | None] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(String(500))
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    example_url: Mapped[str | None] = mapped_column(String(1000))
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)
    origin: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="internal"
    )
    contact: Mapped[str | None] = mapped_column(String(320))
    protocol: Mapped[str | None] = mapped_column(String(64))
    public_key_hash: Mapped[str | None] = mapped_column(String(64))
    public_idempotency_hash: Mapped[str | None] = mapped_column(String(64))
    public_payload_hash: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="em_avaliacao"
    )
    response: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requester: Mapped[User | None] = relationship(foreign_keys=[requester_id])
    project: Mapped[Project | None] = relationship(foreign_keys=[project_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
    task: Mapped[Task | None] = relationship(foreign_keys=[task_id])
    attachments: Mapped[list[RequestAttachment]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class RequestAttachment(Base):
    __tablename__ = "request_attachments"
    __table_args__ = (
        CheckConstraint(
            "size > 0 AND size <= 5242880", name="ck_request_attachments_size_positive"
        ),
        Index("ix_request_attachments_request", "request_id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[bytes] = deferred(mapped_column(LargeBinary, nullable=False))
    request: Mapped[ChangeRequest] = relationship(back_populates="attachments")


class PublicRequestRateLimit(Base):
    """Janela persistente por rede, sem conservar o endereco do visitante."""

    __tablename__ = "public_request_rate_limits"
    __table_args__ = (
        CheckConstraint("request_count >= 1", name="ck_public_request_rate_limit_count"),
    )

    network_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
