"""Contratos minimizados para a abertura e consulta publica de solicitacoes."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.requests import (
    AttachmentRead,
    RequestCreate,
    RequestEdit,
    RequestResubmit,
    RequestStatus,
    Schema,
)


class PublicRequestCreate(RequestCreate):
    contact: str = Field(min_length=3, max_length=320)


class PublicRequestCreated(Schema):
    protocol: str


class PublicRequestEdit(RequestEdit):
    contact: str = Field(min_length=3, max_length=320)


class PublicRequestEditRead(PublicRequestEdit):
    protocol: str
    status: RequestStatus
    response: str | None
    attachments: list[AttachmentRead]


class PublicRequestResubmit(RequestResubmit):
    pass


class PublicRequestLookup(Schema):
    protocol: str = Field(min_length=12, max_length=64)
    key: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class PublicRequestRead(Schema):
    protocol: str
    name: str
    description: str
    status: RequestStatus
    response: str | None
    created_at: datetime
    reviewed_at: datetime | None
    execution_status: Literal[
        "planned", "in_progress", "waiting", "completed", "archived"
    ] | None
    version: int
