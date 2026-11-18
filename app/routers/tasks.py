"""Rotas de tasks, comentarios e historico."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.models import Comment, Task, TaskHistory, User
from app.schemas.labels import LabelRead
from app.schemas.kanban import (
    ColumnSummary, CommentCreate, CommentRead, Page, TaskCreate, TaskHistoryRead, TaskMove, TaskPriority,
    TaskRead, TaskUpdate, UserRead,
)
from app.services.kanban import KanbanService
from app.services.access import AccessService

tasks_router = APIRouter(prefix="/tasks", tags=["tasks"])


def user_read(user: User) -> UserRead:
    return UserRead.model_validate(user)


def task_read(task: Task, role: str = "admin") -> TaskRead:
    return TaskRead(
        id=task.id,
        code=f"{task.board.project.key}-{task.number}",
        board_id=task.board_id,
        project_id=task.board.project_id,
        role=role,
        title=task.title,
        description=task.description,
        column_id=task.column_id,
        column=ColumnSummary.model_validate(task.column),
        priority=task.priority,
        task_type=task.task_type,
        reporter=user_read(task.reporter),
        assignee=user_read(task.assignee) if task.assignee is not None else None,
        due_date=task.due_date,
        position=task.position,
        version=task.version,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
        archived_at=task.archived_at,
        labels=[LabelRead.model_validate(label) for label in task.labels],
    )


async def authorized_task_read(session: AsyncSession, task: Task, user: User) -> TaskRead:
    role = await AccessService(session).require_project(user, task.board.project_id)
    return task_read(task, role)


def comment_read(comment: Comment) -> CommentRead:
    return CommentRead(
        id=comment.id, task_id=comment.task_id, author=user_read(comment.author), body=comment.body,
        created_at=comment.created_at, updated_at=comment.updated_at,
    )


def history_read(item: TaskHistory) -> TaskHistoryRead:
    return TaskHistoryRead(
        id=item.id, event=item.event, actor=user_read(item.actor), old_value=item.old_value,
        new_value=item.new_value, created_at=item.created_at,
    )


@tasks_router.get("", response_model=Page[TaskRead])
async def list_tasks(
    board_id: int | None = Query(default=None, gt=0),
    assignee_id: int | None = Query(default=None, gt=0),
    priority: TaskPriority | None = None,
    q: str | None = Query(default=None, max_length=300),
    label_ids: list[int] = Query(default=[]),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Page[TaskRead]:
    tasks, total = await KanbanService(session).list_tasks(board_id, assignee_id, priority, q, label_ids, offset, limit, current_user)
    return Page(items=[await authorized_task_read(session, task, current_user) for task in tasks], total=total, offset=offset, limit=limit)


@tasks_router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> TaskRead:
    return await authorized_task_read(session, await KanbanService(session).create_task(data, current_user, idempotency_key), current_user)


@tasks_router.get("/by-code/{code}", response_model=TaskRead)
async def get_task_by_code(code: str, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_ready_user)) -> TaskRead:
    service = KanbanService(session)
    task = await service.task_by_code(code, current_user)
    return task_read(task, await AccessService(session).require_project(current_user, task.board.project_id))


@tasks_router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> TaskRead:
    task = await KanbanService(session)._task(task_id)
    role = await AccessService(session).require_project(current_user, task.board.project_id)
    return task_read(task, role)


@tasks_router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> TaskRead:
    return await authorized_task_read(session, await KanbanService(session).update_task(task_id, data, current_user), current_user)


@tasks_router.patch("/{task_id}/move", response_model=TaskRead)
async def move_task(
    task_id: int,
    data: TaskMove,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> TaskRead:
    return await authorized_task_read(session, await KanbanService(session).move_task(task_id, data, current_user), current_user)


@tasks_router.get("/{task_id}/comments", response_model=Page[CommentRead])
async def list_comments(
    task_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Page[CommentRead]:
    comments, total = await KanbanService(session).comments(task_id, offset, limit, current_user)
    return Page(items=[comment_read(comment) for comment in comments], total=total, offset=offset, limit=limit)


@tasks_router.post("/{task_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED)
async def create_comment(
    task_id: int,
    data: CommentCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> CommentRead:
    return comment_read(await KanbanService(session).create_comment(task_id, data, current_user, idempotency_key))


@tasks_router.get("/{task_id}/history", response_model=Page[TaskHistoryRead])
async def list_history(
    task_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Page[TaskHistoryRead]:
    history, total = await KanbanService(session).history(task_id, offset, limit, current_user)
    return Page(items=[history_read(item) for item in history], total=total, offset=offset, limit=limit)
