"""Usuarios disponiveis como responsaveis nas tasks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_admin_user
from app.models.user import User
from app.schemas.auth import (
    MembershipBulkRequest,
    MembershipBulkResult,
    PasswordReset,
    UserCreate,
    UserListResponse,
    UserMembershipPublic,
    UserPublic,
    UserUpdate,
)
from app.schemas.kanban import Page
from app.services.users import MemberService, UserService


router = APIRouter(prefix="/api/v1/users", tags=["usuarios"])


@router.get("", response_model=UserListResponse)
async def list_users(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    include_inactive: bool = Query(default=False),
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(default=None, min_length=1, max_length=200),
) -> UserListResponse:
    criteria = list(() if include_inactive else (User.is_active.is_(True),))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        criteria.append((User.name.ilike(pattern)) | (User.email.ilike(pattern)))
    total = await db.scalar(select(func.count()).select_from(User).where(*criteria))
    users = (
        await db.scalars(
            select(User).where(*criteria).order_by(User.name.asc(), User.id.asc()).offset(offset).limit(limit)
        )
    ).all()
    return UserListResponse(
        items=[UserPublic.model_validate(user) for user in users],
        total=total or 0,
        offset=offset,
        limit=limit,
    )


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    actor: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> UserPublic:
    try:
        user = await UserService(db).create(
            actor=actor,
            name=body.name,
            email=body.email,
            password=body.password,
            global_role=body.global_role,
            project_access=body.project_access,
        )
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado.") from error
    return UserPublic.model_validate(user)


@router.post("/{user_id}/memberships/bulk", response_model=MembershipBulkResult)
async def bulk_memberships(
    user_id: int,
    body: MembershipBulkRequest,
    actor: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> MembershipBulkResult:
    result = await UserService(db).bulk_memberships(
        actor=actor,
        user_id=user_id,
        action=body.action,
        scope=body.scope,
        project_ids=body.project_ids,
        role=body.role,
    )
    return MembershipBulkResult(**result)


@router.patch("/{user_id}", response_model=UserPublic)
async def update_user(
    user_id: int,
    body: UserUpdate,
    actor: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> UserPublic:
    try:
        user = await UserService(db).update(actor=actor, user_id=user_id, values=body.model_dump(exclude_unset=True))
    except IntegrityError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email ja cadastrado.") from error
    return UserPublic.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=UserPublic)
async def reset_password(
    user_id: int,
    body: PasswordReset,
    actor: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> UserPublic:
    user = await UserService(db).reset_password(actor=actor, user_id=user_id, password=body.password)
    return UserPublic.model_validate(user)


@router.get("/{user_id}/memberships", response_model=Page[UserMembershipPublic])
async def list_memberships(
    user_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_session),
) -> Page[UserMembershipPublic]:
    rows, total = await MemberService(db).memberships_for_user(user_id, offset, limit)
    return Page(
        items=[UserMembershipPublic(project_id=project.id, project_key=project.key, project_name=project.name, role=member.role) for member, project in rows],
        total=total, offset=offset, limit=limit,
    )
