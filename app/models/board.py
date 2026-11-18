"""Modelos de board e de suas colunas ordenadas."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Task


class Board(Base):
    """Board único de um projeto no MVP."""

    __tablename__ = "boards"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_boards_name_not_blank"),
        UniqueConstraint("project_id", name="uq_boards_project_id"),
        # O FK é criado depois de board_columns pela migration. A dupla (id,
        # default_column_id) impede apontar para uma coluna de outro board.
        ForeignKeyConstraint(
            ["id", "default_column_id"],
            ["board_columns.board_id", "board_columns.id"],
            name="fk_boards_default_column_belongs_to_board",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", name="fk_boards_project_id_projects", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_column_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="board")
    columns: Mapped[list[BoardColumn]] = relationship(
        back_populates="board",
        foreign_keys="BoardColumn.board_id",
        order_by="BoardColumn.position",
    )
    default_column: Mapped[BoardColumn | None] = relationship(
        foreign_keys="[Board.default_column_id]",
        primaryjoin="and_(Board.id == BoardColumn.board_id, Board.default_column_id == BoardColumn.id)",
        overlaps="board,columns",
        post_update=True,
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="board", foreign_keys="Task.board_id", overlaps="column,tasks"
    )


class BoardColumn(Base):
    """Coluna editável do board, incluindo a indicação de conclusão."""

    __tablename__ = "board_columns"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_board_columns_name_not_blank"),
        CheckConstraint("position >= 0", name="ck_board_columns_position_nonnegative"),
        UniqueConstraint("board_id", "id", name="uq_board_columns_board_id_id"),
        UniqueConstraint("board_id", "name", name="uq_board_columns_board_id_name"),
        UniqueConstraint("board_id", "position", name="uq_board_columns_board_id_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(
        ForeignKey("boards.id", name="fk_board_columns_board_id_boards", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    board: Mapped[Board] = relationship(
        back_populates="columns", foreign_keys=[board_id], overlaps="default_column"
    )
    tasks: Mapped[list[Task]] = relationship(
        back_populates="column", foreign_keys="[Task.board_id, Task.column_id]", overlaps="board,tasks"
    )
