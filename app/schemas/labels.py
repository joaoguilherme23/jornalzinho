"""Contratos do catalogo de etiquetas por projeto."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from app.schemas.kanban import LabelRead, Schema

LabelColor = Literal["teal", "blue", "purple", "orange", "red", "gray"]


class LabelCreate(Schema):
    name: str = Field(min_length=1, max_length=80)
    color: LabelColor = "gray"

    @field_validator("name")
    @classmethod
    def label_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name nao pode ser vazio")
        return value


class LabelUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: LabelColor | None = None
    is_archived: bool | None = None

    @field_validator("name", "color", "is_archived")
    @classmethod
    def non_null(cls, value: str | bool | None, info):
        if value is None:
            raise ValueError(f"{info.field_name} nao pode ser nulo")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("name nao pode ser vazio")
        return value
