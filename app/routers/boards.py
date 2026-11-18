"""Rotas de boards e colunas."""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.services.access import AccessService
from app.models import Board, BoardColumn, User
from app.routers.tasks import task_read
from app.schemas.kanban import BoardColumnCreate, BoardColumnRead, BoardColumnUpdate, BoardRead, BoardUpdate, ProjectSummary
from app.services.kanban import KanbanService

boards_router = APIRouter(prefix="/boards", tags=["boards"])
columns_router = APIRouter(prefix="/columns", tags=["columns"])


def column_read(column: BoardColumn) -> BoardColumnRead:
    return BoardColumnRead.model_validate(column)


@boards_router.get("/{board_id}", response_model=BoardRead)
async def get_board(
    board_id: int,
    tasks_offset: int = Query(default=0, ge=0),
    tasks_limit: int = Query(default=200, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> BoardRead:
    board, tasks, total, role = await KanbanService(session).board(board_id, tasks_offset, tasks_limit, current_user)
    return BoardRead(
        id=board.id,
        name=board.name,
        project=ProjectSummary.model_validate(board.project),
        role=role,
        default_column_id=board.default_column_id,
        columns=[column_read(column) for column in board.columns],
        tasks=[task_read(task, role) for task in tasks],
        tasks_total=total,
        tasks_offset=tasks_offset,
        tasks_limit=tasks_limit,
    )


@boards_router.patch("/{board_id}", response_model=BoardRead)
async def update_board(
    board_id: int,
    data: BoardUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> BoardRead:
    board = await KanbanService(session).update_board(board_id, data, current_user)
    board, tasks, total, role = await KanbanService(session).board(board.id, 0, 200, current_user)
    return BoardRead(
        id=board.id, name=board.name, project=ProjectSummary.model_validate(board.project), role=role, default_column_id=board.default_column_id,
        columns=[column_read(column) for column in board.columns], tasks=[task_read(task, role) for task in tasks],
        tasks_total=total, tasks_offset=0, tasks_limit=200,
    )


@boards_router.post("/{board_id}/columns", response_model=BoardColumnRead, status_code=status.HTTP_201_CREATED)
async def create_column(
    board_id: int,
    data: BoardColumnCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> BoardColumnRead:
    return column_read(await KanbanService(session).create_column(board_id, data, current_user))


@columns_router.patch("/{column_id}", response_model=BoardColumnRead)
async def update_column(
    column_id: int,
    data: BoardColumnUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> BoardColumnRead:
    return column_read(await KanbanService(session).update_column(column_id, data, current_user))


@columns_router.delete("/{column_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_column(
    column_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Response:
    await KanbanService(session).delete_column(column_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
