"""Contratos das APIs pública e administrativa de publicação."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.kanban import Page, ReadSchema, Schema


PublicationStatus = Literal["planned", "in_progress", "waiting"]
PublicWorkStatus = Literal["planned", "in_progress", "waiting", "completed"]


class _TextInput(Schema):
    @field_validator("name", "title", "body", check_fields=False)
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("campo nao pode ser vazio")
        return value


class ProjectPublicationUpdate(_TextInput):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=20_000)
    published: bool
    version: int = Field(ge=0)


class TaskPublicationUpdate(_TextInput):
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=50_000)
    published: bool
    version: int = Field(ge=0)


class ColumnPublicationUpdate(Schema):
    status: PublicationStatus


class NewsCreate(_TextInput):
    title: str = Field(min_length=1, max_length=300)
    summary: str | None = Field(default=None, max_length=20_000)
    body: str = Field(min_length=1, max_length=100_000)
    project_id: int | None = Field(default=None, gt=0)
    published: bool = False


class NewsUpdate(NewsCreate):
    version: int = Field(ge=1)


class PublicProjectRead(ReadSchema):
    id: int
    name: str
    summary: str | None


class PublicWorkRead(ReadSchema):
    code: str
    title: str
    summary: str | None
    project_id: int
    project_name: str
    status: PublicWorkStatus
    updated_at: datetime


class PublicNewsRead(ReadSchema):
    id: int
    title: str
    summary: str | None
    body: str
    project_name: str | None
    published_at: datetime | None


class PublicationProjectListItem(ReadSchema):
    id: int
    name: str
    can_publish: bool


class PublicationProjectRead(ReadSchema):
    id: int
    name: str
    summary: str | None
    published: bool
    version: int = Field(ge=0)


class PublicationColumnRead(ReadSchema):
    id: int
    name: str
    is_done: bool
    status: PublicWorkStatus


class PublicationTaskRead(ReadSchema):
    id: int
    code: str
    internal_title: str
    title: str
    summary: str | None
    published: bool
    version: int = Field(ge=0)


class PublicationProjectDetail(ReadSchema):
    project: PublicationProjectRead
    columns: list[PublicationColumnRead]
    tasks: list[PublicationTaskRead]


class PublicationNewsRead(ReadSchema):
    id: int
    title: str
    summary: str | None
    body: str
    project_id: int | None
    published: bool
    published_at: datetime | None
    version: int


PublicWorkPage = Page[PublicWorkRead]
PublicNewsPage = Page[PublicNewsRead]
PublicationProjectPage = Page[PublicationProjectListItem]
PublicationNewsPage = Page[PublicationNewsRead]
