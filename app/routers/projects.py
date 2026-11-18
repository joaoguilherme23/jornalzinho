"""Rotas de projetos."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.services.access import AccessService
from app.models import Project, User
from app.schemas.kanban import Page, ProjectCreate, ProjectRead
from app.services.kanban import KanbanService

projects_router = APIRouter(prefix="/projects", tags=["projects"])


def project_read(project: Project, role: str) -> ProjectRead:
    return ProjectRead(
        id=project.id,
        key=project.key,
        name=project.name,
        description=project.description,
        legacy_app_id=project.legacy_app_id,
        default_board_id=project.board.id if project.board is not None else None,
        role=role,
    )


@projects_router.get("", response_model=Page[ProjectRead])
async def list_projects(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Page[ProjectRead]:
    projects, total = await KanbanService(session).list_projects(current_user, offset, limit)
    access = AccessService(session)
    return Page(items=[project_read(project, await access.require_project(current_user, project.id)) for project in projects], total=total, offset=offset, limit=limit)


@projects_router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    data: ProjectCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> ProjectRead:
    project = await KanbanService(session).create_project(data, current_user, idempotency_key)
    return project_read(project, "admin")
