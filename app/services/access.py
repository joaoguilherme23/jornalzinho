"""Verificacao central de escopo e papeis de projetos."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import ProjectMember
from app.models.project import Project
from app.models.user import User


PASSWORD_CHANGE_REQUIRED = {
    "code": "password_change_required",
    "message": "Troque a senha temporaria para continuar.",
}
RESOURCE_NOT_FOUND_DETAIL = "Recurso nao encontrado."


class AccessService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def require_ready(user: User) -> None:
        if user.must_change_password:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)

    @staticmethod
    def require_admin(user: User) -> None:
        AccessService.require_ready(user)
        if user.global_role != "admin":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso administrativo necessario.")

    async def visible_project_ids(self, user: User) -> list[int] | None:
        self.require_ready(user)
        if user.global_role == "admin":
            return None
        return list(
            await self.db.scalars(
                select(ProjectMember.project_id).where(ProjectMember.user_id == user.id).order_by(ProjectMember.project_id)
            )
        )

    async def require_project(self, user: User, project_id: int, action: str = "read") -> str:
        self.require_ready(user)
        if action not in {"read", "write", "manage"}:
            raise ValueError("acao de projeto invalida")
        project = await self.db.scalar(select(Project.id).where(Project.id == project_id))
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RESOURCE_NOT_FOUND_DETAIL)
        if user.global_role == "admin":
            return "admin"
        member = await self.db.scalar(
            select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        )
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=RESOURCE_NOT_FOUND_DETAIL)
        allowed = {
            "viewer": {"read"},
            "member": {"read", "write"},
            "manager": {"read", "write", "manage"},
        }
        if action not in allowed[member.role]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acao nao permitida neste projeto.")
        return member.role

    async def eligible_assignee(self, user_id: int, project_id: int) -> User:
        user = await self.db.scalar(
            select(User)
            .join(ProjectMember, ProjectMember.user_id == User.id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                ProjectMember.project_id == project_id,
                ProjectMember.role.in_(("manager", "member")),
            )
        )
        if user is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Responsavel nao elegivel.")
        return user
