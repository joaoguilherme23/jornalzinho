"""Schemas publicos de autenticacao, usuarios e equipe."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def normalizar_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or "@" not in email or any(char.isspace() for char in email):
        raise ValueError("email invalido")
    return email


def validar_senha(value: str) -> str:
    tamanho = len(value.encode("utf-8"))
    if tamanho < 12 or tamanho > 72:
        raise ValueError("senha deve ter entre 12 e 72 bytes em UTF-8")
    return value


def validar_senha_login(value: str) -> str:
    tamanho = len(value.encode("utf-8"))
    if tamanho < 1 or tamanho > 72:
        raise ValueError("senha deve ter entre 1 e 72 bytes em UTF-8")
    return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str

    @field_validator("email")
    @classmethod
    def email_normalizado(cls, value: str) -> str:
        return normalizar_email(value)

    @field_validator("password")
    @classmethod
    def senha_valida(cls, value: str) -> str:
        return validar_senha_login(value)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    is_active: bool
    global_role: Literal["admin", "user"]
    must_change_password: bool


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic
    expires_in: int = 900
    session_expires_at: datetime
    server_time: datetime


class UserListResponse(BaseModel):
    items: list[UserPublic]
    total: int
    offset: int
    limit: int


ProjectRole = Literal["manager", "member", "viewer"]
ProjectAccessScope = Literal["all", "selected"]


class ProjectAccess(BaseModel):
    """Selecao explicita de projetos a vincular a uma conta."""

    model_config = ConfigDict(extra="forbid")

    scope: ProjectAccessScope
    project_ids: list[Annotated[int, Field(gt=0)]] | None = None
    role: ProjectRole = "member"

    @model_validator(mode="after")
    def validate_scope(self) -> "ProjectAccess":
        provided_ids = "project_ids" in self.model_fields_set
        if self.scope == "all":
            if provided_ids:
                raise ValueError("project_ids nao pode ser informado quando scope for all")
            return self
        if not provided_ids or not self.project_ids:
            raise ValueError("project_ids e obrigatorio e nao pode ser vazio quando scope for selected")
        if len(self.project_ids) != len(set(self.project_ids)):
            raise ValueError("project_ids nao pode conter duplicados")
        return self


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str
    global_role: Literal["admin", "user"] = "user"
    project_access: ProjectAccess | None = None

    _email = field_validator("email")(normalizar_email)
    _password = field_validator("password")(validar_senha)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("nome nao pode ser vazio")
        return value

    @model_validator(mode="after")
    def reject_null_project_access(self) -> "UserCreate":
        if "project_access" in self.model_fields_set and self.project_access is None:
            raise ValueError("project_access nao pode ser nulo")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    is_active: bool | None = None
    global_role: Literal["admin", "user"] | None = None

    @field_validator("name")
    @classmethod
    def update_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("nome nao pode ser vazio")
        return value

    @field_validator("email")
    @classmethod
    def update_email(cls, value: str | None) -> str | None:
        return normalizar_email(value) if value is not None else None

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "UserUpdate":
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} nao pode ser nulo")
        return self


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str
    _password = field_validator("password")(validar_senha)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str
    _current = field_validator("current_password")(validar_senha_login)
    _new = field_validator("new_password")(validar_senha)


class MemberUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    role: ProjectRole
    _email = field_validator("email")(normalizar_email)


class ProjectParticipant(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    is_active: bool


class ProjectMemberPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user: ProjectParticipant
    role: ProjectRole


class UserMembershipPublic(BaseModel):
    project_id: int
    project_key: str
    project_name: str
    role: ProjectRole


class MembershipBulkRequest(BaseModel):
    """Adiciona ou remove vinculos de um usuario como uma unica operacao."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["add", "remove"]
    scope: ProjectAccessScope
    project_ids: list[Annotated[int, Field(gt=0)]] | None = None
    role: ProjectRole | None = None

    @model_validator(mode="after")
    def validate_bulk_operation(self) -> "MembershipBulkRequest":
        provided_ids = "project_ids" in self.model_fields_set
        if self.scope == "all":
            if provided_ids:
                raise ValueError("project_ids nao pode ser informado quando scope for all")
        elif not provided_ids or not self.project_ids:
            raise ValueError("project_ids e obrigatorio e nao pode ser vazio quando scope for selected")
        elif len(self.project_ids) != len(set(self.project_ids)):
            raise ValueError("project_ids nao pode conter duplicados")
        if self.action == "remove" and "role" in self.model_fields_set:
            raise ValueError("role nao pode ser informado ao remover vinculos")
        if self.action == "add" and "role" in self.model_fields_set and self.role is None:
            raise ValueError("role nao pode ser nulo ao adicionar vinculos")
        return self


class MembershipBulkResult(BaseModel):
    added: int
    removed: int
    unchanged: int
