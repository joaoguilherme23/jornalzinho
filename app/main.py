"""Jornalzinho: composição da API privada, mural e aplicação React."""

from __future__ import annotations

import hashlib
import json
import logging
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from html import escape
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette._utils import get_route_path

from . import config
from .agendador import Servico
from .core.auth_settings import get_auth_settings
from .core.database import dispose_engine, get_engine, get_session
from .core.security import get_ready_user, get_admin_user
from .models import User
from .services.news_access import allowed_app_ids, filter_editorial, filter_releases
from .routers.auth import router as auth_router
from .routers.users import router as users_router
from .routers.projects import projects_router
from .routers.boards import boards_router, columns_router
from .routers.tasks import tasks_router
from .routers.portfolio import build_portfolio_router
from .routers.members import router as members_router
from .routers.labels import labels_router
from .routers.requests import requests_router, RequestBodyLimitMiddleware
from .routers.public_requests import public_requests_router
from .routers.publication import public_router, publication_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("mural")

RAIZ = Path(__file__).resolve().parents[1]
FRONTEND = RAIZ / "frontend" / "dist"
CATALOGO = Path(__file__).resolve().parent / "editorial_catalog.json"

cfg = config.carregar()
servico = Servico(cfg)
auth_settings = get_auth_settings()


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    log.info("subindo: %s", cfg)
    servico.carregar_cache()
    servico.iniciar()
    try:
        yield
    finally:
        await servico.parar()
        await dispose_engine()


aplicacao = FastAPI(
    title="Jornalzinho",
    description="Kanban do time e notícias sobre os projetos.",
    version="2.0.0",
    lifespan=ciclo_de_vida,
    root_path=auth_settings.APP_ROOT_PATH,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

for router in (auth_router, users_router, members_router):
    aplicacao.include_router(router)
aplicacao.add_middleware(RequestBodyLimitMiddleware)
for router in (projects_router, boards_router, columns_router, tasks_router, labels_router, requests_router,
               public_requests_router, public_router, publication_router):
    aplicacao.include_router(router, prefix="/api/v1")
aplicacao.include_router(build_portfolio_router(lambda: servico.mural), prefix="/api/v1")


@aplicacao.middleware("http")
async def cabecalhos_privados(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    response.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "font-src 'self'; img-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ))
    if "/api/" in request.url.path:
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Authorization, Cookie"
    return response


@aplicacao.exception_handler(RequestValidationError)
async def entrada_invalida(_: Request, error: RequestValidationError):
    # A senha nunca deve voltar no input de uma resposta de validação.
    errors = [{key: entry[key] for key in ("loc", "msg", "type")} for entry in error.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@aplicacao.exception_handler(SQLAlchemyError)
async def erro_de_persistencia(_: Request, error: SQLAlchemyError):
    log.error("falha de persistencia: %s", type(error).__name__)
    return JSONResponse(
        {"detail": "Não foi possível concluir a operação. Tente novamente."},
        status_code=503 if isinstance(error, OperationalError) else 500,
    )


@aplicacao.get("/api/v1/openapi.json", dependencies=[Depends(get_ready_user)], include_in_schema=False)
async def contrato():
    return aplicacao.openapi()


@aplicacao.get("/", include_in_schema=False)
@aplicacao.get("/login", include_in_schema=False)
@aplicacao.get("/noticias", include_in_schema=False)
@aplicacao.get("/noticias/{news_id}", include_in_schema=False)
@aplicacao.get("/acompanhar", include_in_schema=False)
@aplicacao.get("/acompanhar/{code}", include_in_schema=False)
@aplicacao.get("/solicitar", include_in_schema=False)
@aplicacao.get("/minha-solicitacao", include_in_schema=False)
@aplicacao.get("/app", include_in_schema=False)
@aplicacao.get("/app/{workspace_path:path}", include_in_schema=False)
async def pagina(request: Request) -> Response:
    # O navegador deve abrir o HTML na origem aceita pelo login. Corrige aliases
    # locais sem ampliar as origens autorizadas nos POST de autenticacao.
    origin = urlsplit(auth_settings.APP_ORIGIN)
    if origin.scheme == request.url.scheme == "http" and origin.hostname in {"localhost", "127.0.0.1", "::1"}:
        port = f":{origin.port}" if origin.port is not None else ""
        aliases = {f"{host}{port}" for host in ("localhost", "127.0.0.1", "[::1]")}
        host = request.headers.get("host", "").lower()
        if host in aliases and host != origin.netloc.lower():
            target = f"{auth_settings.APP_ORIGIN}{auth_settings.APP_ROOT_PATH}{get_route_path(request.scope)}"
            if request.url.query:
                target += f"?{request.url.query}"
            return RedirectResponse(target, status_code=307, headers={"Cache-Control": "no-store"})
    if not (FRONTEND / "index.html").is_file():
        raise HTTPException(503, "Frontend não compilado. Execute npm ci e npm run build em frontend/.")
    # O mesmo build funciona na raiz e em APP_ROOT_PATH, inclusive em deep links.
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    base = escape(f"{auth_settings.APP_ROOT_PATH}/", quote=True)
    html = html.replace('<base href="/" />', f'<base href="{base}" />')
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache"},
    )


def private_json(payload: dict, if_none_match: str | None = None) -> Response:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    etag = '"' + hashlib.sha256(body).hexdigest() + '"'
    if if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"ETag": etag},
    )


@aplicacao.get("/api/releases.json")
async def releases(
    if_none_match: str | None = Header(default=None),
    user: User = Depends(get_ready_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    allowed = await allowed_app_ids(session, user)
    return private_json(filter_releases(json.loads(servico.corpo), allowed), if_none_match)


@aplicacao.get("/api/editorial.json")
async def catalogo_editorial(
    if_none_match: str | None = Header(default=None),
    user: User = Depends(get_ready_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    allowed = await allowed_app_ids(session, user)
    payload = json.loads(CATALOGO.read_text(encoding="utf-8"))
    return private_json(filter_editorial(payload, allowed), if_none_match)


@aplicacao.get("/health")
async def health() -> JSONResponse:
    estado = servico.saude()
    async def verificar_banco():
        async with get_engine().connect() as connection:
            await connection.execute(text("SELECT 1"))
    try:
        await asyncio.wait_for(verificar_banco(), timeout=5)
        banco_ok = True
    except Exception:
        banco_ok = False
    ok = estado["ok"] and banco_ok
    return JSONResponse(
        {"ok": ok, "banco": banco_ok, "ultima_coleta": estado["ultima_coleta"]},
        status_code=200 if ok else 503,
    )


# Arquivos estáticos ausentes e APIs desconhecidas continuam retornando 404.
if FRONTEND.is_dir():
    aplicacao.mount("/", StaticFiles(directory=FRONTEND), name="frontend")
