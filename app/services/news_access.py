"""Filtra as fontes Git pelo mesmo acesso aplicado aos projetos e tarefas."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, User
from app.services.access import AccessService


async def allowed_app_ids(session: AsyncSession, user: User) -> set[str] | None:
    projects = await AccessService(session).visible_project_ids(user)
    if projects is None:
        return None
    return set(await session.scalars(
        select(Project.legacy_app_id).where(Project.id.in_(projects), Project.legacy_app_id.is_not(None))
    ))


def filter_releases(payload: dict, allowed: set[str] | None) -> dict:
    if allowed is None:
        return payload
    return {**payload, "apps": [app for app in payload.get("apps", []) if app.get("id") in allowed]}


def filter_editorial(payload: dict, allowed: set[str] | None) -> dict:
    if allowed is None:
        return payload
    return {
        section: {key: value for key, value in payload.get(section, {}).items() if key in allowed}
        for section in ("apps", "curadoria")
    }
