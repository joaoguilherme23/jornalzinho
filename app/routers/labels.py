"""Rotas do catalogo de etiquetas."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.models import User
from app.schemas.kanban import Page
from app.schemas.labels import LabelCreate, LabelRead, LabelUpdate
from app.services.kanban import KanbanService

labels_router = APIRouter(tags=["labels"])


@labels_router.get("/projects/{project_id}/labels", response_model=Page[LabelRead])
async def list_labels(
    project_id: int,
    include_archived: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> Page[LabelRead]:
    labels = await KanbanService(session).list_labels(project_id, include_archived, current_user)
    return Page(items=[LabelRead.model_validate(item) for item in labels], total=len(labels), offset=0, limit=200)


@labels_router.post("/projects/{project_id}/labels", response_model=LabelRead, status_code=status.HTTP_201_CREATED)
async def create_label(
    project_id: int,
    data: LabelCreate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> LabelRead:
    return LabelRead.model_validate(await KanbanService(session).create_label(project_id, data.name, data.color, current_user))


@labels_router.patch("/labels/{label_id}", response_model=LabelRead)
async def update_label(
    label_id: int,
    data: LabelUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_ready_user),
) -> LabelRead:
    return LabelRead.model_validate(await KanbanService(session).update_label(label_id, data.model_dump(exclude_unset=True), current_user))
