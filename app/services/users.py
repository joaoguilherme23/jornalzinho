"""Administracao de contas e trilha de auditoria."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AdminAuditLog
from app.models.membership import ProjectMember
from app.models.project import Project
from app.models.user import Session, User
from app.schemas.auth import ProjectAccess, normalizar_email
from app.services.auth import AuthService, utc_now


LAST_ADMIN_LOCK = 2026092301


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
        if not self.db.in_transaction():
            async with self.db.begin():
                yield
            return
        try:
            yield
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    def _audit(
        self,
        *,
        actor_id: int | None,
        action: str,
        source: str = "api",
        subject_user_id: int | None = None,
        project_id: int | None = None,
        old_value: dict[str, object] | None = None,
        new_value: dict[str, object] | None = None,
    ) -> None:
        self.db.add(
            AdminAuditLog(
                actor_id=actor_id,
                action=action,
                source=source,
                subject_user_id=subject_user_id,
                project_id=project_id,
                old_value=old_value,
                new_value=new_value,
            )
        )

    async def _admin_change_lock(self) -> None:
        # Serializa rebaixamento/desativacao entre transacoes concorrentes no PostgreSQL.
        await self.db.execute(select(func.pg_advisory_xact_lock(LAST_ADMIN_LOCK)))

    async def _ensure_not_last_admin(self, user: User, *, remains_active_admin: bool) -> None:
        if user.global_role != "admin" or not user.is_active or remains_active_admin:
            return
        await self._admin_change_lock()
        active_admins = await self.db.scalar(
            select(func.count()).select_from(User).where(User.global_role == "admin", User.is_active.is_(True))
        ) or 0
        if active_admins <= 1:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nao e permitido remover o ultimo administrador ativo.")

    async def _project_ids_for_scope(self, *, scope: str, project_ids: list[int] | None) -> list[int]:
        """Resolve o snapshot de projetos e valida a selecao antes dos vinculos."""
        if scope == "all":
            if project_ids is not None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selecao de projetos invalida.")
            return list(
                (await self.db.scalars(select(Project.id).order_by(Project.id))).all()
            )
        if scope != "selected" or not project_ids or any(project_id < 1 for project_id in project_ids):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selecao de projetos invalida.")
        if len(project_ids) != len(set(project_ids)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selecao de projetos invalida.")
        existing_ids = list(
            (await self.db.scalars(
                select(Project.id).where(Project.id.in_(project_ids)).order_by(Project.id)
            )).all()
        )
        if len(existing_ids) != len(project_ids):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Projeto nao encontrado.")
        return existing_ids

    async def _locked_memberships(self, *, user_id: int, project_ids: list[int]) -> dict[int, ProjectMember]:
        if not project_ids:
            return {}
        members = list(
            (await self.db.scalars(
                select(ProjectMember)
                .where(ProjectMember.user_id == user_id, ProjectMember.project_id.in_(project_ids))
                .order_by(ProjectMember.project_id)
                .with_for_update()
            )).all()
        )
        return {member.project_id: member for member in members}

    async def _add_missing_memberships(
        self, *, actor: User, user: User, project_ids: list[int], role: str
    ) -> tuple[int, int]:
        existing = await self._locked_memberships(user_id=user.id, project_ids=project_ids)
        for project_id in project_ids:
            if project_id in existing:
                continue
            self.db.add(ProjectMember(project_id=project_id, user_id=user.id, role=role))
            self._audit(
                actor_id=actor.id,
                action="project_member_added",
                subject_user_id=user.id,
                project_id=project_id,
                new_value={"role": role},
            )
        added = len(project_ids) - len(existing)
        return added, len(existing)

    async def create(
        self,
        *,
        actor: User,
        name: str,
        email: str,
        password: str,
        global_role: str = "user",
        project_access: ProjectAccess | None = None,
    ) -> User:
        async with self._transaction():
            project_ids = await self._project_ids_for_scope(
                scope=project_access.scope, project_ids=project_access.project_ids
            ) if project_access is not None else []
            user = await AuthService(self.db).create_user(name=name, email=email, password=password)
            user.global_role = global_role
            user.must_change_password = True
            self._audit(
                actor_id=actor.id,
                action="user_created",
                subject_user_id=user.id,
                new_value={"email": user.email, "global_role": user.global_role, "is_active": user.is_active},
            )
            if project_access is not None:
                await self._add_missing_memberships(
                    actor=actor, user=user, project_ids=project_ids, role=project_access.role
                )
            await self.db.flush()
        return user

    async def bulk_memberships(
        self,
        *,
        actor: User,
        user_id: int,
        action: str,
        scope: str,
        project_ids: list[int] | None,
        role: str | None = None,
    ) -> dict[str, int]:
        async with self._transaction():
            user = await self.db.scalar(
                select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
            )
            if user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado.")
            selected_project_ids = await self._project_ids_for_scope(scope=scope, project_ids=project_ids)
            if action == "add":
                if not user.is_active:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario indisponivel.")
                added, unchanged = await self._add_missing_memberships(
                    actor=actor,
                    user=user,
                    project_ids=selected_project_ids,
                    role="member" if role is None else role,
                )
                await self.db.flush()
                return {"added": added, "removed": 0, "unchanged": unchanged}
            if action != "remove" or role is not None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Operacao de vinculos invalida.")
            existing = await self._locked_memberships(user_id=user.id, project_ids=selected_project_ids)
            for project_id, member in existing.items():
                old = {"role": member.role}
                await self.db.delete(member)
                self._audit(
                    actor_id=actor.id,
                    action="project_member_removed",
                    subject_user_id=user.id,
                    project_id=project_id,
                    old_value=old,
                )
            removed = len(existing)
            await self.db.flush()
            return {"added": 0, "removed": removed, "unchanged": len(selected_project_ids) - removed}

    async def update(self, *, actor: User, user_id: int, values: dict[str, object]) -> User:
        async with self._transaction():
            user = await self.db.scalar(
                select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
            )
            if user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado.")
            old = {field: getattr(user, field) for field in ("name", "email", "is_active", "global_role")}
            future_active = bool(values.get("is_active", user.is_active))
            future_role = str(values.get("global_role", user.global_role))
            await self._ensure_not_last_admin(user, remains_active_admin=future_active and future_role == "admin")
            if "name" in values:
                cleaned = str(values["name"]).strip()
                if not cleaned:
                    raise ValueError("nome nao pode ser vazio")
                user.name = cleaned
            if "email" in values:
                user.email = normalizar_email(str(values["email"]))
            if "is_active" in values:
                user.is_active = future_active
                if not future_active:
                    await self.db.execute(
                        update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None)).values(revoked_at=utc_now())
                    )
            if "global_role" in values:
                user.global_role = future_role
            new = {field: getattr(user, field) for field in old}
            if old != new:
                self._audit(actor_id=actor.id, action="user_updated", subject_user_id=user.id, old_value=old, new_value=new)
            await self.db.flush()
        return user

    async def reset_password(self, *, actor: User, user_id: int, password: str) -> User:
        async with self._transaction():
            user = await self.db.scalar(
                select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
            )
            if user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario nao encontrado.")
            from app.services.auth import hash_password
            user.password_hash = await hash_password(password)
            user.must_change_password = True
            await self.db.execute(
                update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None)).values(revoked_at=utc_now())
            )
            self._audit(actor_id=actor.id, action="password_reset", subject_user_id=user.id)
            await self.db.flush()
        return user


class MemberService(UserService):
    """Mudancas de membros por projeto, auditadas e sem elevacao lateral."""

    async def list_members(self, project_id: int, offset: int, limit: int) -> tuple[list[tuple[ProjectMember, User]], int]:
        total = await self.db.scalar(
            select(func.count()).select_from(ProjectMember).where(ProjectMember.project_id == project_id)
        ) or 0
        rows = (await self.db.execute(
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.name, User.id).offset(offset).limit(limit)
        )).all()
        return list(rows), total

    async def assignees(self, project_id: int, offset: int, limit: int) -> tuple[list[User], int]:
        criteria = (ProjectMember.project_id == project_id, ProjectMember.role.in_(("manager", "member")), User.is_active.is_(True))
        total = await self.db.scalar(select(func.count()).select_from(User).join(ProjectMember).where(*criteria)) or 0
        users = (await self.db.scalars(
            select(User).join(ProjectMember).where(*criteria).order_by(User.name, User.id).offset(offset).limit(limit)
        )).all()
        return list(users), total

    async def memberships_for_user(self, user_id: int, offset: int, limit: int) -> tuple[list[tuple[ProjectMember, Project]], int]:
        total = await self.db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == user_id)) or 0
        rows = (await self.db.execute(
            select(ProjectMember, Project).join(Project, Project.id == ProjectMember.project_id)
            .where(ProjectMember.user_id == user_id).order_by(Project.key, Project.id).offset(offset).limit(limit)
        )).all()
        return list(rows), total

    async def upsert(self, *, actor: User, project_id: int, email: str, role: str, actor_role: str) -> ProjectMember:
        async with self._transaction():
            target = await self.db.scalar(select(User).where(User.email == normalizar_email(email)).with_for_update())
            if target is None or not target.is_active:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario indisponivel.")
            member = await self.db.scalar(
                select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == target.id).with_for_update()
            )
            if actor_role != "admin" and (role == "manager" or (member is not None and member.role == "manager")):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acao nao permitida neste projeto.")
            old = {"role": member.role} if member is not None else None
            if member is None:
                member = ProjectMember(project_id=project_id, user_id=target.id, role=role)
                self.db.add(member)
                action = "project_member_added"
            else:
                member.role = role
                action = "project_member_updated"
            self._audit(actor_id=actor.id, action=action, subject_user_id=target.id, project_id=project_id, old_value=old, new_value={"role": role})
            await self.db.flush()
        return member

    async def remove(self, *, actor: User, project_id: int, user_id: int, actor_role: str) -> None:
        async with self._transaction():
            # A ordem user -> membership e a mesma dos lotes para evitar deadlock.
            target = await self.db.scalar(select(User).where(User.id == user_id).with_for_update())
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario indisponivel.")
            member = await self.db.scalar(
                select(ProjectMember).where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id).with_for_update()
            )
            if member is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario indisponivel.")
            if actor_role != "admin" and member.role == "manager":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acao nao permitida neste projeto.")
            old = {"role": member.role}
            await self.db.delete(member)
            self._audit(actor_id=actor.id, action="project_member_removed", subject_user_id=user_id, project_id=project_id, old_value=old)
            await self.db.flush()
