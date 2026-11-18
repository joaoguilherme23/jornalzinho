"""Popula exclusivamente o banco local da prévia pública com dados fictícios."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import dispose_engine, get_engine
from app.models.board import Board, BoardColumn
from app.models.membership import ProjectMember
from app.models.project import Project
from app.models.publication import ProjectPublication, PublicNews, TaskPublication
from app.models.task import Task
from app.models.user import User
from app.services.auth import AuthService

DATABASE = "jornalzinho_public_preview"
ADMIN_EMAIL = "admin@jornalzinho.example.test"
PROJECT_KEY = "JORNAL"


def password() -> str:
    credential_file = Path(os.environ.get("ADMIN_CREDENTIAL_FILE", "/run/secrets/admin_credentials"))
    try:
        value = credential_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError("credencial local ausente") from error
    if len(value.encode("utf-8")) < 12:
        raise RuntimeError("credencial local inválida")
    return value


async def get_or_create_admin(db: AsyncSession, secret: str) -> User:
    admin = await db.scalar(select(User).where(User.email == ADMIN_EMAIL).with_for_update())
    if admin is not None:
        return admin
    admin = await AuthService(db).create_user(name="Administração Jornalzinho", email=ADMIN_EMAIL, password=secret)
    admin.global_role = "admin"
    admin.must_change_password = True
    return admin


async def seed() -> None:
    if os.environ.get("PUBLIC_PREVIEW_ALLOW_SETUP") != "1" or os.environ.get("POSTGRES_DB") != DATABASE:
        raise RuntimeError("destino não autorizado")
    async with AsyncSession(get_engine(), expire_on_commit=False) as db:
        async with db.begin():
            admin = await get_or_create_admin(db, password())
            project = await db.scalar(select(Project).where(Project.key == PROJECT_KEY).with_for_update())
            if project is None:
                project = Project(
                    key=PROJECT_KEY,
                    name="Jornalzinho — demonstração",
                    description="Projeto fictício para explorar o quadro, as publicações e as solicitações.",
                    owner_id=admin.id,
                    priority="medium",
                    status="in_progress",
                    objective="Organizar a edição de demonstração do Jornalzinho.",
                )
                db.add(project)
                await db.flush()
            membership = await db.scalar(select(ProjectMember).where(ProjectMember.project_id == project.id, ProjectMember.user_id == admin.id))
            if membership is None:
                db.add(ProjectMember(project_id=project.id, user_id=admin.id, role="manager"))
            board = await db.scalar(select(Board).where(Board.project_id == project.id).with_for_update())
            if board is None:
                board = Board(project_id=project.id, name="Produção editorial")
                db.add(board)
                await db.flush()
            columns = (await db.scalars(select(BoardColumn).where(BoardColumn.board_id == board.id).order_by(BoardColumn.position))).all()
            if not columns:
                columns = [
                    BoardColumn(board_id=board.id, name="Pautas", position=0, is_done=False),
                    BoardColumn(board_id=board.id, name="Em produção", position=1, is_done=False),
                    BoardColumn(board_id=board.id, name="Revisão", position=2, is_done=False),
                    BoardColumn(board_id=board.id, name="Publicado", position=3, is_done=True),
                ]
                db.add_all(columns)
                await db.flush()
                board.default_column_id = columns[0].id
            if not await db.scalar(select(Task.id).where(Task.board_id == board.id)):
                for position, (title, description, column) in enumerate((
                    ("Definir as pautas da semana", "Exemplo fictício de uma tarefa editorial.", columns[0]),
                    ("Preparar entrevista de demonstração", "Conteúdo de exemplo, sem dados de clientes.", columns[1]),
                    ("Revisar guia de publicação", "Validação fictícia antes da publicação.", columns[2]),
                    ("Publicar boletim de boas-vindas", "Notícia fictícia visível no portal público.", columns[3]),
                ), start=1):
                    task = Task(board_id=board.id, column_id=column.id, number=position, title=title, description=description, priority="medium", task_type="task", reporter_id=admin.id, position=position)
                    db.add(task)
                    await db.flush()
                    db.add(TaskPublication(task_id=task.id, title=title, summary=description, published=True))
                project.next_task_number = 5
            if await db.get(ProjectPublication, project.id) is None:
                db.add(ProjectPublication(project_id=project.id, name="Jornalzinho em demonstração", summary="Acompanhe exemplos fictícios do trabalho editorial.", published=True))
            if not await db.scalar(select(PublicNews.id).where(PublicNews.project_id == project.id)):
                db.add(PublicNews(title="Bem-vindo ao Jornalzinho", summary="Esta é uma notícia de demonstração.", body="O Jornalzinho reúne publicações, projetos e tarefas em um espaço único. Todo o conteúdo desta instalação é fictício.", project_id=project.id, published=True, published_at=datetime.now(timezone.utc)))
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(seed())
