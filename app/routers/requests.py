"""Rotas privadas de solicitações e de download dos seus anexos."""

import hashlib
import ipaddress
from asyncio import Semaphore, TimeoutError, wait_for
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic
from uuid import UUID
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette._utils import get_route_path
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.database import get_session
from app.core.security import get_ready_user
from app.models import User
from app.schemas.requests import (
    RequestCreate,
    RequestEdit,
    RequestList,
    RequestRead,
    RequestResubmit,
    RequestReview,
    RequestStatus,
)
from app.services.requests import RequestsService

requests_router = APIRouter(prefix="/requests", tags=["requests"])
REQUEST_BODY_LIMIT = 21 * 1024 * 1024
PUBLIC_LOOKUP_BODY_LIMIT = 8 * 1024
PUBLIC_CREATE_ATTEMPT_LIMIT = 12
PUBLIC_OTHER_ATTEMPT_LIMIT = 60
# Compatibilidade para consumidores do limite de criacao anterior.
PUBLIC_ATTEMPT_LIMIT = PUBLIC_CREATE_ATTEMPT_LIMIT
PUBLIC_ATTEMPT_WINDOW_SECONDS = 5 * 60
PUBLIC_ATTEMPT_BUCKETS = 4096
REQUEST_BODY_MAX_CONCURRENT = 4
REQUEST_BODY_READ_TIMEOUT_SECONDS = 15


class RequestBodyLimitMiddleware:
    """Limita o stream antes de o JSON/base64 ser materializado pelo FastAPI."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self._public_attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._attempt_lock = Lock()
        self._body_read_slots = Semaphore(REQUEST_BODY_MAX_CONCURRENT)

    @staticmethod
    def _public_network_hash(scope: Scope) -> str:
        client = scope.get("client")
        address = client[0] if client else None
        try:
            ip = ipaddress.ip_address(address)
            value = str(ip) if ip.version == 4 else str(
                ipaddress.ip_network(f"{ip}/64", strict=False)
            )
        except ValueError:
            value = "unknown"
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _allow_public_attempt(self, scope: Scope, operation: str = "create") -> bool:
        """Freia parse repetido de corpos invalidos sem guardar endereco de rede."""
        now = monotonic()
        key = f"{operation}:{self._public_network_hash(scope)}"
        limit = PUBLIC_CREATE_ATTEMPT_LIMIT if operation == "create" else PUBLIC_OTHER_ATTEMPT_LIMIT
        with self._attempt_lock:
            for stale_key, stale_attempts in tuple(self._public_attempts.items()):
                while stale_attempts and now - stale_attempts[0] >= PUBLIC_ATTEMPT_WINDOW_SECONDS:
                    stale_attempts.popleft()
                if not stale_attempts:
                    del self._public_attempts[stale_key]
            attempts = self._public_attempts.get(key)
            if attempts is None:
                # Nao despeja redes ainda ativas: isso abriria bypass por chaves efemeras.
                if len(self._public_attempts) >= PUBLIC_ATTEMPT_BUCKETS:
                    return False
                attempts = deque()
                self._public_attempts[key] = attempts
            if len(attempts) >= limit:
                return False
            attempts.append(now)
            self._public_attempts.move_to_end(key)
            return True

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return None
            return parsed if parsed >= 0 else None
        return None

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            {"detail": "Solicitacao muito grande. Use ate 3 anexos de 5 MB."},
            status_code=413,
        )(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        route_path = get_route_path(scope).rstrip("/")
        public_path = route_path == "/api/v1/public/requests"
        lookup_path = route_path == "/api/v1/public/requests/lookup"
        if (
            scope["method"] not in {"POST", "PUT"}
            or not (
                route_path == "/api/v1/requests"
                or route_path.startswith("/api/v1/requests/")
                or route_path == "/api/v1/public/requests"
                or route_path.startswith("/api/v1/public/requests/")
            )
        ):
            await self.app(scope, receive, send)
            return
        public_operation: str | None = None
        if scope["method"] == "POST" and public_path:
            public_operation = "create"
        elif scope["method"] == "POST" and lookup_path:
            public_operation = "lookup"
        elif scope["method"] == "PUT" and route_path.startswith("/api/v1/public/requests/"):
            public_operation = "edit"
        elif scope["method"] == "POST" and route_path.startswith("/api/v1/public/requests/") and route_path.endswith("/resubmit"):
            public_operation = "resubmit"
        elif public_path or route_path.startswith("/api/v1/public/requests/"):
            public_operation = "other"
        if public_operation is not None and not self._allow_public_attempt(scope, public_operation):
            await JSONResponse(
                {"detail": "Muitas tentativas. Tente novamente mais tarde."},
                status_code=429,
                headers={"Retry-After": str(PUBLIC_ATTEMPT_WINDOW_SECONDS)},
            )(scope, receive, send)
            return
        body_limit = (
            min(PUBLIC_LOOKUP_BODY_LIMIT, REQUEST_BODY_LIMIT)
            if public_operation in {"lookup", "resubmit", "other"}
            else REQUEST_BODY_LIMIT
        )
        content_length = self._content_length(scope)
        if content_length is not None and content_length > body_limit:
            await self._too_large(scope, receive, send)
            return
        try:
            await wait_for(self._body_read_slots.acquire(), REQUEST_BODY_READ_TIMEOUT_SECONDS)
        except TimeoutError:
            await JSONResponse(
                {"detail": "Muitos envios simultaneos. Tente novamente."},
                status_code=503,
                headers={"Retry-After": "1"},
            )(scope, receive, send)
            return
        try:
            body = bytearray()
            deadline = monotonic() + REQUEST_BODY_READ_TIMEOUT_SECONDS
            while True:
                try:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    message = await wait_for(receive(), remaining)
                except TimeoutError:
                    await JSONResponse(
                        {"detail": "Tempo para enviar a solicitacao esgotado."},
                        status_code=408,
                    )(scope, receive, send)
                    return
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if len(body) + len(chunk) > body_limit:
                    await self._too_large(scope, receive, send)
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, send)
        finally:
            self._body_read_slots.release()


@requests_router.get("", response_model=RequestList)
async def list_requests(
    status: RequestStatus | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestList:
    return await RequestsService(session).list(user, status, offset, limit)


@requests_router.post("", response_model=RequestRead, status_code=201)
async def create_request(
    data: RequestCreate,
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestRead:
    return await RequestsService(session).create(data, user, idempotency_key)


@requests_router.get("/{request_id}", response_model=RequestRead)
async def get_request(
    request_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestRead:
    service = RequestsService(session)
    return await service.read(await service.item(request_id, user), user)


@requests_router.put("/{request_id}", response_model=RequestRead)
async def edit_request(
    request_id: int,
    data: RequestEdit,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestRead:
    return await RequestsService(session).edit(request_id, data, user)


@requests_router.post("/{request_id}/resubmit", response_model=RequestRead)
async def resubmit_request(
    request_id: int,
    data: RequestResubmit,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestRead:
    return await RequestsService(session).resubmit(request_id, data, user)


@requests_router.post("/{request_id}/review", response_model=RequestRead)
async def review_request(
    request_id: int,
    data: RequestReview,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> RequestRead:
    return await RequestsService(session).review(request_id, data, user)


@requests_router.get("/{request_id}/attachments/{attachment_id}")
async def download_attachment(
    request_id: int,
    attachment_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_ready_user),
) -> Response:
    file = await RequestsService(session).attachment(request_id, attachment_id, user)
    return Response(
        file.content,
        media_type=file.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(file.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )
