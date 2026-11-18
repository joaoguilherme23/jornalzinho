"""Importações centralizadas para que Alembic conheça todo o metadata."""

from app.models.base import Base
from app.models.board import Board, BoardColumn
from app.models.idempotency import IdempotencyRequest
from app.models.project import Project
from app.models.task import Comment, Task, TaskHistory, TaskPriority, TaskType
from app.models.user import RetiredRefreshToken, Session, User
from app.models.membership import ProjectMember
from app.models.audit import AdminAuditLog
from app.models.label import Label, TaskLabel
from app.models.change_request import ChangeRequest, RequestAttachment, PublicRequestRateLimit
from app.models.publication import ProjectPublication, TaskPublication, ColumnPublication, PublicNews
from app.models.git_news import GitNewsCommit, GitNewsCursor

__all__ = [
    "Base",
    "Board",
    "BoardColumn",
    "Comment",
    "IdempotencyRequest",
    "Project",
    "Session",
    "RetiredRefreshToken",
    "Task",
    "TaskHistory",
    "TaskPriority",
    "TaskType",
    "User",
    "ProjectMember",
    "AdminAuditLog",
    "Label",
    "TaskLabel",
    "ChangeRequest",
    "RequestAttachment",
    "PublicRequestRateLimit",
    "ProjectPublication",
    "TaskPublication",
    "ColumnPublication",
    "PublicNews",
    "GitNewsCommit",
    "GitNewsCursor",
]
