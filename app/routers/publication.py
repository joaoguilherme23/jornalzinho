"""Rotas públicas e administrativas da publicação."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.models.user import User
from app.schemas.publication import (
    ColumnPublicationUpdate,
    NewsCreate,
    NewsUpdate,
    ProjectPublicationUpdate,
    PublicationColumnRead,
    PublicationNewsPage,
    PublicationNewsRead,
    PublicationProjectDetail,
    PublicationProjectPage,
    PublicationProjectRead,
    PublicNewsPage,
    PublicNewsRead,
    PublicProjectRead,
    PublicWorkPage,
    PublicWorkRead,
    PublicWorkStatus,
    TaskPublicationUpdate,
    PublicationTaskRead,
)
from app.services.publication import PublicationService


public_router = APIRouter(prefix="/public", tags=["public"])
publication_router = APIRouter(prefix="/publication", tags=["publication"])


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@public_router.get("/projects", response_model=dict[str, list[PublicProjectRead]])
async def list_public_projects(response: Response, session: AsyncSession = Depends(get_session)) -> dict[str, list[PublicProjectRead]]:
    no_store(response)
    return {"items": await PublicationService(session).public_projects()}


@public_router.get("/work", response_model=PublicWorkPage)
async def list_public_work(
    response: Response,
    project_id: int | None = Query(default=None, gt=0),
    status_value: PublicWorkStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, min_length=1, max_length=300),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PublicWorkPage:
    no_store(response)
    items, total = await PublicationService(session).public_work(
        project_id=project_id, work_status=status_value, q=q, offset=offset, limit=limit
    )
    return PublicWorkPage(items=items, total=total, offset=offset, limit=limit)


@public_router.get("/work/{code}", response_model=PublicWorkRead)
async def get_public_work(code: str, response: Response, session: AsyncSession = Depends(get_session)) -> PublicWorkRead:
    no_store(response)
    return await PublicationService(session).public_work_by_code(code)


@public_router.get("/news", response_model=PublicNewsPage)
async def list_public_news(
    response: Response,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> PublicNewsPage:
    no_store(response)
    items, total = await PublicationService(session).public_news(offset=offset, limit=limit)
    return PublicNewsPage(items=items, total=total, offset=offset, limit=limit)


@public_router.get("/news/{news_id}", response_model=PublicNewsRead)
async def get_public_news(news_id: int, response: Response, session: AsyncSession = Depends(get_session)) -> PublicNewsRead:
    no_store(response)
    return await PublicationService(session).public_news_by_id(news_id)


@publication_router.get("/projects", response_model=PublicationProjectPage)
async def list_publication_projects(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> PublicationProjectPage:
    items = await PublicationService(session).management_projects(current_user)
    return PublicationProjectPage(items=items[offset:offset + limit], total=len(items), offset=offset, limit=limit)


@publication_router.get("/projects/{project_id}", response_model=PublicationProjectDetail)
async def get_publication_project(
    project_id: int, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_ready_user)
) -> PublicationProjectDetail:
    return await PublicationService(session).management_project(project_id=project_id, user=current_user)


@publication_router.put("/projects/{project_id}", response_model=PublicationProjectRead)
async def update_publication_project(
    project_id: int, data: ProjectPublicationUpdate, session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> PublicationProjectRead:
    return await PublicationService(session).update_project(project_id=project_id, data=data, user=current_user)


@publication_router.put("/tasks/{task_id}", response_model=PublicationTaskRead)
async def update_publication_task(
    task_id: int, data: TaskPublicationUpdate, session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> PublicationTaskRead:
    return await PublicationService(session).update_task(task_id=task_id, data=data, user=current_user)


@publication_router.put("/columns/{column_id}", response_model=PublicationColumnRead)
async def update_publication_column(
    column_id: int, data: ColumnPublicationUpdate, session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> PublicationColumnRead:
    return await PublicationService(session).update_column(column_id=column_id, data=data, user=current_user)


@publication_router.get("/news", response_model=PublicationNewsPage)
async def list_publication_news(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session), current_user: User = Depends(get_ready_user),
) -> PublicationNewsPage:
    items, total = await PublicationService(session).management_news(user=current_user, offset=offset, limit=limit)
    return PublicationNewsPage(items=items, total=total, offset=offset, limit=limit)


@publication_router.post("/news", response_model=PublicationNewsRead, status_code=status.HTTP_201_CREATED)
async def create_publication_news(
    data: NewsCreate, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_ready_user)
) -> PublicationNewsRead:
    return await PublicationService(session).create_news(data=data, user=current_user)


@publication_router.put("/news/{news_id}", response_model=PublicationNewsRead)
async def update_publication_news(
    news_id: int, data: NewsUpdate, session: AsyncSession = Depends(get_session), current_user: User = Depends(get_ready_user)
) -> PublicationNewsRead:
    return await PublicationService(session).update_news(news_id=news_id, data=data, user=current_user)
