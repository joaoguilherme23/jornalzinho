"""Contratos da solicitação, seus anexos e da avaliação pela equipe."""

from datetime import date, datetime
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RequestStatus = Literal["em_avaliacao", "ajuste", "aprovado", "recusado"]
RequestKind = Literal["existing", "novo_projeto", "outro"]
RequestType = Literal[
    "correcao", "dado_novo", "melhoria", "funcionalidade", "novo_projeto", "outro"
]
RequestUrgency = Literal["travando", "importante", "seria_bom"]
URL_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


class Schema(BaseModel):
    model_config = ConfigDict(
        extra="forbid", str_strip_whitespace=True, from_attributes=True
    )


class AttachmentCreate(Schema):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal[
        "image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"
    ]
    content_base64: str = Field(min_length=4, max_length=6990508)


class AttachmentRead(Schema):
    id: int
    filename: str
    mime_type: str
    size: int


class RequestFields(Schema):
    name: str = Field(min_length=2, max_length=120)
    area: str | None = Field(default=None, max_length=120)
    project_id: int | None = Field(default=None, gt=0)
    project_kind: RequestKind
    project_name: str | None = Field(default=None, max_length=200)
    request_type: RequestType
    type_detail: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=5, max_length=4000)
    location: str | None = Field(default=None, max_length=500)
    purpose: str = Field(min_length=5, max_length=2000)
    example_url: str | None = Field(default=None, max_length=1000)
    urgency: RequestUrgency

    @field_validator("example_url")
    @classmethod
    def safe_example(cls, value: str | None) -> str | None:
        if not value:
            return None
        if (
            any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in value)
            or "\\" in value
        ):
            raise ValueError("O link contém caracteres inválidos.")

        # Domínios copiados sem esquema devem produzir sempre um link HTTPS.
        normalized = value if URL_SCHEME.match(value) else f"https://{value}"
        if len(normalized) > 1000:
            raise ValueError("O link pode ter no máximo 1000 caracteres.")
        url = urlsplit(normalized)
        if (
            url.scheme.lower() not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
        ):
            raise ValueError(
                "Informe um endereço HTTP ou HTTPS válido, sem credenciais."
            )
        try:
            port = url.port
        except ValueError as exc:
            raise ValueError(
                "Informe um endereço HTTP ou HTTPS válido, sem credenciais."
            ) from exc
        if port is not None and not 0 < port < 65536:
            raise ValueError("Informe um endereço HTTP ou HTTPS válido, sem credenciais.")
        return normalized


class RequestCreate(RequestFields):
    attachments: list[AttachmentCreate] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def conditional_fields(self):
        if self.project_kind == "existing" and self.project_id is None:
            raise ValueError("Selecione o projeto.")
        if self.project_kind != "existing":
            if self.project_id is not None:
                raise ValueError("Informe o projeto de destino somente na aprovação.")
            if not self.project_name or len(self.project_name) > 160:
                raise ValueError(
                    "Informe o nome ou ideia do projeto, até 160 caracteres."
                )
        if self.request_type == "outro" and not self.type_detail:
            raise ValueError("Informe qual tipo de pedido.")
        return self


class RequestEdit(RequestFields):
    """Alterações da autora antes de uma tarefa ser criada.

    ``attachments`` contém somente arquivos novos. Os anexos anteriores só são
    apagados quando seus identificadores aparecem em ``remove_attachment_ids``.
    """

    version: int = Field(ge=1)
    attachments: list[AttachmentCreate] = Field(default_factory=list, max_length=3)
    remove_attachment_ids: list[int] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def conditional_fields(self):
        if self.project_kind == "existing" and self.project_id is None:
            raise ValueError("Selecione o projeto.")
        if self.project_kind != "existing":
            if self.project_id is not None:
                raise ValueError("Informe o projeto de destino somente na aprovação.")
            if not self.project_name or len(self.project_name) > 160:
                raise ValueError(
                    "Informe o nome ou ideia do projeto, até 160 caracteres."
                )
        if self.request_type == "outro" and not self.type_detail:
            raise ValueError("Informe qual tipo de pedido.")
        if len(set(self.remove_attachment_ids)) != len(self.remove_attachment_ids):
            raise ValueError("Um anexo só pode ser removido uma vez.")
        return self


class RequestResubmit(Schema):
    version: int = Field(ge=1)


class RequestReview(Schema):
    version: int = Field(ge=1)
    status: RequestStatus
    response: str | None = Field(default=None, max_length=2000)
    assignee_id: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    project_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def response_for_negative_review(self):
        if self.status in {"ajuste", "recusado"} and not self.response:
            raise ValueError("Informe a orientação para o solicitante.")
        return self


class RequestRead(RequestFields):
    id: int
    status: RequestStatus
    response: str | None
    version: int
    created_at: datetime
    reviewed_at: datetime | None
    requester_id: int | None
    reviewer_id: int | None
    origin: Literal["internal", "public"] = "internal"
    contact: str | None = None
    task_id: int | None
    task_code: str | None = None
    board_id: int | None = None
    has_task: bool = False
    can_review: bool
    attachments: list[AttachmentRead]


class RequestList(Schema):
    items: list[RequestRead]
    total: int
    limit: int
    offset: int
    counts: dict[RequestStatus, int]
