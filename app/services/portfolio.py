"""Leitura e edição transacional do portfólio ligado ao mural Git."""

from __future__ import annotations

import secrets
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modelos import App, Mural
from app.models import Board, BoardColumn, Project, Task, User
from app.models.membership import ProjectMember
from app.schemas.portfolio import (
    PendingTask,
    PortfolioAppUpdate,
    PortfolioItem,
    PortfolioLink,
    PortfolioOwner,
    PortfolioProjectUpdate,
    PortfolioRead,
)
from app.services.kanban import create_default_board
from app.services.access import AccessService


PROJECT_OPTIONS = (selectinload(Project.board), selectinload(Project.owner))


def not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


class PortfolioService:
    def __init__(self, session: AsyncSession, get_mural: Callable[[], Mural | None]) -> None:
        self.session = session
        self.get_mural = get_mural

    @asynccontextmanager
    async def _transaction(self):
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

    def _mural(self) -> Mural | None:
        return self.get_mural()

    def _app(self, app_id: str) -> App:
        mural = self._mural()
        if mural is not None:
            app = next((item for item in mural.apps if item.id == app_id), None)
            if app is not None:
                return app
        raise not_found("aplicacao Git nao encontrada no mural atual")

    async def _active_owner(self, owner_id: int | None, project_id: int) -> User | None:
        if owner_id is None:
            return None
        return await AccessService(self.session).eligible_assignee(owner_id, project_id)

    @staticmethod
    def _project_key(app_id: str) -> str:
        normalized = re.sub(r"[^A-Z0-9_]+", "_", app_id.upper()).strip("_")
        normalized = normalized[:18] or "PROJECT"
        return f"APP_{normalized}_{secrets.token_hex(3).upper()}"

    @staticmethod
    def _links(value: Sequence[PortfolioLink]) -> list[dict[str, str]]:
        return [item.model_dump() for item in value]

    @staticmethod
    def _owner(project: Project) -> PortfolioOwner | None:
        if project.owner is None:
            return None
        return PortfolioOwner(id=project.owner.id, name=project.owner.name, email=project.owner.email)

    @staticmethod
    def _card(
        project: Project | None,
        git: App | None,
        pending: Sequence[PendingTask] = (),
        pending_total: int = 0,
        role: str = "viewer",
    ) -> PortfolioItem:
        if project is None:
            if git is None:
                raise ValueError("card sem projeto e sem aplicacao Git")
            return PortfolioItem(
                ref=f"git:{git.id}", project_id=None, legacy_app_id=git.id, board_id=None,
                version=0, name=git.nome, description=None, priority=None, status=None, owner=None,
                due_date=None, objective=None, milestone_title=None, milestone_due_date=None,
                links=[], pending_tasks=[], pending_tasks_total=0, git=git, role=role,
            )
        return PortfolioItem(
            ref=f"git:{git.id}" if git is not None else f"project:{project.id}",
            project_id=project.id, legacy_app_id=project.legacy_app_id,
            board_id=project.board.id if project.board is not None else None,
            version=project.portfolio_version, name=project.name, description=project.description,
            priority=project.priority, status=project.status, owner=PortfolioService._owner(project),
            due_date=project.due_date, objective=project.objective, milestone_title=project.milestone_title,
            milestone_due_date=project.milestone_due_date,
            links=[PortfolioLink.model_validate(link) for link in project.links],
            pending_tasks=list(pending), pending_tasks_total=pending_total, git=git, role=role,
        )

    async def _projects(self, project_ids: list[int] | None) -> Sequence[Project]:
        return (await self.session.scalars(
            select(Project).where(True if project_ids is None else Project.id.in_(project_ids))
            .options(*PROJECT_OPTIONS).order_by(Project.id)
        )).all()

    async def _pending_tasks(self, project_ids: list[int] | None) -> tuple[dict[int, list[PendingTask]], dict[int, int]]:
        ranked = (
            select(
                Task.id.label("task_id"),
                Board.project_id.label("project_id"),
                func.count(Task.id).over(partition_by=Board.project_id).label("total"),
                func.row_number().over(
                    partition_by=Board.project_id,
                    order_by=(
                        case((Task.priority == "critical", 0), else_=1),
                        Task.due_date.asc().nulls_last(),
                        Task.id.asc(),
                    ),
                ).label("position"),
            )
            .join(Board, Task.board_id == Board.id)
            .join(
                BoardColumn,
                and_(Task.board_id == BoardColumn.board_id, Task.column_id == BoardColumn.id),
            )
            .where(Task.archived_at.is_(None), BoardColumn.is_done.is_(False),
                   True if project_ids is None else Board.project_id.in_(project_ids))
            .subquery()
        )
        rows = await self.session.execute(
            select(Task, ranked.c.project_id, ranked.c.total)
            .join(ranked, Task.id == ranked.c.task_id)
            .where(ranked.c.position <= 20)
            .options(selectinload(Task.board).selectinload(Board.project))
            .order_by(ranked.c.project_id, ranked.c.position)
        )
        tasks: dict[int, list[PendingTask]] = defaultdict(list)
        totals: dict[int, int] = {}
        for task, project_id, total in rows.tuples():
            tasks[project_id].append(
                PendingTask(
                    id=task.id,
                    code=f"{task.board.project.key}-{task.number}",
                    title=task.title,
                    due_date=task.due_date,
                    priority=task.priority.value if hasattr(task.priority, "value") else str(task.priority),
                )
            )
            totals[project_id] = total
        return tasks, totals

    async def read(self, user: User) -> PortfolioRead:
        project_ids = await AccessService(self.session).visible_project_ids(user)
        mural = self._mural()
        apps = mural.apps if mural is not None else []
        apps_by_id = {app.id: app for app in apps}
        projects = await self._projects(project_ids)
        samples, totals = await self._pending_tasks(project_ids)
        roles = dict((await self.session.execute(
            select(ProjectMember.project_id, ProjectMember.role).where(ProjectMember.user_id == user.id)
        )).all()) if project_ids is not None else {project.id: "admin" for project in projects}
        linked = {project.legacy_app_id: project for project in projects if project.legacy_app_id in apps_by_id}
        items = [
            self._card(linked.get(app.id), app, samples.get(linked[app.id].id, ()), totals.get(linked[app.id].id, 0), roles[linked[app.id].id])
            if app.id in linked
            else self._card(None, app, role="admin")
            for app in apps
            if project_ids is None or app.id in linked
        ]
        items.extend(
            self._card(project, None, samples.get(project.id, ()), totals.get(project.id, 0), roles[project.id])
            for project in projects
            if project.legacy_app_id not in apps_by_id
        )
        return PortfolioRead(git_collected_at=mural.gerado_em if mural is not None else "", items=items)

    async def _project(self, project_id: int, *, lock: bool = False) -> Project:
        statement = select(Project).where(Project.id == project_id).options(*PROJECT_OPTIONS)
        if lock:
            statement = statement.with_for_update()
        project = await self.session.scalar(statement)
        if project is None:
            raise not_found("projeto nao encontrado")
        return project

    async def _apply_metadata(self, project: Project, data: PortfolioAppUpdate | PortfolioProjectUpdate) -> None:
        fields = (
            "name", "description", "priority", "status", "due_date", "objective",
            "milestone_title", "milestone_due_date",
        )
        for field in fields:
            if field in data.model_fields_set:
                setattr(project, field, getattr(data, field))
        if "links" in data.model_fields_set:
            project.links = self._links(data.links or [])
        if "owner_id" in data.model_fields_set and data.owner_id != project.owner_id:
            project.owner = await self._active_owner(data.owner_id, project.id)

    async def update_app(self, app_id: str, data: PortfolioAppUpdate, user: User) -> PortfolioItem:
        try:
            async with self._transaction():
                project = await self.session.scalar(
                    select(Project).where(Project.legacy_app_id == app_id).options(*PROJECT_OPTIONS).with_for_update()
                )
                if project is None:
                    AccessService.require_admin(user)
                    role = "admin"
                    app = self._app(app_id)
                    if data.version != 0:
                        raise conflict("a primeira edicao deve usar versao 0")
                    project = Project(key=self._project_key(app.id), name=data.name or app.nome, legacy_app_id=app.id)
                    self.session.add(project)
                    await create_default_board(self.session, project)
                    await self._apply_metadata(project, data)
                else:
                    role = await AccessService(self.session).require_project(user, project.id, "manage")
                    app = self._app(app_id)
                    if project.portfolio_version != data.version:
                        raise conflict("a versao do portfolio esta desatualizada")
                    await self._apply_metadata(project, data)
                    project.portfolio_version += 1
                await self.session.flush()
                project = await self._project(project.id)
            samples, totals = await self._pending_tasks([project.id])
            return self._card(project, app, samples.get(project.id, ()), totals.get(project.id, 0), role)
        except IntegrityError as error:
            raise conflict("projeto ja vinculado a esta aplicacao Git") from error

    async def update_project(self, project_id: int, data: PortfolioProjectUpdate, user: User) -> PortfolioItem:
        try:
            async with self._transaction():
                role = await AccessService(self.session).require_project(user, project_id, "manage")
                project = await self._project(project_id, lock=True)
                if project.portfolio_version != data.version:
                    raise conflict("a versao do portfolio esta desatualizada")
                if "legacy_app_id" in data.model_fields_set and data.legacy_app_id != project.legacy_app_id:
                    AccessService.require_admin(user)
                    if data.legacy_app_id is not None:
                        self._app(data.legacy_app_id)
                    project.legacy_app_id = data.legacy_app_id
                await self._apply_metadata(project, data)
                project.portfolio_version += 1
                await self.session.flush()
                project = await self._project(project.id)
            git = None
            if project.legacy_app_id is not None:
                mural = self._mural()
                if mural is not None:
                    git = next((app for app in mural.apps if app.id == project.legacy_app_id), None)
            samples, totals = await self._pending_tasks([project.id])
            return self._card(project, git, samples.get(project.id, ()), totals.get(project.id, 0), role)
        except IntegrityError as error:
            raise conflict("identificador de aplicacao Git ja esta vinculado a outro projeto") from error
