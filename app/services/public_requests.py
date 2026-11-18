"""Persistencia segura da abertura e do acompanhamento publico de solicitacoes."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import case, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import BoardColumn
from app.models.change_request import (
    ChangeRequest,
    PublicRequestRateLimit,
    RequestAttachment,
)
from app.models.publication import ColumnPublication, ProjectPublication
from app.models.task import Task
from app.schemas.public_requests import (
    PublicRequestCreate,
    PublicRequestCreated,
    PublicRequestEdit,
    PublicRequestEditRead,
    PublicRequestLookup,
    PublicRequestRead,
    PublicRequestResubmit,
)
from app.services.kanban import KanbanService, payload_hash
from app.services.requests import OPTIONS, RequestsService, decode_attachment


PUBLIC_RATE_LIMIT = 10
PUBLIC_RATE_WINDOW = timedelta(hours=1)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def idempotency_hash(key: str, request_key: str) -> str:
    """Vincula a chave de repeticao a credencial sem gravar nenhuma das duas."""
    return sha256(f"{key}\x00{request_key}")


def network_hash(address: str | None) -> str:
    """Hasheia um IPv4 individual ou uma rede IPv6 /64 sem reter o endereco."""
    if not address:
        return sha256("unknown")
    try:
        ip = ipaddress.ip_address(address)
        if ip.version == 4:
            return sha256(str(ip))
        network = ipaddress.ip_network(f"{ip}/64", strict=False)
        return sha256(str(network))
    except ValueError:
        return sha256("unknown")


def advisory_lock_value(value: str) -> int:
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "big", signed=True)


class PublicRequestsService:
    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def _consume_rate_limit(self, network: str) -> None:
        now = datetime.now(timezone.utc)
        elapsed = now - PUBLIC_RATE_WINDOW
        statement = (
            insert(PublicRequestRateLimit)
            .values(network_hash=network, window_started_at=now, request_count=1)
            .on_conflict_do_update(
                index_elements=[PublicRequestRateLimit.network_hash],
                set_={
                    "window_started_at": case(
                        (PublicRequestRateLimit.window_started_at <= elapsed, now),
                        else_=PublicRequestRateLimit.window_started_at,
                    ),
                    "request_count": case(
                        (PublicRequestRateLimit.window_started_at <= elapsed, 1),
                        else_=PublicRequestRateLimit.request_count + 1,
                    ),
                },
            )
            .returning(PublicRequestRateLimit.request_count)
        )
        count = await self.db.scalar(statement)
        if count is None or count > PUBLIC_RATE_LIMIT:
            raise HTTPException(
                429,
                "Limite de solicitações atingido. Tente novamente mais tarde.",
                headers={"Retry-After": str(int(PUBLIC_RATE_WINDOW.total_seconds()))},
            )

    async def create(
        self,
        data: PublicRequestCreate,
        request_key: str,
        key: str,
        client_address: str | None,
    ) -> PublicRequestCreated:
        if len(request_key) < 32 or not re.fullmatch(r"[0-9a-fA-F]{64}", key):
            raise HTTPException(422, "A credencial e a chave de repetição são inválidas.")
        credential_digest = sha256(key)
        replay_digest = idempotency_hash(key, request_key)
        body_digest = payload_hash(data.model_dump(mode="json"))

        async with KanbanService(self.db)._transaction():
            # Serializa tentativas iguais antes da verificacao e da criacao do registro.
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": advisory_lock_value(replay_digest)},
            )
            previous = await self.db.scalar(
                select(ChangeRequest).where(
                    ChangeRequest.public_idempotency_hash == replay_digest
                )
            )
            if previous is not None:
                if previous.public_payload_hash != body_digest:
                    raise HTTPException(409, "Idempotency-Key reutilizada com corpo diferente.")
                return PublicRequestCreated(protocol=previous.protocol or "")

            project_name = data.project_name
            if data.project_kind == "existing":
                publication = await self.db.scalar(
                    select(ProjectPublication).where(
                        ProjectPublication.project_id == data.project_id,
                        ProjectPublication.published.is_(True),
                    )
                )
                if publication is None:
                    raise HTTPException(422, "Projeto indisponível para solicitações públicas.")
                project_name = publication.name

            await self._consume_rate_limit(network_hash(client_address))
            values = data.model_dump(exclude={"attachments", "contact"}, mode="json")
            values["project_name"] = project_name
            item = ChangeRequest(
                **values,
                requester_id=None,
                origin="public",
                contact=data.contact,
                protocol=f"PR-{secrets.token_urlsafe(18)}",
                public_key_hash=credential_digest,
                public_idempotency_hash=replay_digest,
                public_payload_hash=body_digest,
                status="em_avaliacao",
                version=1,
            )
            item.attachments = []
            for file in data.attachments:
                filename, content = decode_attachment(
                    file.filename, file.mime_type, file.content_base64
                )
                item.attachments.append(
                    RequestAttachment(
                        filename=filename,
                        mime_type=file.mime_type,
                        size=len(content),
                        content=content,
                    )
                )
            self.db.add(item)
            await self.db.flush()
            return PublicRequestCreated(protocol=item.protocol or "")

    async def editable_item(
        self, protocol: str, key: str, *, lock: bool = False
    ) -> ChangeRequest:
        statement = (
            select(ChangeRequest)
            .where(
                ChangeRequest.protocol == protocol,
                ChangeRequest.origin == "public",
            )
            .options(*OPTIONS)
        )
        if lock:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        item = await self.db.scalar(statement)
        if (
            item is None
            or not item.public_key_hash
            or not hmac.compare_digest(item.public_key_hash, sha256(key))
        ):
            raise HTTPException(404, "Solicitação não encontrada.")
        return item

    @staticmethod
    def editable_read(item: ChangeRequest) -> PublicRequestEditRead:
        values = {
            key: getattr(item, key)
            for key in (
                "name",
                "area",
                "project_id",
                "project_kind",
                "project_name",
                "request_type",
                "type_detail",
                "description",
                "location",
                "purpose",
                "example_url",
                "urgency",
                "version",
                "status",
                "response",
                "contact",
            )
        }
        return PublicRequestEditRead(
            **values,
            protocol=item.protocol or "",
            attachments=[
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "mime_type": attachment.mime_type,
                    "size": attachment.size,
                }
                for attachment in item.attachments
            ],
        )

    async def validate_edit_project(self, data: PublicRequestEdit) -> str | None:
        if data.project_kind != "existing":
            return data.project_name
        publication = await self.db.scalar(
            select(ProjectPublication).where(
                ProjectPublication.project_id == data.project_id,
                ProjectPublication.published.is_(True),
            )
        )
        if publication is None:
            raise HTTPException(422, "Projeto indisponível para solicitações públicas.")
        return publication.name

    async def apply_edit(self, item: ChangeRequest, data: PublicRequestEdit) -> None:
        project_name = await self.validate_edit_project(data)
        existing = {attachment.id: attachment for attachment in item.attachments}
        removed = set(data.remove_attachment_ids)
        if not removed.issubset(existing):
            raise HTTPException(422, "Um dos anexos informados não pertence à solicitação.")
        if len(existing) - len(removed) + len(data.attachments) > 3:
            raise HTTPException(422, "Use no máximo três anexos.")
        values = data.model_dump(
            exclude={
                "version",
                "attachments",
                "remove_attachment_ids",
                "contact",
            },
            mode="json",
        )
        values["project_name"] = project_name
        for field, value in values.items():
            setattr(item, field, value)
        item.contact = data.contact
        item.attachments[:] = [
            attachment
            for attachment in item.attachments
            if attachment.id not in removed
        ]
        for file in data.attachments:
            filename, content = decode_attachment(
                file.filename, file.mime_type, file.content_base64
            )
            item.attachments.append(
                RequestAttachment(
                    filename=filename,
                    mime_type=file.mime_type,
                    size=len(content),
                    content=content,
                )
            )

    async def edit(
        self, protocol: str, key: str, data: PublicRequestEdit
    ) -> PublicRequestEditRead:
        async with KanbanService(self.db)._transaction():
            item = await self.editable_item(protocol, key, lock=True)
            RequestsService.ensure_editable(item)
            if item.version != data.version:
                raise HTTPException(
                    409,
                    "A solicitação foi atualizada. Confira os dados antes de salvar novamente.",
                )
            await self.apply_edit(item, data)
            item.version += 1
            await self.db.flush()
            return self.editable_read(item)

    async def resubmit(
        self, protocol: str, key: str, data: PublicRequestResubmit
    ) -> PublicRequestRead:
        async with KanbanService(self.db)._transaction():
            item = await self.editable_item(protocol, key, lock=True)
            RequestsService.ensure_editable(item)
            if item.version != data.version:
                raise HTTPException(
                    409,
                    "A solicitação foi atualizada. Confira a avaliação antes de reenviar.",
                )
            item.status = "em_avaliacao"
            item.version += 1
            await self.db.flush()
            return await self.lookup(
                PublicRequestLookup(protocol=protocol, key=key)
            )

    async def edit_read(self, protocol: str, key: str) -> PublicRequestEditRead:
        return self.editable_read(await self.editable_item(protocol, key))

    async def lookup(self, data: PublicRequestLookup) -> PublicRequestRead:
        row = (
            await self.db.execute(
                select(
                    ChangeRequest,
                    Task.archived_at,
                    BoardColumn.is_done,
                    ColumnPublication.status,
                )
                .outerjoin(Task, Task.id == ChangeRequest.task_id)
                .outerjoin(BoardColumn, BoardColumn.id == Task.column_id)
                .outerjoin(
                    ColumnPublication,
                    ColumnPublication.column_id == BoardColumn.id,
                )
                .where(
                    ChangeRequest.protocol == data.protocol,
                    ChangeRequest.origin == "public",
                )
            )
        ).first()
        if row is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        item, archived_at, is_done, published_status = row
        if not item.public_key_hash or not hmac.compare_digest(
            item.public_key_hash, sha256(data.key)
        ):
            raise HTTPException(404, "Solicitação não encontrada.")
        execution_status = None
        if item.task_id is not None:
            execution_status = (
                "archived"
                if archived_at is not None
                else "completed"
                if is_done is True
                else published_status if published_status is not None else "planned"
            )
        return PublicRequestRead(
            protocol=item.protocol or "",
            name=item.name,
            description=item.description,
            status=item.status,
            response=item.response,
            created_at=item.created_at,
            reviewed_at=item.reviewed_at,
            execution_status=execution_status,
            version=item.version,
        )
