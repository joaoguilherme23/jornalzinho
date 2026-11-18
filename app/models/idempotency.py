"""Persistência mínima para reprocessar requisições idempotentes."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class IdempotencyRequest(Base):
    """Chave, hash do corpo e referência ao recurso sem reter o payload original."""

    __tablename__ = "idempotency_requests"
    __table_args__ = (
        CheckConstraint("btrim(operation) <> ''", name="ck_idempotency_requests_operation_not_blank"),
        CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_idempotency_requests_payload_hash_sha256"),
        CheckConstraint("btrim(resource_type) <> ''", name="ck_idempotency_requests_resource_type_not_blank"),
        CheckConstraint("resource_id > 0", name="ck_idempotency_requests_resource_id_positive"),
        UniqueConstraint("user_id", "operation", "request_key", name="uq_idempotency_requests_user_operation_key"),
        Index("ix_idempotency_requests_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_idempotency_requests_user_id_users", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    request_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="idempotency_requests")
