"""Solicitações da equipe e aprovação atômica para o quadro de tarefas."""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, undefer

from app.models import (
    Board,
    BoardColumn,
    Project,
    Task,
    TaskHistory,
    User,
)
from app.models.audit import AdminAuditLog
from app.models.change_request import ChangeRequest, RequestAttachment
from app.models.membership import ProjectMember
from app.schemas.requests import (
    AttachmentRead,
    RequestCreate,
    RequestEdit,
    RequestList,
    RequestRead,
    RequestResubmit,
    RequestReview,
)
from app.services.access import AccessService
from app.services.kanban import KanbanService, payload_hash

STATUSES = ("em_avaliacao", "ajuste", "aprovado", "recusado")
FILE_LIMIT = 5 * 1024 * 1024
OPTIONS = (selectinload(ChangeRequest.attachments),)


def decode_attachment(filename: str, mime_type: str, encoded: str) -> tuple[str, bytes]:
    """Verifica tamanho e assinatura antes de persistir o arquivo privado."""
    if len(encoded) > ((FILE_LIMIT + 2) // 3) * 4:
        raise HTTPException(422, "Cada anexo deve ter até 5 MB.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, "Conteúdo de anexo inválido.") from exc
    if not content or len(content) > FILE_LIMIT:
        raise HTTPException(422, "Cada anexo deve ter entre 1 byte e 5 MB.")
    signatures = {
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/gif": content[:6] in (b"GIF87a", b"GIF89a"),
        "image/webp": content[:4] == b"RIFF" and content[8:12] == b"WEBP",
        "application/pdf": content.startswith(b"%PDF-"),
    }
    if not signatures.get(mime_type):
        raise HTTPException(422, "Anexo incompatível: use PNG, JPG, WEBP, GIF ou PDF.")
    name = re.sub(
        r"[\x00-\x1f\x7f]", "", filename.replace("\\", "/").split("/")[-1]
    ).strip()
    return name[:255] or "anexo", content


class RequestsService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.access = AccessService(session)

    async def managed_ids(self, user: User) -> list[int]:
        return list(
            await self.db.scalars(
                select(ProjectMember.project_id).where(
                    ProjectMember.user_id == user.id,
                    ProjectMember.role == "manager",
                )
            )
        )

    async def scope(self, user: User):
        if user.global_role == "admin":
            return True
        managed = await self.managed_ids(user)
        return or_(
            ChangeRequest.requester_id == user.id,
            (ChangeRequest.project_kind == "existing")
            & ChangeRequest.project_id.in_(managed),
        )

    async def can_review(self, item: ChangeRequest, user: User) -> bool:
        return user.global_role == "admin" or (
            item.project_kind == "existing"
            and item.project_id in await self.managed_ids(user)
        )

    async def item(
        self, request_id: int, user: User, *, lock: bool = False
    ) -> ChangeRequest:
        statement = (
            select(ChangeRequest)
            .where(ChangeRequest.id == request_id, await self.scope(user))
            .options(*OPTIONS)
        )
        if lock:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        item = await self.db.scalar(statement)
        if item is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        return item

    async def read(self, item: ChangeRequest, user: User) -> RequestRead:
        board_id = task_code = None
        public_task_id = None
        # Autoria da solicitação não concede acesso ao projeto da tarefa.
        if item.task_id:
            visible = await self.access.visible_project_ids(user)
            row = (
                await self.db.execute(
                    select(Task.id, Task.board_id, Task.number, Project.key, Project.id)
                    .join(Board, Board.id == Task.board_id)
                    .join(Project, Project.id == Board.project_id)
                    .where(Task.id == item.task_id)
                )
            ).first()
            if row and (visible is None or row[4] in visible):
                public_task_id, board_id = row[0], row[1]
                task_code = f"{row[3]}-{row[2]}"
        values = {
            key: getattr(item, key)
            for key in (
                "id",
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
                "status",
                "response",
                "version",
                "created_at",
                "reviewed_at",
                "requester_id",
                "reviewer_id",
                "origin",
                "contact",
            )
        }
        return RequestRead(
            **values,
            task_id=public_task_id,
            task_code=task_code,
            board_id=board_id,
            has_task=item.task_id is not None,
            can_review=await self.can_review(item, user),
            attachments=[
                AttachmentRead(
                    id=a.id, filename=a.filename, mime_type=a.mime_type, size=a.size
                )
                for a in item.attachments
            ],
        )

    async def list(
        self, user: User, status: str | None, offset: int, limit: int
    ) -> RequestList:
        scope = await self.scope(user)
        counts = dict.fromkeys(STATUSES, 0)
        counts.update(
            dict(
                (
                    await self.db.execute(
                        select(ChangeRequest.status, func.count())
                        .where(scope)
                        .group_by(ChangeRequest.status)
                    )
                ).all()
            )
        )
        condition = ChangeRequest.status == status if status else True
        items = (
            await self.db.scalars(
                select(ChangeRequest)
                .where(scope, condition)
                .options(*OPTIONS)
                .order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
        return RequestList(
            items=[await self.read(item, user) for item in items],
            total=counts[status] if status else sum(counts.values()),
            counts=counts,
            limit=limit,
            offset=offset,
        )

    async def locked_actor(self, user: User) -> User:
        actor = await self.db.scalar(
            select(User)
            .where(User.id == user.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active:
            raise HTTPException(403, "Conta indisponível.")
        self.access.require_ready(actor)
        return actor

    async def create(self, data: RequestCreate, user: User, key: UUID) -> RequestRead:
        digest = payload_hash(data.model_dump(mode="json"))
        kanban = KanbanService(self.db)
        async with kanban._transaction():
            actor = await self.locked_actor(user)
            previous = await kanban._idempotency(
                actor.id, "create_request", key, digest
            )
            if previous:
                return await self.read(
                    await self.item(previous.resource_id, actor), actor
                )
            # A small per-account quota also bounds repeated large uploads.
            recent = await self.db.scalar(
                select(func.count())
                .select_from(ChangeRequest)
                .where(
                    ChangeRequest.requester_id == actor.id,
                    ChangeRequest.created_at
                    >= datetime.now(timezone.utc) - timedelta(hours=1),
                )
            )
            if recent and recent >= 20:
                raise HTTPException(
                    429,
                    "Limite de 20 solicitações por hora. Tente novamente mais tarde.",
                )
            project_name = data.project_name
            if data.project_kind == "existing":
                await self.access.require_project(actor, data.project_id)
                project_name = await self.db.scalar(
                    select(Project.name).where(Project.id == data.project_id)
                )
            values = data.model_dump(exclude={"attachments"}, mode="json")
            values["project_name"] = project_name
            item = ChangeRequest(
                **values,
                requester_id=actor.id,
                origin="internal",
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
            kanban._record_idempotency(
                actor.id, "create_request", key, digest, "request", item.id
            )
            await self.db.flush()
            return await self.read(item, actor)

    async def editable_item(
        self, request_id: int, user: User, *, lock: bool = False
    ) -> ChangeRequest:
        """Carrega apenas uma solicitação interna da sua própria autora."""
        statement = (
            select(ChangeRequest)
            .where(
                ChangeRequest.id == request_id,
                ChangeRequest.requester_id == user.id,
                ChangeRequest.origin == "internal",
            )
            .options(*OPTIONS)
        )
        if lock:
            statement = statement.with_for_update().execution_options(
                populate_existing=True
            )
        item = await self.db.scalar(statement)
        if item is None:
            raise HTTPException(404, "Solicitação não encontrada.")
        return item

    @staticmethod
    def ensure_editable(item: ChangeRequest) -> None:
        if item.task_id is not None:
            raise HTTPException(
                409,
                "Esta solicitação já gerou uma tarefa. Atualize a tarefa vinculada.",
            )
        if item.status not in {"ajuste", "recusado"}:
            raise HTTPException(
                409,
                "A solicitação só pode ser alterada após pedido de ajuste ou recusa.",
            )

    async def apply_edit(
        self, item: ChangeRequest, data: RequestEdit, user: User
    ) -> None:
        """Aplica campos do formulário e o delta de anexos na mesma transação."""
        project_name = data.project_name
        if data.project_kind == "existing":
            await self.access.require_project(user, data.project_id)
            project_name = await self.db.scalar(
                select(Project.name).where(Project.id == data.project_id)
            )

        existing = {attachment.id: attachment for attachment in item.attachments}
        removed = set(data.remove_attachment_ids)
        if not removed.issubset(existing):
            raise HTTPException(422, "Um dos anexos informados não pertence à solicitação.")
        if len(existing) - len(removed) + len(data.attachments) > 3:
            raise HTTPException(422, "Use no máximo três anexos.")

        values = data.model_dump(
            exclude={"version", "attachments", "remove_attachment_ids"}, mode="json"
        )
        values["project_name"] = project_name
        for field, value in values.items():
            setattr(item, field, value)
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
        self, request_id: int, data: RequestEdit, user: User
    ) -> RequestRead:
        async with KanbanService(self.db)._transaction():
            # Mantem a mesma ordem de locks da avaliacao: pedido, depois conta.
            item = await self.editable_item(request_id, user, lock=True)
            actor = await self.locked_actor(user)
            self.ensure_editable(item)
            if item.version != data.version:
                raise HTTPException(
                    409,
                    "A solicitação foi atualizada. Confira os dados antes de salvar novamente.",
                )
            old_value = {"request_id": item.id, "status": item.status}
            await self.apply_edit(item, data, actor)
            item.version += 1
            self.db.add(
                AdminAuditLog(
                    actor_id=actor.id,
                    subject_user_id=actor.id,
                    project_id=item.project_id,
                    action="request_edited",
                    old_value=old_value,
                    new_value={"request_id": item.id, "status": item.status},
                )
            )
            await self.db.flush()
            return await self.read(item, actor)

    async def resubmit(
        self, request_id: int, data: RequestResubmit, user: User
    ) -> RequestRead:
        async with KanbanService(self.db)._transaction():
            # Mantem a mesma ordem de locks da avaliacao: pedido, depois conta.
            item = await self.editable_item(request_id, user, lock=True)
            actor = await self.locked_actor(user)
            self.ensure_editable(item)
            if item.version != data.version:
                raise HTTPException(
                    409,
                    "A solicitação foi atualizada. Confira a avaliação antes de reenviar.",
                )
            old_status = item.status
            item.status = "em_avaliacao"
            item.version += 1
            self.db.add(
                AdminAuditLog(
                    actor_id=actor.id,
                    subject_user_id=actor.id,
                    project_id=item.project_id,
                    action="request_resubmitted",
                    old_value={"request_id": item.id, "status": old_status},
                    new_value={"request_id": item.id, "status": item.status},
                )
            )
            await self.db.flush()
            return await self.read(item, actor)

    async def approve_task(
        self, item: ChangeRequest, data: RequestReview, user: User
    ) -> None:
        target = data.project_id or item.project_id
        if target is None:
            raise HTTPException(
                422,
                "Selecione o projeto que receberá a tarefa. Cadastre-o em Projetos, se necessário.",
            )
        if item.project_id is not None and target != item.project_id:
            raise HTTPException(
                422, "O projeto da solicitação não pode ser alterado na aprovação."
            )
        await self.access.require_project(user, target, "manage")
        board = await self.db.scalar(
            select(Board)
            .where(Board.project_id == target)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if board is None or board.default_column_id is None:
            raise HTTPException(409, "O projeto ainda não possui quadro configurado.")
        project = await self.db.scalar(
            select(Project)
            .where(Project.id == target)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if item.task_id:
            task = await self.db.scalar(
                select(Task)
                .where(Task.id == item.task_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if task is None or task.board_id != board.id:
                raise HTTPException(
                    409,
                    "A tarefa vinculada precisa ser conferida antes da reaprovação.",
                )
            if task.assignee_id is None or task.due_date is None:
                raise HTTPException(
                    422,
                    "Defina responsável e prazo na tarefa vinculada antes de reaprovar.",
                )
            try:
                await self.access.eligible_assignee(task.assignee_id, target)
            except HTTPException as exc:
                raise HTTPException(
                    422,
                    "Atualize o responsável na tarefa vinculada antes de reaprovar.",
                ) from exc
            if (
                data.assignee_id is not None and data.assignee_id != task.assignee_id
            ) or (data.due_date is not None and data.due_date != task.due_date):
                raise HTTPException(
                    422,
                    "Altere responsável e prazo na tarefa vinculada; a reaprovação preserva os dados atuais.",
                )
            return
        if data.assignee_id is None or data.due_date is None:
            raise HTTPException(
                422, "Antes de aprovar, defina o responsável e o prazo da tarefa."
            )
        await self.access.eligible_assignee(data.assignee_id, target)
        column = await self.db.scalar(
            select(BoardColumn).where(
                BoardColumn.id == board.default_column_id,
                BoardColumn.board_id == board.id,
            )
        )
        if column is None or column.is_done:
            raise HTTPException(
                409, "Configure uma coluna inicial aberta para receber solicitações."
            )
        position = await self.db.scalar(
            select(func.coalesce(func.max(Task.position), -1) + 1).where(
                Task.column_id == column.id
            )
        )
        description = f"Solicitação #{item.id}\n\n## O que precisa\n{item.description}\n\n## Para que serve\n{item.purpose}"
        if item.location:
            description += f"\n\n## Tela ou relatório\n{item.location}"
        if item.example_url:
            description += f"\n\n## Exemplo\n{item.example_url}"
        if item.attachments:
            description += f"\n\nAnexos disponíveis na solicitação #{item.id}."
        task = Task(
            board_id=board.id,
            column_id=column.id,
            number=project.next_task_number,
            title=item.description.replace("\n", " ")[:300],
            description=description,
            priority={"travando": "high", "importante": "medium", "seria_bom": "low"}[
                item.urgency
            ],
            task_type="bug"
            if item.request_type == "correcao"
            else "improvement"
            if item.request_type == "melhoria"
            else "task",
            reporter_id=item.requester_id or user.id,
            assignee_id=data.assignee_id,
            due_date=data.due_date,
            position=position,
            version=1,
        )
        project.next_task_number += 1
        self.db.add(task)
        await self.db.flush()
        item.task_id, item.project_id = task.id, target
        self.db.add(
            TaskHistory(
                task_id=task.id,
                actor_id=user.id,
                event="created",
                old_value=None,
                new_value={"task_id": task.id, "request_id": item.id},
            )
        )

    async def review(
        self, request_id: int, data: RequestReview, user: User
    ) -> RequestRead:
        async with KanbanService(self.db)._transaction():
            # A solicitacao e o primeiro lock compartilhado entre avaliadores.
            # Trancar a conta antes dela permite ciclo com a FK do responsavel
            # quando dois avaliadores aprovam ao mesmo tempo.
            item = await self.item(request_id, user, lock=True)
            actor = await self.locked_actor(user)
            if not await self.can_review(item, actor):
                raise HTTPException(403, "Você não pode avaliar esta solicitação.")
            if item.version != data.version:
                raise HTTPException(
                    409,
                    "A solicitação foi atualizada. Confira a avaliação atual antes de salvar novamente.",
                )
            if data.project_id is not None and data.status != "aprovado":
                raise HTTPException(
                    422, "O projeto de destino só é informado na aprovação."
                )
            old_status = item.status
            if data.status == "aprovado":
                await self.approve_task(item, data, actor)
            item.status, item.response = data.status, data.response
            item.reviewer_id, item.reviewed_at = actor.id, datetime.now(timezone.utc)
            item.version += 1
            self.db.add(
                AdminAuditLog(
                    actor_id=actor.id,
                    subject_user_id=item.requester_id,
                    project_id=item.project_id,
                    action="request_reviewed",
                    old_value={"request_id": item.id, "status": old_status},
                    new_value={
                        "request_id": item.id,
                        "status": item.status,
                        "task_id": item.task_id,
                    },
                )
            )
            await self.db.flush()
            return await self.read(item, actor)

    async def attachment(
        self, request_id: int, attachment_id: int, user: User
    ) -> RequestAttachment:
        await self.item(request_id, user)
        attachment = await self.db.scalar(
            select(RequestAttachment)
            .where(
                RequestAttachment.id == attachment_id,
                RequestAttachment.request_id == request_id,
            )
            .options(undefer(RequestAttachment.content))
        )
        if attachment is None:
            raise HTTPException(404, "Anexo não encontrado.")
        return attachment
