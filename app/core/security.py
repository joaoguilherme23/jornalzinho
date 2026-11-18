"""Dependencia JWT para proteger a API privada."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth_settings import AuthSettings, get_auth_settings
from app.core.database import get_session
from app.core.session_policy import session_deadline, utc_now
from app.models.user import Session, User
from app.services.access import AccessService


ACCESS_TOKEN_MINUTES = 15
JWT_ALGORITHM = "HS256"
bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais invalidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(
    *, user: User, session_id: int, settings: AuthSettings,
    session_expires_at: datetime | None = None, now: datetime | None = None,
) -> str:
    now = now or utc_now()
    expires_at = now + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    if session_expires_at is not None:
        expires_at = min(expires_at, session_expires_at)
    return jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(session_id),
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": now,
            "exp": expires_at,
        },
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_identity(token: str, settings: AuthSettings) -> tuple[int, int]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            audience=settings.JWT_AUDIENCE,
            options={"require_exp": True, "require_iat": True, "require_sub": True},
        )
        user_id = int(payload["sub"])
        session_id = int(payload["sid"])
        if user_id < 1 or session_id < 1:
            raise ValueError("identificador invalido")
        return user_id, session_id
    except (JWTError, KeyError, TypeError, ValueError):
        raise unauthorized() from None


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    user_id, session_id = decode_access_identity(credentials.credentials, settings)
    credential = await db.scalar(
        select(Session)
        .options(selectinload(Session.user))
        .where(Session.id == session_id, Session.user_id == user_id)
    )
    now = utc_now()
    if (
        credential is None
        or credential.revoked_at is not None
        or session_deadline(credential) <= now
        or not credential.user.is_active
    ):
        raise unauthorized()
    return credential.user


async def get_ready_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    AccessService.require_ready(current_user)
    return current_user


async def get_admin_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    AccessService.require_admin(current_user)
    return current_user
