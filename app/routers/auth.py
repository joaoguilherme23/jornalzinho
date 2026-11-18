"""Rotas de login, renovacao e encerramento de sessao."""

from __future__ import annotations

import time
import logging
from collections import deque
from datetime import datetime
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_settings import AuthSettings, get_auth_settings
from app.core.database import get_session
from app.core.security import ACCESS_TOKEN_MINUTES, create_access_token, decode_access_identity, get_current_user
from app.core.session_policy import session_deadline, utc_now
from app.models.user import Session, User
from app.schemas.auth import AccessTokenResponse, ChangePasswordRequest, LoginRequest, UserPublic, normalizar_email
from app.services.auth import AuthService


REFRESH_COOKIE_NAME = "jornalzinho_refresh"
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_PER_EMAIL = 5
LOGIN_MAX_PER_IP = 20
LOGIN_MAX_TRACKED_KEYS = 4096

router = APIRouter(prefix="/api/v1/auth", tags=["autenticacao"])
log = logging.getLogger("jornalzinho.auth")


class LoginRateLimiter:
    """Limite local por processo. Para mais workers, substituir por armazenamento compartilhado."""

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}

    def _purge_expired(self, now: float) -> None:
        for key, attempts in tuple(self._attempts.items()):
            while attempts and attempts[0] <= now - LOGIN_WINDOW_SECONDS:
                attempts.popleft()
            if not attempts:
                self._attempts.pop(key, None)

    def _allow(self, key: str, limit: int, now: float) -> int | None:
        attempts = self._attempts.get(key)
        if attempts is None:
            # Nunca despeja chaves ainda ativas: isso liberaria tentativas brutas.
            if len(self._attempts) >= LOGIN_MAX_TRACKED_KEYS:
                return LOGIN_WINDOW_SECONDS
            attempts = deque()
            self._attempts[key] = attempts
        if len(attempts) >= limit:
            return max(1, ceil(attempts[0] + LOGIN_WINDOW_SECONDS - now))
        attempts.append(now)
        return None

    def allow_login(self, *, email_key: str, ip_key: str) -> int | None:
        now = time.monotonic()
        self._purge_expired(now)
        # IP entra primeiro para que emails unicos nao gerem estado sob ataque distribuido.
        retry_after = self._allow(ip_key, LOGIN_MAX_PER_IP, now)
        if retry_after is not None:
            return retry_after
        return self._allow(email_key, LOGIN_MAX_PER_EMAIL, now)

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)


login_limiter = LoginRateLimiter()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def require_trusted_origin(request: Request, settings: AuthSettings = Depends(get_auth_settings)) -> None:
    """Impede que um cookie seja criado, rotacionado ou revogado por outra origem."""

    if request.headers.get("origin") != settings.APP_ORIGIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origem recusada.")


def set_refresh_cookie(
    response: Response, refresh_token: str, settings: AuthSettings, expires_at: datetime,
) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=max(0, int((expires_at - utc_now()).total_seconds())),
        path=settings.refresh_cookie_path,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


def clear_refresh_cookie(response: Response, settings: AuthSettings) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=settings.refresh_cookie_path,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )


def token_response(user: User, session: Session, settings: AuthSettings) -> AccessTokenResponse:
    now = utc_now().replace(microsecond=0)
    deadline = session_deadline(session)
    expires_in = min(ACCESS_TOKEN_MINUTES * 60, int((deadline - now).total_seconds()))
    if expires_in <= 0:
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")
    return AccessTokenResponse(
        access_token=create_access_token(
            user=user, session_id=session.id, settings=settings, session_expires_at=deadline, now=now,
        ),
        user=UserPublic.model_validate(user),
        expires_in=expires_in,
        session_expires_at=deadline,
        server_time=utc_now(),
    )


def rejected_refresh() -> JSONResponse:
    # Uma resposta atrasada nao pode apagar o cookie de um login mais recente.
    return JSONResponse(
        {"detail": "Credenciais invalidas."}, status_code=401, headers={"WWW-Authenticate": "Bearer"}
    )


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    _: None = Depends(require_trusted_origin),
    db: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> AccessTokenResponse:
    email_key = f"email:{normalizar_email(body.email)}"
    ip_key = f"ip:{client_ip(request)}"
    retry_after = login_limiter.allow_login(email_key=email_key, ip_key=ip_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Tente novamente mais tarde.",
            headers={"Retry-After": str(retry_after)},
        )

    service = AuthService(db)
    user = await service.authenticate(body.email, body.password)
    if user is None:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais invalidas.")

    session, refresh = await service.create_refresh_session(user)
    # Substituir a conta/sessao no mesmo navegador encerra a credencial anterior.
    previous = request.cookies.get(REFRESH_COOKIE_NAME)
    if previous:
        await service.revoke_refresh_session(previous)
    await db.commit()
    log.info("session.login_completed")
    login_limiter.clear(email_key)
    login_limiter.clear(ip_key)
    body = token_response(user, session, settings)
    set_refresh_cookie(response, refresh, settings, body.session_expires_at)
    return body


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    request: Request,
    response: Response,
    _: None = Depends(require_trusted_origin),
    db: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> AccessTokenResponse | Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        return rejected_refresh()
    async with db.begin():
        service = AuthService(db)
        result = await service.rotate_refresh_session(refresh_token)
    if result is None:
        return rejected_refresh()
    user, session, rotated_token = result
    log.info("session.refresh_completed")
    body = token_response(user, session, settings)
    set_refresh_cookie(response, rotated_token, settings, body.session_expires_at)
    return body


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> Response:
    try:
        await AuthService(db).change_password(current_user.id, body.current_password, body.new_password)
        await db.commit()
    except ValueError as error:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)) from error
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response, settings)
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    _: None = Depends(require_trusted_origin),
    db: AsyncSession = Depends(get_session),
    settings: AuthSettings = Depends(get_auth_settings),
) -> Response:
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    access_identity = None
    scheme, _, access = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() == "bearer" and access:
        try:
            access_identity = decode_access_identity(access, settings)
        except HTTPException:
            pass  # Cookie continua podendo revogar se o JWT ja expirou.
    if refresh_token or access_identity:
        async with db.begin():
            service = AuthService(db)
            if refresh_token:
                await service.revoke_refresh_session(refresh_token)
            if access_identity:
                await service.revoke_access_session(user_id=access_identity[0], session_id=access_identity[1])
    clear_refresh_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    log.info("session.logout_completed")
    return response
