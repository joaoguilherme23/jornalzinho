"""Contratos da API de portfólio de projetos."""

from __future__ import annotations

from datetime import date
from enum import Enum
from urllib.parse import urlparse
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.modelos import App


class PortfolioSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PortfolioPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PortfolioStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    COMPLETED = "completed"


class PortfolioLink(PortfolioSchema):
    label: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2_048)

    @field_validator("label")
    @classmethod
    def label_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("label nao pode ser vazio")
        return value

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url deve usar HTTP ou HTTPS")
        return value


class PortfolioUpdateBase(PortfolioSchema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    priority: PortfolioPriority | None = None
    status: PortfolioStatus | None = None
    owner_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    objective: str | None = Field(default=None, max_length=20_000)
    milestone_title: str | None = Field(default=None, min_length=1, max_length=300)
    milestone_due_date: date | None = None
    links: list[PortfolioLink] | None = Field(default=None, max_length=50)

    @field_validator("name", "milestone_title")
    @classmethod
    def text_not_blank(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            if info.field_name == "name":
                raise ValueError("name nao pode ser nulo")
            return None
        value = value.strip()
        if not value:
            raise ValueError("texto nao pode ser vazio")
        return value


class PortfolioAppUpdate(PortfolioUpdateBase):
    version: int = Field(ge=0)


class PortfolioProjectUpdate(PortfolioUpdateBase):
    version: int = Field(ge=1)
    legacy_app_id: str | None = Field(default=None, max_length=255)


class PortfolioOwner(PortfolioSchema):
    id: int
    name: str
    email: str


class PendingTask(PortfolioSchema):
    id: int
    code: str
    title: str
    due_date: date | None
    priority: str


class PortfolioItem(PortfolioSchema):
    role: Literal["admin", "manager", "member", "viewer"]
    ref: str
    project_id: int | None
    legacy_app_id: str | None
    board_id: int | None
    version: int = Field(ge=0)
    name: str
    description: str | None
    priority: PortfolioPriority | None
    status: PortfolioStatus | None
    owner: PortfolioOwner | None
    due_date: date | None
    objective: str | None
    milestone_title: str | None
    milestone_due_date: date | None
    links: list[PortfolioLink]
    pending_tasks: list[PendingTask]
    pending_tasks_total: int = Field(ge=0)
    git: App | None


class PortfolioRead(PortfolioSchema):
    git_collected_at: str
    items: list[PortfolioItem]
