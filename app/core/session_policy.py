"""Prazo absoluto compartilhado por access token, refresh e cookie."""

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import Session


SESSION_MAX_AGE_SECONDS = 12 * 60 * 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def session_deadline(session: "Session") -> datetime:
    # Inclui sessoes criadas antes da politica de 12h, sem ampliar prazos menores.
    deadline = min(session.expires_at, session.created_at + timedelta(seconds=SESSION_MAX_AGE_SECONDS))
    # O PostgreSQL pode devolver timestamptz no fuso configurado da conexao.
    return deadline.astimezone(timezone.utc)
