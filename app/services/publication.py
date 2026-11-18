"""Consultas públicas e operações administrativas de publicação."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re
from typing import AsyncIterator

from fastapi import HTTPException, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.board import Board, BoardColumn
from app.models.membership import ProjectMember
from app.models.project import Project
from app.models.publication import ColumnPublication, ProjectPublication, PublicNews, TaskPublication
from app.models.task import Task
from app.models.user import User
from app.schemas.publication import (
    ColumnPublicationUpdate,
    NewsCreate,
    NewsUpdate,
    ProjectPublicationUpdate,
    PublicationColumnRead,
    PublicationNewsRead,
    PublicationProjectDetail,
    PublicationProjectListItem,
    PublicationProjectRead,
    PublicationTaskRead,
    PublicNewsRead,
    PublicProjectRead,
    PublicWorkRead,
    TaskPublicationUpdate,
)
from app.services.access import AccessService


PUBLIC_STATUSES = ("planned", "in_progress", "waiting", "completed")
PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")
MAX_TASK_NUMBER = 2_147_483_647


def not_found(detail: str = "Item nao encontrado.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A publicação foi alterada por outra pessoa.")


class PublicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.access = AccessService(session)

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[None]:
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

    @staticmethod
    def _status_expression():
        return case(
            (BoardColumn.is_done.is_(True), "completed"),
            else_=func.coalesce(ColumnPublication.status, "planned"),
        )

    async def public_projects(self) -> list[PublicProjectRead]:
        rows = await self.session.execute(
            select(Project.id, ProjectPublication.name, ProjectPublication.summary)
            .join(ProjectPublication, ProjectPublication.project_id == Project.id)
            .where(ProjectPublication.published.is_(True))
            .order_by(ProjectPublication.name, Project.id)
        )
        return [PublicProjectRead(id=row.id, name=row.name, summary=row.summary) for row in rows]

    def _public_work_statement(self):
        return (
            select(Task, Project, ProjectPublication, TaskPublication, BoardColumn, ColumnPublication)
            .join(Board, Board.id == Task.board_id)
            .join(Project, Project.id == Board.project_id)
            .join(ProjectPublication, ProjectPublication.project_id == Project.id)
            .join(TaskPublication, TaskPublication.task_id == Task.id)
            .join(BoardColumn, BoardColumn.id == Task.column_id)
            .outerjoin(ColumnPublication, ColumnPublication.column_id == BoardColumn.id)
            .where(
                ProjectPublication.published.is_(True),
                TaskPublication.published.is_(True),
                Task.archived_at.is_(None),
            )
        )

    @staticmethod
    def _public_work(
        row: tuple[Task, Project, ProjectPublication, TaskPublication, BoardColumn, ColumnPublication | None]
    ) -> PublicWorkRead:
        task, project, project_publication, publication, column, column_publication = row
        work_status = "completed" if column.is_done else (column_publication.status if column_publication else "planned")
        updated_values = [
            task.updated_at,
            project_publication.updated_at,
            publication.updated_at,
            column.updated_at,
        ]
        if column_publication is not None:
            updated_values.append(column_publication.updated_at)
        updated_at = max(updated_values)
        return PublicWorkRead(
            code=f"{project.key}-{task.number}",
            title=publication.title,
            summary=publication.summary,
            project_id=project.id,
            project_name=project_publication.name,
            status=work_status,
            updated_at=updated_at,
        )

    async def public_work(
        self, *, project_id: int | None, work_status: str | None, q: str | None, offset: int, limit: int
    ) -> tuple[list[PublicWorkRead], int]:
        statement = self._public_work_statement()
        conditions = []
        if project_id is not None:
            conditions.append(Project.id == project_id)
        if work_status is not None:
            conditions.append(self._status_expression() == work_status)
        if q:
            pattern = f"%{q.strip()}%"
            conditions.append(or_(TaskPublication.title.ilike(pattern), TaskPublication.summary.ilike(pattern)))
        if conditions:
            statement = statement.where(*conditions)
        count = await self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = (await self.session.execute(statement.order_by(Task.updated_at.desc(), Task.id.desc()).offset(offset).limit(limit))).all()
        return [self._public_work(row) for row in rows], count

    async def public_work_by_code(self, code: str) -> PublicWorkRead:
        key, separator, number_text = code.rpartition("-")
        if (
            not separator
            or PROJECT_KEY_PATTERN.fullmatch(key) is None
            or not number_text.isdecimal()
            or len(number_text) > 10
            or (len(number_text) > 1 and number_text.startswith("0"))
        ):
            raise not_found()
        number = int(number_text)
        if number < 1 or number > MAX_TASK_NUMBER:
            raise not_found()
        row = (await self.session.execute(
            self._public_work_statement().where(Project.key == key, Task.number == number)
        )).one_or_none()
        if row is None:
            raise not_found()
        return self._public_work(row)

    def _public_news_statement(self):
        return (
            select(PublicNews, ProjectPublication.name)
            .outerjoin(Project, Project.id == PublicNews.project_id)
            .outerjoin(ProjectPublication, ProjectPublication.project_id == Project.id)
            .where(
                PublicNews.published.is_(True),
                or_(PublicNews.project_id.is_(None), ProjectPublication.published.is_(True)),
            )
        )

    @staticmethod
    def _public_news(row: tuple[PublicNews, str | None]) -> PublicNewsRead:
        item, project_name = row
        return PublicNewsRead(
            id=item.id, title=item.title, summary=item.summary, body=item.body,
            project_name=project_name, published_at=item.published_at,
        )

    async def public_news(self, *, offset: int, limit: int) -> tuple[list[PublicNewsRead], int]:
        statement = self._public_news_statement()
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = (await self.session.execute(
            statement.order_by(PublicNews.published_at.desc().nullslast(), PublicNews.id.desc()).offset(offset).limit(limit)
        )).all()
        return [self._public_news(row) for row in rows], total

    async def public_news_by_id(self, news_id: int) -> PublicNewsRead:
        row = (await self.session.execute(self._public_news_statement().where(PublicNews.id == news_id))).one_or_none()
        if row is None:
            raise not_found()
        return self._public_news(row)

    async def management_projects(self, user: User) -> list[PublicationProjectListItem]:
        ids = await self.access.visible_project_ids(user)
        statement = select(Project.id, Project.name).order_by(Project.name, Project.id)
        if ids is not None:
            statement = statement.join(ProjectMember).where(ProjectMember.user_id == user.id, ProjectMember.role == "manager")
        rows = await self.session.execute(statement)
        return [PublicationProjectListItem(id=row.id, name=row.name, can_publish=True) for row in rows]

    async def management_project(self, *, project_id: int, user: User) -> PublicationProjectDetail:
        await self.access.require_project(user, project_id, "manage")
        project = await self.session.get(Project, project_id)
        if project is None:
            raise not_found("Projeto nao encontrado.")
        project_publication = await self.session.get(ProjectPublication, project_id)
        project_read = PublicationProjectRead(
            id=project.id,
            name=project_publication.name if project_publication else project.name,
            summary=project_publication.summary if project_publication else project.description,
            published=project_publication.published if project_publication else False,
            version=project_publication.version if project_publication else 0,
        )
        column_rows = (await self.session.execute(
            select(BoardColumn, ColumnPublication)
            .join(Board, Board.id == BoardColumn.board_id)
            .outerjoin(ColumnPublication, ColumnPublication.column_id == BoardColumn.id)
            .where(Board.project_id == project_id)
            .order_by(BoardColumn.position, BoardColumn.id)
        )).all()
        task_rows = (await self.session.execute(
            select(Task, TaskPublication, Project.key)
            .join(Board, Board.id == Task.board_id)
            .join(Project, Project.id == Board.project_id)
            .outerjoin(TaskPublication, TaskPublication.task_id == Task.id)
            .where(Board.project_id == project_id)
            .order_by(Task.number, Task.id)
        )).all()
        return PublicationProjectDetail(
            project=project_read,
            columns=[PublicationColumnRead(
                id=column.id, name=column.name, is_done=column.is_done,
                status="completed" if column.is_done else (publication.status if publication else "planned"),
            ) for column, publication in column_rows],
            tasks=[PublicationTaskRead(
                id=task.id, code=f"{key}-{task.number}", internal_title=task.title,
                title=publication.title if publication else task.title,
                summary=publication.summary if publication else task.description,
                published=publication.published if publication else False,
                version=publication.version if publication else 0,
            ) for task, publication, key in task_rows],
        )

    async def update_project(self, *, project_id: int, data: ProjectPublicationUpdate, user: User) -> PublicationProjectRead:
        await self.access.require_project(user, project_id, "manage")
        try:
            async with self._transaction():
                item = await self.session.scalar(
                    select(ProjectPublication).where(ProjectPublication.project_id == project_id).with_for_update()
                )
                if item is None:
                    if data.version != 0:
                        raise conflict()
                    item = ProjectPublication(
                        project_id=project_id, name=data.name, summary=data.summary, published=data.published, version=1
                    )
                    self.session.add(item)
                else:
                    if item.version != data.version:
                        raise conflict()
                    item.name, item.summary, item.published = data.name, data.summary, data.published
                    item.version += 1
                await self.session.flush()
                return PublicationProjectRead(id=project_id, name=item.name, summary=item.summary, published=item.published, version=item.version)
        except IntegrityError as error:
            raise conflict() from error

    async def update_task(self, *, task_id: int, data: TaskPublicationUpdate, user: User) -> PublicationTaskRead:
        task_row = (await self.session.execute(
            select(Task, Project.key, Board.project_id)
            .join(Board, Board.id == Task.board_id)
            .join(Project, Project.id == Board.project_id)
            .where(Task.id == task_id)
        )).one_or_none()
        if task_row is None:
            raise not_found()
        task, key, project_id = task_row
        await self.access.require_project(user, project_id, "manage")
        try:
            async with self._transaction():
                item = await self.session.scalar(select(TaskPublication).where(TaskPublication.task_id == task_id).with_for_update())
                if item is None:
                    if data.version != 0:
                        raise conflict()
                    item = TaskPublication(
                        task_id=task_id, title=data.title, summary=data.summary, published=data.published, version=1
                    )
                    self.session.add(item)
                else:
                    if item.version != data.version:
                        raise conflict()
                    item.title, item.summary, item.published = data.title, data.summary, data.published
                    item.version += 1
                await self.session.flush()
                return PublicationTaskRead(
                    id=task.id, code=f"{key}-{task.number}", internal_title=task.title, title=item.title,
                    summary=item.summary, published=item.published, version=item.version,
                )
        except IntegrityError as error:
            raise conflict() from error

    async def update_column(self, *, column_id: int, data: ColumnPublicationUpdate, user: User) -> PublicationColumnRead:
        row = (await self.session.execute(
            select(BoardColumn, Board.project_id).join(Board, Board.id == BoardColumn.board_id).where(BoardColumn.id == column_id)
        )).one_or_none()
        if row is None:
            raise not_found()
        column, project_id = row
        await self.access.require_project(user, project_id, "manage")
        try:
            async with self._transaction():
                item = await self.session.scalar(select(ColumnPublication).where(ColumnPublication.column_id == column_id).with_for_update())
                if item is None:
                    item = ColumnPublication(column_id=column_id, status=data.status)
                    self.session.add(item)
                else:
                    item.status = data.status
                await self.session.flush()
                return PublicationColumnRead(
                    id=column.id, name=column.name, is_done=column.is_done,
                    status="completed" if column.is_done else item.status,
                )
        except IntegrityError as error:
            raise conflict() from error

    async def _require_news_access(self, *, project_id: int | None, user: User) -> None:
        if project_id is None:
            self.access.require_admin(user)
        else:
            await self.access.require_project(user, project_id, "manage")

    async def management_news(self, *, user: User, offset: int, limit: int) -> tuple[list[PublicationNewsRead], int]:
        ids = await self.access.visible_project_ids(user)
        statement = select(PublicNews)
        if ids is not None:
            statement = statement.join(ProjectMember, ProjectMember.project_id == PublicNews.project_id).where(
                ProjectMember.user_id == user.id, ProjectMember.role == "manager"
            )
        total = await self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = await self.session.scalars(statement.order_by(PublicNews.updated_at.desc(), PublicNews.id.desc()).offset(offset).limit(limit))
        return [self._management_news(item) for item in rows], total

    @staticmethod
    def _management_news(item: PublicNews) -> PublicationNewsRead:
        return PublicationNewsRead(
            id=item.id, title=item.title, summary=item.summary, body=item.body, project_id=item.project_id,
            published=item.published, published_at=item.published_at, version=item.version,
        )

    async def create_news(self, *, data: NewsCreate, user: User) -> PublicationNewsRead:
        await self._require_news_access(project_id=data.project_id, user=user)
        now = datetime.now(timezone.utc)
        async with self._transaction():
            item = PublicNews(
                title=data.title, summary=data.summary, body=data.body, project_id=data.project_id,
                published=data.published, published_at=now if data.published else None, version=1,
            )
            self.session.add(item)
            await self.session.flush()
            return self._management_news(item)

    async def update_news(self, *, news_id: int, data: NewsUpdate, user: User) -> PublicationNewsRead:
        item = await self.session.get(PublicNews, news_id)
        if item is None:
            raise not_found()
        await self._require_news_access(project_id=item.project_id, user=user)
        await self._require_news_access(project_id=data.project_id, user=user)
        async with self._transaction():
            locked = await self.session.scalar(
                select(PublicNews)
                .where(PublicNews.id == news_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if locked is None:
                raise not_found()
            await self._require_news_access(project_id=locked.project_id, user=user)
            await self._require_news_access(project_id=data.project_id, user=user)
            if locked.version != data.version:
                raise conflict()
            was_published = locked.published
            locked.title, locked.summary, locked.body = data.title, data.summary, data.body
            locked.project_id, locked.published = data.project_id, data.published
            if data.published and not was_published:
                locked.published_at = datetime.now(timezone.utc)
            elif not data.published:
                locked.published_at = None
            locked.version += 1
            await self.session.flush()
            return self._management_news(locked)
