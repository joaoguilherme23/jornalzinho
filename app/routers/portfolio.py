"""Rotas do portfólio, independentes da composição da aplicação."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.security import get_ready_user
from app.modelos import Mural
from app.models import User
from app.schemas.portfolio import PortfolioAppUpdate, PortfolioItem, PortfolioProjectUpdate, PortfolioRead
from app.services.portfolio import PortfolioService


def build_portfolio_router(get_mural: Callable[[], Mural | None]) -> APIRouter:
    router = APIRouter(prefix="/portfolio", tags=["portfolio"])

    @router.get("", response_model=PortfolioRead)
    async def get_portfolio(
        session: AsyncSession = Depends(get_session),
        user: User = Depends(get_ready_user),
    ) -> PortfolioRead:
        return await PortfolioService(session, get_mural).read(user)

    @router.put("/apps/{app_id}", response_model=PortfolioItem)
    async def update_git_app(
        app_id: str,
        data: PortfolioAppUpdate,
        session: AsyncSession = Depends(get_session),
        user: User = Depends(get_ready_user),
    ) -> PortfolioItem:
        return await PortfolioService(session, get_mural).update_app(app_id, data, user)

    @router.patch("/projects/{project_id}", response_model=PortfolioItem)
    async def update_project(
        project_id: int,
        data: PortfolioProjectUpdate,
        session: AsyncSession = Depends(get_session),
        user: User = Depends(get_ready_user),
    ) -> PortfolioItem:
        return await PortfolioService(session, get_mural).update_project(project_id, data, user)

    return router
