"""Contratos Pydantic da API de projetos e tarefas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.models.task import TaskPriority, TaskType

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ReadSchema(Schema):
    model_config = ConfigDict(extra="forbid", from_attributes=True, populate_by_name=True)


class Page(ReadSchema, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)


class UserRead(ReadSchema):
    id: int
    name: str
    email: str


class ProjectCreate(Schema):
    key: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z][A-Z0-9_]{0,31}$")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    legacy_app_id: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def project_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name nao pode ser vazio")
        return value


class ProjectRead(ReadSchema):
    id: int
    key: str
    name: str
    description: str | None
    legacy_app_id: str | None
    default_board_id: int | None
    role: str


class BoardColumnCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    is_done: bool = False

    @field_validator("name")
    @classmethod
    def column_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name nao pode ser vazio")
        return value


class BoardColumnUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_done: bool | None = None
    position: int | None = Field(default=None, ge=0)

    @field_validator("name", "is_done", "position")
    @classmethod
    def update_column_required_fields(cls, value: str | bool | int | None, info: ValidationInfo) -> str | bool | int:
        if value is None:
            raise ValueError(f"{info.field_name} nao pode ser nulo")
        if info.field_name == "name":
            value = value.strip()  # type: ignore[union-attr]
            if not value:
                raise ValueError("name nao pode ser vazio")
        return value


class BoardColumnRead(ReadSchema):
    id: int
    name: str
    position: int
    is_done: bool


class BoardUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    default_column_id: int | None = Field(default=None, gt=0)

    @field_validator("name", "default_column_id")
    @classmethod
    def update_board_required_fields(cls, value: str | int | None, info: ValidationInfo) -> str | int:
        if value is None:
            raise ValueError(f"{info.field_name} nao pode ser nulo")
        if info.field_name == "name":
            value = value.strip()  # type: ignore[union-attr]
            if not value:
                raise ValueError("name nao pode ser vazio")
        return value


class ProjectSummary(ReadSchema):
    id: int
    key: str
    name: str


class ColumnSummary(ReadSchema):
    id: int
    name: str
    is_done: bool


class LabelRead(ReadSchema):
    id: int
    project_id: int
    name: str
    color: str
    is_archived: bool


class TaskCreate(Schema):
    board_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=50_000)
    priority: TaskPriority = TaskPriority.MEDIUM
    task_type: TaskType = Field(default=TaskType.TASK, alias="type")
    assignee_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    label_ids: list[int] = Field(default_factory=list)

    @field_validator("label_ids")
    @classmethod
    def task_create_labels(cls, value: list[int]) -> list[int]:
        if any(identifier < 1 for identifier in value):
            raise ValueError("label_ids deve conter identificadores positivos")
        if len(set(value)) != len(value):
            raise ValueError("label_ids nao pode conter duplicidades")
        return sorted(value)

    @field_validator("title")
    @classmethod
    def task_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title nao pode ser vazio")
        return value


class TaskUpdate(Schema):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=50_000)
    priority: TaskPriority | None = None
    task_type: TaskType | None = Field(default=None, alias="type")
    assignee_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    label_ids: list[int] | None = None

    @field_validator("label_ids")
    @classmethod
    def task_update_labels(cls, value: list[int] | None) -> list[int]:
        if value is None:
            raise ValueError("label_ids nao pode ser nulo")
        if any(identifier < 1 for identifier in value):
            raise ValueError("label_ids deve conter identificadores positivos")
        if len(set(value)) != len(value):
            raise ValueError("label_ids nao pode conter duplicidades")
        return sorted(value)

    @field_validator("title", "priority", "task_type")
    @classmethod
    def update_task_required_fields(
        cls, value: str | TaskPriority | TaskType | None, info: ValidationInfo
    ) -> str | TaskPriority | TaskType:
        if value is None:
            field_name = "type" if info.field_name == "task_type" else info.field_name
            raise ValueError(f"{field_name} nao pode ser nulo")
        if info.field_name == "title":
            value = value.strip()  # type: ignore[union-attr]
            if not value:
                raise ValueError("title nao pode ser vazio")
        return value


class TaskMove(Schema):
    column_id: int = Field(gt=0)
    position: int = Field(ge=0)
    version: int = Field(ge=1)


class TaskRead(ReadSchema):
    id: int
    code: str
    board_id: int
    project_id: int
    role: str
    title: str
    description: str | None
    column_id: int
    column: ColumnSummary
    priority: TaskPriority
    task_type: TaskType = Field(alias="type")
    reporter: UserRead
    assignee: UserRead | None
    due_date: date | None
    position: int
    version: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    archived_at: datetime | None
    labels: list[LabelRead]


class BoardRead(ReadSchema):
    id: int
    name: str
    project: ProjectSummary
    role: str
    default_column_id: int | None
    columns: list[BoardColumnRead]
    tasks: list[TaskRead]
    tasks_total: int = Field(ge=0)
    tasks_offset: int = Field(ge=0)
    tasks_limit: int = Field(ge=1, le=200)


class CommentCreate(Schema):
    body: str = Field(min_length=1, max_length=20_000)

    @field_validator("body")
    @classmethod
    def comment_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("body nao pode ser vazio")
        return value


class CommentRead(ReadSchema):
    id: int
    task_id: int
    author: UserRead
    body: str
    created_at: datetime
    updated_at: datetime


class TaskHistoryRead(ReadSchema):
    id: int
    event: str
    actor: UserRead
    old_value: dict[str, object] | None
    new_value: dict[str, object] | None
    created_at: datetime


IdempotencyKey = UUID
