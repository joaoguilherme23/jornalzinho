"""API de equipe por projeto."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.models.user import User
from app.schemas.auth import MemberUpsert, ProjectMemberPublic, ProjectParticipant
from app.schemas.kanban import Page
from app.services.access import AccessService
from app.services.users import MemberService


router = APIRouter(prefix="/api/v1/projects", tags=["equipe"])


@router.get("/{project_id}/members", response_model=Page[ProjectMemberPublic])
async def list_members(project_id: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), current_user: User = Depends(get_ready_user), db: AsyncSession = Depends(get_session)) -> Page[ProjectMemberPublic]:
    await AccessService(db).require_project(current_user, project_id, "read")
    rows, total = await MemberService(db).list_members(project_id, offset, limit)
    return Page(items=[ProjectMemberPublic(user=ProjectParticipant.model_validate(user), role=member.role) for member, user in rows], total=total, offset=offset, limit=limit)


@router.get("/{project_id}/assignees", response_model=Page[ProjectParticipant])
async def list_assignees(project_id: int, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), current_user: User = Depends(get_ready_user), db: AsyncSession = Depends(get_session)) -> Page[ProjectParticipant]:
    await AccessService(db).require_project(current_user, project_id, "read")
    users, total = await MemberService(db).assignees(project_id, offset, limit)
    return Page(items=[ProjectParticipant.model_validate(user) for user in users], total=total, offset=offset, limit=limit)


@router.put("/{project_id}/members", response_model=ProjectMemberPublic)
async def upsert_member(project_id: int, body: MemberUpsert, current_user: User = Depends(get_ready_user), db: AsyncSession = Depends(get_session)) -> ProjectMemberPublic:
    role = await AccessService(db).require_project(current_user, project_id, "manage")
    member = await MemberService(db).upsert(actor=current_user, project_id=project_id, email=body.email, role=body.role, actor_role=role)
    user = await db.get(User, member.user_id)
    assert user is not None
    return ProjectMemberPublic(user=ProjectParticipant.model_validate(user), role=member.role)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(project_id: int, user_id: int, current_user: User = Depends(get_ready_user), db: AsyncSession = Depends(get_session)) -> None:
    role = await AccessService(db).require_project(current_user, project_id, "manage")
    await MemberService(db).remove(actor=current_user, project_id=project_id, user_id=user_id, actor_role=role)
