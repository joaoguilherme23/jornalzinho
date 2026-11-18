"""Regras transacionais do dominio Kanban."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Board, BoardColumn, Comment, IdempotencyRequest, Project, Task, TaskHistory, User
from app.models.label import Label
from app.services.access import AccessService, RESOURCE_NOT_FOUND_DETAIL
from app.schemas.kanban import (
    BoardColumnCreate,
    BoardColumnUpdate,
    BoardUpdate,
    CommentCreate,
    ProjectCreate,
    TaskCreate,
    TaskMove,
    TaskUpdate,
)


TASK_OPTIONS = (
    selectinload(Task.column),
    selectinload(Task.reporter),
    selectinload(Task.assignee),
    selectinload(Task.board).selectinload(Board.project),
    selectinload(Task.labels),
)

DEFAULT_BOARD_COLUMNS = (
    ("Backlog", False),
    ("To Do", False),
    ("In Progress", False),
    ("Review", False),
    ("Done", True),
)


async def create_default_board(session: AsyncSession, project: Project) -> Board:
    """Cria o board inicial e suas colunas dentro da transacao do chamador."""

    board = Board(project=project, name=project.name)
    columns = [
        BoardColumn(board=board, name=name, position=position, is_done=is_done)
        for position, (name, is_done) in enumerate(DEFAULT_BOARD_COLUMNS)
    ]
    session.add_all([board, *columns])
    await session.flush()
    board.default_column_id = columns[0].id
    await session.flush()
    return board


def not_found(detail: str = RESOURCE_NOT_FOUND_DETAIL) -> HTTPException:
    """Evita diferenciar recurso inexistente de recurso fora do escopo."""
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RESOURCE_NOT_FOUND_DETAIL)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def payload_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def json_value(value: object) -> object:
    if hasattr(value, "value"):
        return value.value  # type: ignore[union-attr]
    if hasattr(value, "isoformat"):
        return value.isoformat()  # type: ignore[union-attr]
    return value


class KanbanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @asynccontextmanager
    async def _transaction(self):
        """Fecha a transacao iniciada pela dependencia de autenticacao, se houver."""
        if not self.session.in_transaction():
            async with self.session.begin():
                yield
            return
        try:
            yield
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise

    async def _idempotency(
        self, user_id: int, operation: str, request_key: UUID, digest: str
    ) -> IdempotencyRequest | None:
        request = await self.session.scalar(
            select(IdempotencyRequest).where(
                IdempotencyRequest.user_id == user_id,
                IdempotencyRequest.operation == operation,
                IdempotencyRequest.request_key == request_key,
            )
        )
        if request is not None and request.payload_hash != digest:
            raise conflict("Idempotency-Key reutilizada com corpo diferente")
        return request

    def _record_idempotency(
        self, user_id: int, operation: str, request_key: UUID, digest: str, resource_type: str, resource_id: int
    ) -> None:
        self.session.add(
            IdempotencyRequest(
                user_id=user_id,
                operation=operation,
                request_key=request_key,
                payload_hash=digest,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )

    async def _active_assignee(self, user_id: int | None, project_id: int, current_id: int | None = None) -> User | None:
        if user_id is None:
            return None
        if current_id == user_id:
            return await self.session.get(User, user_id)
        user = await AccessService(self.session).eligible_assignee(user_id, project_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="responsavel ativo nao encontrado")
        return user

    async def _project_role(self, user: User, project_id: int, action: str = "read") -> str:
        return await AccessService(self.session).require_project(user, project_id, action)

    async def _board_role(self, user: User, board_id: int, action: str = "read") -> tuple[Board, str]:
        board = await self.session.scalar(select(Board).where(Board.id == board_id).options(selectinload(Board.project)))
        if board is None:
            raise not_found("board nao encontrado")
        return board, await self._project_role(user, board.project_id, action)

    async def _labels(self, project_id: int, ids: list[int], current_ids: set[int] | None = None) -> list[Label]:
        if not ids:
            return []
        labels = (await self.session.scalars(select(Label).where(Label.id.in_(ids)))).all()
        by_id = {label.id: label for label in labels}
        if len(by_id) != len(ids) or any(label.project_id != project_id for label in labels):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="etiqueta nao pertence ao projeto")
        current_ids = current_ids or set()
        if any(label.is_archived and label.id not in current_ids for label in labels):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="etiqueta arquivada nao pode ser aplicada")
        return [by_id[label_id] for label_id in ids]

    async def _task(self, task_id: int, *, lock: bool = False) -> Task:
        statement: Select[tuple[Task]] = select(Task).where(Task.id == task_id).options(*TASK_OPTIONS)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        task = await self.session.scalar(statement)
        if task is None:
            raise not_found("task nao encontrada")
        return task

    async def list_projects(self, user: User, offset: int, limit: int) -> tuple[Sequence[Project], int]:
        visible = await AccessService(self.session).visible_project_ids(user)
        filters = () if visible is None else (Project.id.in_(visible),)
        total = await self.session.scalar(select(func.count()).select_from(Project).where(*filters)) or 0
        projects = (await self.session.scalars(
            select(Project).where(*filters).options(selectinload(Project.board)).order_by(Project.key).offset(offset).limit(limit)
        )).all()
        return projects, total

    async def create_project(self, data: ProjectCreate, user: User, request_key: UUID) -> Project:
        AccessService.require_admin(user)
        body = data.model_dump(mode="json")
        digest = payload_hash(body)
        try:
            async with self._transaction():
                await self.session.scalar(select(User).where(User.id == user.id).with_for_update())
                existing = await self._idempotency(user.id, "create_project", request_key, digest)
                if existing is not None:
                    project = await self.session.scalar(
                        select(Project).where(Project.id == existing.resource_id).options(selectinload(Project.board))
                    )
                    if project is None:
                        raise conflict("requisicao idempotente referencia recurso ausente")
                    return project
                project = Project(**body)
                self.session.add(project)
                await create_default_board(self.session, project)
                self._record_idempotency(user.id, "create_project", request_key, digest, "project", project.id)
            return project
        except IntegrityError as error:
            raise conflict("chave ou identificador legado de projeto ja existe") from error

    async def board(self, board_id: int, tasks_offset: int, tasks_limit: int, user: User) -> tuple[Board, Sequence[Task], int, str]:
        board = await self.session.scalar(
            select(Board).where(Board.id == board_id).options(selectinload(Board.project), selectinload(Board.columns))
        )
        if board is None:
            raise not_found("board nao encontrado")
        role = await self._project_role(user, board.project_id)
        total = await self.session.scalar(select(func.count()).select_from(Task).where(Task.board_id == board_id)) or 0
        tasks = (await self.session.scalars(
            select(Task).where(Task.board_id == board_id).options(*TASK_OPTIONS)
            .order_by(Task.column_id, Task.position, Task.id).offset(tasks_offset).limit(tasks_limit)
        )).all()
        return board, tasks, total, role

    async def update_board(self, board_id: int, data: BoardUpdate, user: User) -> Board:
        await self._board_role(user, board_id, "manage")
        try:
            async with self._transaction():
                board = await self.session.scalar(
                    select(Board).where(Board.id == board_id).options(selectinload(Board.columns)).with_for_update()
                    .execution_options(populate_existing=True)
                )
                if board is None:
                    raise not_found("board nao encontrado")
                if "name" in data.model_fields_set:
                    board.name = data.name  # type: ignore[assignment]
                if "default_column_id" in data.model_fields_set:
                    column = next((item for item in board.columns if item.id == data.default_column_id), None)
                    if column is None:
                        raise conflict("coluna padrao deve pertencer ao board")
                    board.default_column_id = column.id
            return board
        except IntegrityError as error:
            raise conflict("nao foi possivel atualizar o board") from error

    async def create_column(self, board_id: int, data: BoardColumnCreate, user: User) -> BoardColumn:
        await self._board_role(user, board_id, "manage")
        try:
            async with self._transaction():
                board = await self.session.scalar(
                    select(Board).where(Board.id == board_id).with_for_update().execution_options(populate_existing=True)
                )
                if board is None:
                    raise not_found("board nao encontrado")
                position = await self.session.scalar(
                    select(func.coalesce(func.max(BoardColumn.position), -1) + 1).where(BoardColumn.board_id == board_id)
                )
                column = BoardColumn(board_id=board_id, name=data.name, is_done=data.is_done, position=position or 0)
                self.session.add(column)
            return column
        except IntegrityError as error:
            raise conflict("nome ou posicao da coluna ja existe neste board") from error

    async def update_column(self, column_id: int, data: BoardColumnUpdate, user: User) -> BoardColumn:
        probe = await self.session.scalar(select(BoardColumn).where(BoardColumn.id == column_id))
        if probe is None:
            raise not_found("coluna nao encontrada")
        await self._board_role(user, probe.board_id, "manage")
        try:
            async with self._transaction():
                board = await self.session.scalar(
                    select(Board).where(Board.id == probe.board_id).with_for_update().execution_options(populate_existing=True)
                )
                if board is None:
                    raise not_found("board nao encontrado")
                column = await self.session.scalar(
                    select(BoardColumn).where(BoardColumn.id == column_id).with_for_update().execution_options(populate_existing=True)
                )
                if column is None or column.board_id != board.id:
                    raise not_found("coluna nao encontrada")
                columns = (await self.session.scalars(
                    select(BoardColumn).where(BoardColumn.board_id == column.board_id).order_by(BoardColumn.position).with_for_update()
                    .execution_options(populate_existing=True)
                )).all()
                if "name" in data.model_fields_set:
                    column.name = data.name  # type: ignore[assignment]
                if "is_done" in data.model_fields_set:
                    if data.is_done != column.is_done:
                        occupied = await self.session.scalar(
                            select(Task.id).where(Task.column_id == column.id).limit(1)
                        )
                        if occupied is not None:
                            raise conflict("nao e permitido alterar conclusao de coluna com tasks")
                    column.is_done = data.is_done  # type: ignore[assignment]
                if "position" in data.model_fields_set:
                    columns.remove(column)
                    columns.insert(min(data.position or 0, len(columns)), column)
                    await self._renumber_columns(columns)
            return column
        except IntegrityError as error:
            raise conflict("nome ou posicao da coluna ja existe neste board") from error

    async def _renumber_columns(self, columns: Sequence[BoardColumn]) -> None:
        identifiers = [column.id for column in columns]
        temporary_start = max(column.position for column in columns) + len(columns) + 1
        for offset, column in enumerate(columns):
            await self.session.execute(
                update(BoardColumn).where(BoardColumn.id == column.id).values(position=temporary_start + offset)
            )
        for column in columns:
            await self.session.refresh(column)
        for index, column in enumerate(columns):
            await self.session.execute(
                update(BoardColumn).where(BoardColumn.id == column.id).values(position=index)
            )
            await self.session.refresh(column)

    async def delete_column(self, column_id: int, user: User) -> None:
        probe = await self.session.scalar(select(BoardColumn).where(BoardColumn.id == column_id))
        if probe is None:
            raise not_found("coluna nao encontrada")
        await self._board_role(user, probe.board_id, "manage")
        async with self._transaction():
            board = await self.session.scalar(
                select(Board).where(Board.id == probe.board_id).with_for_update().execution_options(populate_existing=True)
            )
            if board is None:
                raise not_found("board nao encontrado")
            column = await self.session.scalar(
                select(BoardColumn).where(BoardColumn.id == column_id).with_for_update().execution_options(populate_existing=True)
            )
            if column is None or column.board_id != board.id:
                raise not_found("coluna nao encontrada")
            if board.default_column_id == column.id:
                raise conflict("nao e permitido remover a coluna padrao")
            has_tasks = await self.session.scalar(select(Task.id).where(Task.column_id == column.id).limit(1))
            if has_tasks is not None:
                raise conflict("nao e permitido remover coluna com tasks")
            await self.session.delete(column)

    async def list_tasks(
        self, board_id: int | None, assignee_id: int | None, priority: str | None, q: str | None, label_ids: list[int], offset: int, limit: int, user: User
    ) -> tuple[Sequence[Task], int]:
        visible = await AccessService(self.session).visible_project_ids(user)
        statement = select(Task).join(Board, Task.board_id == Board.id).join(Project, Board.project_id == Project.id).options(*TASK_OPTIONS)
        count_statement = select(func.count()).select_from(Task).join(Board, Task.board_id == Board.id).join(Project, Board.project_id == Project.id)
        if visible is not None:
            statement = statement.where(Board.project_id.in_(visible))
            count_statement = count_statement.where(Board.project_id.in_(visible))
        if board_id is not None:
            await self._board_role(user, board_id)
        for condition in (
            Task.board_id == board_id if board_id is not None else None,
            Task.assignee_id == assignee_id if assignee_id is not None else None,
            Task.priority == priority if priority is not None else None,
            (or_(Task.title.ilike(f"%{q.strip()}%"), func.concat(Project.key, "-", Task.number).ilike(f"%{q.strip()}%"))) if q and q.strip() else None,
        ):
            if condition is not None:
                statement = statement.where(condition)
                count_statement = count_statement.where(condition)
        if label_ids:
            labels = await self._labels_for_filter(label_ids, visible)
            for label in labels:
                statement = statement.where(Task.labels.any(Label.id == label.id))
                count_statement = count_statement.where(Task.labels.any(Label.id == label.id))
        total = await self.session.scalar(count_statement) or 0
        tasks = (await self.session.scalars(
            statement.order_by(Task.updated_at.desc(), Task.id.desc()).offset(offset).limit(limit)
        )).all()
        return tasks, total

    async def _labels_for_filter(self, label_ids: list[int], visible: list[int] | None) -> list[Label]:
        labels = (await self.session.scalars(select(Label).where(Label.id.in_(label_ids)))).all()
        if len({item.id for item in labels}) != len(label_ids) or (visible is not None and any(item.project_id not in visible for item in labels)):
            raise not_found("etiqueta nao encontrada")
        return labels

    async def create_task(self, data: TaskCreate, user: User, request_key: UUID) -> Task:
        body = data.model_dump(mode="json", by_alias=True)
        if not body.get("label_ids"):
            body.pop("label_ids", None)
        digest = payload_hash(body)
        try:
            async with self._transaction():
                board_for_access, _ = await self._board_role(user, data.board_id, "write")
                await self.session.scalar(select(User).where(User.id == user.id).with_for_update())
                existing = await self._idempotency(user.id, "create_task", request_key, digest)
                if existing is not None:
                    task = await self._task(existing.resource_id)
                    return task
                board = await self.session.scalar(
                    select(Board).where(Board.id == data.board_id).options(selectinload(Board.project)).with_for_update()
                    .execution_options(populate_existing=True)
                )
                if board is None:
                    raise not_found("board nao encontrado")
                if board.default_column_id is None:
                    raise conflict("board nao possui coluna padrao")
                column = await self.session.scalar(
                    select(BoardColumn).where(BoardColumn.id == board.default_column_id, BoardColumn.board_id == board.id)
                    .execution_options(populate_existing=True)
                )
                if column is None:
                    raise conflict("coluna padrao invalida")
                project = await self.session.scalar(
                    select(Project).where(Project.id == board.project_id).with_for_update().execution_options(populate_existing=True)
                )
                if project is None:
                    raise conflict("projeto do board nao encontrado")
                assignee = await self._active_assignee(data.assignee_id, board.project_id)
                labels = await self._labels(board.project_id, data.label_ids)
                position = await self.session.scalar(
                    select(func.coalesce(func.max(Task.position), -1) + 1).where(Task.column_id == column.id)
                )
                task = Task(
                    board_id=board.id, column_id=column.id, number=project.next_task_number,
                    title=data.title, description=data.description, priority=data.priority,
                    task_type=data.task_type, reporter_id=user.id, assignee=assignee,
                    due_date=data.due_date, position=position or 0, labels=labels,
                )
                project.next_task_number += 1
                self.session.add(task)
                await self.session.flush()
                self._history(task.id, user.id, "created", None, {"task_id": task.id})
                self._record_idempotency(user.id, "create_task", request_key, digest, "task", task.id)
                await self.session.flush()
                task = await self._task(task.id)
            return task
        except IntegrityError as error:
            raise conflict("nao foi possivel criar a task") from error

    def _history(self, task_id: int, actor_id: int, event: str, old: dict[str, object] | None, new: dict[str, object] | None) -> None:
        self.session.add(TaskHistory(task_id=task_id, actor_id=actor_id, event=event, old_value=old, new_value=new))

    async def update_task(self, task_id: int, data: TaskUpdate, user: User) -> Task:
        task_probe = await self._task(task_id)
        await self._project_role(user, task_probe.board.project_id, "write")
        async with self._transaction():
            task = await self._task(task_id, lock=True)
            if task.version != data.version:
                raise conflict("versao da task esta desatualizada")
            previous: dict[str, object] = {}
            changes: dict[str, object] = {}
            if "assignee_id" in data.model_fields_set:
                assignee = await self._active_assignee(data.assignee_id, task.board.project_id, task.assignee_id)
                if task.assignee_id != data.assignee_id:
                    previous["assignee_id"] = task.assignee_id
                    changes["assignee_id"] = data.assignee_id
                    task.assignee = assignee
            if "label_ids" in data.model_fields_set:
                labels = await self._labels(task.board.project_id, data.label_ids or [], {item.id for item in task.labels})
                if {item.id for item in labels} != {item.id for item in task.labels}:
                    previous["label_ids"] = sorted(item.id for item in task.labels)
                    changes["label_ids"] = sorted(item.id for item in labels)
                    task.labels = labels
                    task.version += 1
            fields = (("title", data.title), ("description", data.description), ("priority", data.priority), ("task_type", data.task_type), ("due_date", data.due_date))
            for field, value in fields:
                if field in data.model_fields_set and getattr(task, field) != value:
                    output_name = "type" if field == "task_type" else field
                    previous_value = getattr(task, field)
                    previous[output_name] = json_value(previous_value)
                    changes[output_name] = json_value(value)
                    setattr(task, field, value)
            if changes:
                self._history(task.id, user.id, "updated", previous, changes)
            await self.session.flush()
            task = await self._task(task.id)
        return task

    async def move_task(self, task_id: int, data: TaskMove, user: User) -> Task:
        task_probe = await self._task(task_id)
        await self._project_role(user, task_probe.board.project_id, "write")
        async with self._transaction():
            board = await self.session.scalar(
                select(Board).where(Board.id == task_probe.board_id).with_for_update().execution_options(populate_existing=True)
            )
            if board is None:
                raise not_found("board nao encontrado")
            task = await self._task(task_id, lock=True)
            if task.version != data.version:
                raise conflict("versao da task esta desatualizada")
            destination = await self.session.scalar(
                select(BoardColumn).where(BoardColumn.id == data.column_id, BoardColumn.board_id == board.id)
            )
            if destination is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="coluna nao pertence ao board")
            source_id = task.column_id
            column_ids = sorted({source_id, destination.id})
            locked_by_column = {
                column_id: (await self.session.scalars(
                    select(Task).where(Task.column_id == column_id).order_by(Task.position, Task.id).with_for_update()
                )).all()
                for column_id in column_ids
            }
            source_tasks = locked_by_column[source_id]
            destination_tasks = source_tasks if source_id == destination.id else locked_by_column[destination.id]
            source_tasks.remove(task)
            if destination_tasks is not source_tasks:
                task.column_id = destination.id
            destination_tasks.insert(min(data.position, len(destination_tasks)), task)
            for index, item in enumerate(source_tasks):
                item.position = index
            for index, item in enumerate(destination_tasks):
                item.position = index
            if destination.is_done and source_id != destination.id:
                task.completed_at = datetime.now(timezone.utc)
            elif not destination.is_done and source_id != destination.id:
                task.completed_at = None
            self._history(task.id, user.id, "moved", {"column_id": source_id}, {"column_id": destination.id, "position": task.position})
            await self.session.flush()
            task = await self._task(task.id)
        return task

    async def create_comment(self, task_id: int, data: CommentCreate, user: User, request_key: UUID) -> Comment:
        task_probe = await self._task(task_id)
        await self._project_role(user, task_probe.board.project_id, "write")
        body = {"task_id": task_id, **data.model_dump(mode="json")}
        digest = payload_hash(body)
        legacy_digest = payload_hash(data.model_dump(mode="json"))
        try:
            async with self._transaction():
                await self.session.scalar(select(User).where(User.id == user.id).with_for_update())
                existing = await self.session.scalar(
                    select(IdempotencyRequest).where(
                        IdempotencyRequest.user_id == user.id,
                        IdempotencyRequest.operation == "create_comment",
                        IdempotencyRequest.request_key == request_key,
                    )
                )
                if existing is not None and existing.payload_hash not in (digest, legacy_digest):
                    raise conflict("Idempotency-Key reutilizada com corpo diferente")
                if existing is not None:
                    comment = await self.session.scalar(
                        select(Comment).where(Comment.id == existing.resource_id).options(selectinload(Comment.author))
                    )
                    if comment is None:
                        raise conflict("requisicao idempotente referencia recurso ausente")
                    if comment.task_id != task_id:
                        raise conflict("Idempotency-Key reutilizada para outra task")
                    return comment
                task = await self._task(task_id, lock=True)
                comment = Comment(task_id=task.id, author_id=user.id, body=data.body)
                self.session.add(comment)
                await self.session.flush()
                self._history(task.id, user.id, "comment_added", None, {"comment_id": comment.id})
                self._record_idempotency(user.id, "create_comment", request_key, digest, "comment", comment.id)
                await self.session.flush()
                comment = await self.session.scalar(select(Comment).where(Comment.id == comment.id).options(selectinload(Comment.author)))
            if comment is None:
                raise conflict("comentario nao foi persistido")
            return comment
        except IntegrityError as error:
            raise conflict("nao foi possivel criar o comentario") from error

    async def comments(self, task_id: int, offset: int, limit: int, user: User) -> tuple[Sequence[Comment], int]:
        task = await self._task(task_id)
        await self._project_role(user, task.board.project_id)
        total = await self.session.scalar(select(func.count()).select_from(Comment).where(Comment.task_id == task_id)) or 0
        comments = (await self.session.scalars(
            select(Comment).where(Comment.task_id == task_id).options(selectinload(Comment.author))
            .order_by(Comment.created_at, Comment.id).offset(offset).limit(limit)
        )).all()
        return comments, total

    async def history(self, task_id: int, offset: int, limit: int, user: User) -> tuple[Sequence[TaskHistory], int]:
        task = await self._task(task_id)
        await self._project_role(user, task.board.project_id)
        total = await self.session.scalar(select(func.count()).select_from(TaskHistory).where(TaskHistory.task_id == task_id)) or 0
        history = (await self.session.scalars(
            select(TaskHistory).where(TaskHistory.task_id == task_id).options(selectinload(TaskHistory.actor))
            .order_by(TaskHistory.created_at, TaskHistory.id).offset(offset).limit(limit)
        )).all()
        return history, total

    async def task_by_code(self, code: str, user: User) -> Task:
        key, separator, number = code.upper().rpartition("-")
        if not separator or not key or not number.isdigit() or len(number) > 10 or int(number) < 1 or int(number) > 2_147_483_647:
            raise not_found("task nao encontrada")
        task = await self.session.scalar(
            select(Task).join(Board).join(Project).where(Project.key == key, Task.number == int(number)).options(*TASK_OPTIONS)
        )
        if task is None:
            raise not_found("task nao encontrada")
        await self._project_role(user, task.board.project_id)
        return task

    async def list_labels(self, project_id: int, include_archived: bool, user: User) -> list[Label]:
        await self._project_role(user, project_id)
        statement = select(Label).where(Label.project_id == project_id)
        if not include_archived:
            statement = statement.where(Label.is_archived.is_(False))
        return list((await self.session.scalars(statement.order_by(Label.name, Label.id))).all())

    async def create_label(self, project_id: int, name: str, color: str, user: User) -> Label:
        await self._project_role(user, project_id, "manage")
        label = Label(project_id=project_id, name=name, normalized_name=name.casefold().strip(), color=color)
        try:
            async with self._transaction():
                self.session.add(label)
                await self.session.flush()
            return label
        except IntegrityError as error:
            raise conflict("nome de etiqueta ja existe neste projeto") from error

    async def update_label(self, label_id: int, values: dict[str, object], user: User) -> Label:
        label = await self.session.get(Label, label_id)
        if label is None:
            raise not_found("etiqueta nao encontrada")
        await self._project_role(user, label.project_id, "manage")
        try:
            async with self._transaction():
                label = await self.session.scalar(select(Label).where(Label.id == label_id).with_for_update())
                if label is None:
                    raise not_found("etiqueta nao encontrada")
                if "name" in values:
                    label.name = str(values["name"])
                    label.normalized_name = label.name.casefold().strip()
                if "color" in values:
                    label.color = str(values["color"])
                if "is_archived" in values:
                    label.is_archived = bool(values["is_archived"])
            return label
        except IntegrityError as error:
            raise conflict("nome de etiqueta ja existe neste projeto") from error
