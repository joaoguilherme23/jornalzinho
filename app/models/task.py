"""Modelos de tasks, comentários e histórico."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.board import Board, BoardColumn
    from app.models.label import Label
    from app.models.user import User


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(str, Enum):
    TASK = "task"
    BUG = "bug"
    IMPROVEMENT = "improvement"


class Task(Base):
    """Card ordenado em uma coluna do board."""

    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="ck_tasks_title_not_blank"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="ck_tasks_priority"),
        CheckConstraint("type IN ('task', 'bug', 'improvement')", name="ck_tasks_type"),
        CheckConstraint("number >= 1", name="ck_tasks_number_positive"),
        CheckConstraint("position >= 0", name="ck_tasks_position_nonnegative"),
        CheckConstraint("version >= 1", name="ck_tasks_version_positive"),
        UniqueConstraint("board_id", "number", name="uq_tasks_board_id_number"),
        Index("ix_tasks_board_id_column_id_position", "board_id", "column_id", "position"),
        Index("ix_tasks_assignee_id", "assignee_id"),
        Index("ix_tasks_reporter_id", "reporter_id"),
        # A FK composta materializa a regra de que a coluna pertence ao board.
        ForeignKeyConstraint(
            ["board_id", "column_id"],
            ["board_columns.board_id", "board_columns.id"],
            name="fk_tasks_column_belongs_to_board",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", name="fk_tasks_board_id_boards", ondelete="RESTRICT"), nullable=False
    )
    column_id: Mapped[int] = mapped_column(Integer, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[TaskPriority] = mapped_column(String(16), nullable=False, server_default=TaskPriority.MEDIUM.value)
    task_type: Mapped[TaskType] = mapped_column("type", String(16), nullable=False, server_default=TaskType.TASK.value)
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_tasks_reporter_id_users", ondelete="RESTRICT"), nullable=False
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_tasks_assignee_id_users", ondelete="RESTRICT"), nullable=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __mapper_args__ = {"version_id_col": version}

    board: Mapped[Board] = relationship(
        back_populates="tasks", foreign_keys=[board_id], overlaps="column,tasks"
    )
    column: Mapped[BoardColumn] = relationship(
        back_populates="tasks",
        foreign_keys="[Task.board_id, Task.column_id]",
        primaryjoin="and_(Task.board_id == BoardColumn.board_id, Task.column_id == BoardColumn.id)",
        overlaps="board,tasks",
    )
    reporter: Mapped[User] = relationship(back_populates="reported_tasks", foreign_keys=[reporter_id])
    assignee: Mapped[User | None] = relationship(back_populates="assigned_tasks", foreign_keys=[assignee_id])
    comments: Mapped[list[Comment]] = relationship(back_populates="task")
    history: Mapped[list[TaskHistory]] = relationship(
        back_populates="task", order_by="TaskHistory.created_at"
    )
    labels: Mapped[list[Label]] = relationship(
        secondary="task_labels", back_populates="tasks", order_by="Label.name"
    )


class Comment(Base):
    """Comentário humano associado a uma task."""

    __tablename__ = "comments"
    __table_args__ = (
        CheckConstraint("btrim(body) <> ''", name="ck_comments_body_not_blank"),
        Index("ix_comments_task_id_created_at", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", name="fk_comments_task_id_tasks", ondelete="RESTRICT"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_comments_author_id_users", ondelete="RESTRICT"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="comments")
    author: Mapped[User] = relationship(back_populates="comments")


class TaskHistory(Base):
    """Registro imutável de eventos e valores de uma task."""

    __tablename__ = "task_history"
    __table_args__ = (
        CheckConstraint("btrim(event) <> ''", name="ck_task_history_event_not_blank"),
        Index("ix_task_history_task_id_created_at", "task_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", name="fk_task_history_task_id_tasks", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_task_history_actor_id_users", ondelete="RESTRICT"), nullable=False
    )
    event: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    task: Mapped[Task] = relationship(back_populates="history")
    actor: Mapped[User] = relationship(back_populates="task_history")
