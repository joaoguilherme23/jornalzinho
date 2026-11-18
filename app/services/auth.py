"""Operacoes transacionais de senha, refresh e provisionamento de usuarios."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

import bcrypt
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.session_policy import SESSION_MAX_AGE_SECONDS, session_deadline, utc_now
from app.models.user import RetiredRefreshToken, Session, User
from app.schemas.auth import normalizar_email, validar_senha, validar_senha_login


log = logging.getLogger("jornalzinho.auth")
# Hash valido de uma senha sintetica, gerado com custo bcrypt 12. Ele evita que
# a ausencia ou desativacao de uma conta produza um caminho mais rapido no login.
DUMMY_PASSWORD_HASH = "$2b$12$XfGSgqbxEGfiYrZE/EM7fugiB01yhHRHsM60folh8ySREuZpHHVWa"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


async def hash_password(password: str) -> str:
    validar_senha(password)
    encoded = password.encode("utf-8")
    hashed = await run_in_threadpool(bcrypt.hashpw, encoded, bcrypt.gensalt(rounds=12))
    return hashed.decode("utf-8")


async def verify_password(password: str, password_hash: str) -> bool:
    try:
        validar_senha_login(password)
        return await run_in_threadpool(
            bcrypt.checkpw, password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, UnicodeEncodeError):
        return False


class AuthService:
    """Mantem a sessao persistida como fonte de revogacao dos access tokens."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def authenticate(self, email: str, password: str) -> User | None:
        # O lock permanece na transacao da rota ate a sessao ser criada e o commit
        # acontecer. Assim um reset concorrente espera e revoga inclusive a sessao
        # criada por uma senha anterior, em vez de deixar uma janela entre bcrypt e
        # a revogacao.
        user = await self.db.scalar(
            select(User)
            .where(User.email == normalizar_email(email))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        password_hash = user.password_hash if user is not None and user.is_active else DUMMY_PASSWORD_HASH
        matches = await verify_password(password, password_hash)
        return user if user is not None and user.is_active and matches else None

    async def create_refresh_session(self, user: User) -> tuple[Session, str]:
        now = utc_now()
        # Limpeza indexada; nenhum hash de uma sessao ainda utilizavel e removido.
        await self.db.execute(delete(RetiredRefreshToken).where(RetiredRefreshToken.expires_at <= now))
        refresh = new_refresh_token()
        session = Session(
            user_id=user.id,
            token_hash=token_hash(refresh),
            created_at=now,
            expires_at=now + timedelta(seconds=SESSION_MAX_AGE_SECONDS),
        )
        self.db.add(session)
        await self.db.flush()
        return session, refresh

    async def rotate_refresh_session(self, refresh: str) -> tuple[User, Session, str] | None:
        credential = await self.db.scalar(
            select(Session)
            .options(selectinload(Session.user))
            .where(Session.token_hash == token_hash(refresh))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utc_now()  # O prazo tambem deve valer depois de esperar o lock.
        if (
            credential is None
            or credential.revoked_at is not None
            or session_deadline(credential) <= now
            or not credential.user.is_active
        ):
            log.info("session.refresh_rejected")
            return None

        rotated = new_refresh_token()
        deadline = session_deadline(credential)
        self.db.add(RetiredRefreshToken(
            token_hash=credential.token_hash, session_id=credential.id, expires_at=deadline
        ))
        credential.token_hash = token_hash(rotated)
        credential.expires_at = deadline
        await self.db.flush()
        return credential.user, credential, rotated

    async def revoke_refresh_session(self, refresh: str) -> None:
        hashed = token_hash(refresh)
        # Leia a chave estavel antes de bloquear. Se o refresh estiver em curso,
        # esta leitura ve o hash atual antigo; depois do commit ve o historico.
        session_id = await self.db.scalar(select(Session.id).where(Session.token_hash == hashed))
        if session_id is None:
            session_id = await self.db.scalar(
                select(RetiredRefreshToken.session_id).where(RetiredRefreshToken.token_hash == hashed)
            )
        if session_id is not None:
            await self.db.execute(
                update(Session).where(Session.id == session_id, Session.revoked_at.is_(None))
                .values(revoked_at=utc_now())
            )

    async def revoke_access_session(self, *, user_id: int, session_id: int) -> None:
        # Os identificadores so chegam aqui depois de validar assinatura/claims.
        await self.db.execute(
            update(Session).where(
                Session.id == session_id, Session.user_id == user_id, Session.revoked_at.is_(None)
            ).values(revoked_at=utc_now())
        )

    async def create_user(self, *, name: str, email: str, password: str) -> User:
        cleaned_name = name.strip()
        if not cleaned_name or len(cleaned_name) > 200:
            raise ValueError("nome deve ter entre 1 e 200 caracteres")
        user = User(
            name=cleaned_name,
            email=normalizar_email(email),
            password_hash=await hash_password(password),
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def set_user_active(self, email: str, is_active: bool) -> User | None:
        user = await self.db.scalar(
            select(User).where(User.email == normalizar_email(email)).with_for_update()
        )
        if user is None:
            return None
        if not is_active and user.is_active and user.global_role == "admin":
            await self.db.execute(select(func.pg_advisory_xact_lock(2026092301)))
            active_admins = await self.db.scalar(
                select(func.count()).select_from(User).where(User.global_role == "admin", User.is_active.is_(True))
            ) or 0
            if active_admins <= 1:
                raise ValueError("nao e permitido desativar o ultimo administrador ativo")
        user.is_active = is_active
        if not is_active:
            await self.db.execute(
                update(Session)
                .where(Session.user_id == user.id, Session.revoked_at.is_(None))
                .values(revoked_at=utc_now())
            )
        return user

    async def reset_password(self, email: str, password: str) -> User | None:
        user = await self.db.scalar(
            select(User).where(User.email == normalizar_email(email)).with_for_update()
        )
        if user is None:
            return None
        user.password_hash = await hash_password(password)
        user.must_change_password = True
        await self.db.execute(
            update(Session)
            .where(Session.user_id == user.id, Session.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        return user

    async def change_password(self, user_id: int, current_password: str, new_password: str) -> User:
        if current_password == new_password:
            raise ValueError("a nova senha deve ser diferente da senha atual")
        user = await self.db.scalar(
            select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
        )
        if user is None or not user.is_active or not await verify_password(current_password, user.password_hash):
            raise ValueError("senha atual invalida")
        user.password_hash = await hash_password(new_password)
        user.must_change_password = False
        await self.db.execute(
            update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None)).values(revoked_at=utc_now())
        )
        return user
