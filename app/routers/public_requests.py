"""Endpoints sem sessao para abertura e acompanhamento de solicitacoes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.public_requests import (
    PublicRequestCreate,
    PublicRequestCreated,
    PublicRequestEdit,
    PublicRequestEditRead,
    PublicRequestLookup,
    PublicRequestRead,
    PublicRequestResubmit,
)
from app.services.public_requests import PublicRequestsService


public_requests_router = APIRouter(prefix="/public/requests", tags=["public-requests"])


@public_requests_router.post("", response_model=PublicRequestCreated, status_code=status.HTTP_201_CREATED)
async def create_public_request(
    data: PublicRequestCreate,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=32, max_length=512)
    ],
    x_request_key: Annotated[
        str, Header(alias="X-Request-Key", pattern=r"^[0-9a-fA-F]{64}$")
    ],
    session: AsyncSession = Depends(get_session),
) -> PublicRequestCreated:
    address = request.client.host if request.client else None
    return await PublicRequestsService(session).create(
        data, idempotency_key, x_request_key, address
    )


@public_requests_router.post("/lookup", response_model=PublicRequestRead)
async def lookup_public_request(
    data: PublicRequestLookup,
    session: AsyncSession = Depends(get_session),
) -> PublicRequestRead:
    return await PublicRequestsService(session).lookup(data)


@public_requests_router.get("/{protocol}", response_model=PublicRequestEditRead)
async def get_public_request_for_edit(
    protocol: str,
    x_request_key: Annotated[
        str, Header(alias="X-Request-Key", pattern=r"^[0-9a-fA-F]{64}$")
    ],
    session: AsyncSession = Depends(get_session),
) -> PublicRequestEditRead:
    return await PublicRequestsService(session).edit_read(protocol, x_request_key)


@public_requests_router.put("/{protocol}", response_model=PublicRequestEditRead)
async def edit_public_request(
    protocol: str,
    data: PublicRequestEdit,
    x_request_key: Annotated[
        str, Header(alias="X-Request-Key", pattern=r"^[0-9a-fA-F]{64}$")
    ],
    session: AsyncSession = Depends(get_session),
) -> PublicRequestEditRead:
    return await PublicRequestsService(session).edit(protocol, x_request_key, data)


@public_requests_router.post("/{protocol}/resubmit", response_model=PublicRequestRead)
async def resubmit_public_request(
    protocol: str,
    data: PublicRequestResubmit,
    x_request_key: Annotated[
        str, Header(alias="X-Request-Key", pattern=r"^[0-9a-fA-F]{64}$")
    ],
    session: AsyncSession = Depends(get_session),
) -> PublicRequestRead:
    return await PublicRequestsService(session).resubmit(protocol, x_request_key, data)
