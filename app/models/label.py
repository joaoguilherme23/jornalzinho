"""Etiquetas de projeto e associacao de cards."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.task import Task


class TaskLabel(Base):
    __tablename__ = "task_labels"
    __table_args__ = (Index("ix_task_labels_label_id", "label_id"),)

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", name="fk_task_labels_task_id_tasks", ondelete="CASCADE"), primary_key=True
    )
    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", name="fk_task_labels_label_id_labels", ondelete="RESTRICT"), primary_key=True
    )


class Label(Base):
    __tablename__ = "labels"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="ck_labels_name_not_blank"),
        CheckConstraint("color IN ('teal', 'blue', 'purple', 'orange', 'red', 'gray')", name="ck_labels_color"),
        UniqueConstraint("project_id", "normalized_name", name="uq_labels_project_id_normalized_name"),
        Index("ix_labels_project_id_archived_name", "project_id", "is_archived", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", name="fk_labels_project_id_projects", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False, server_default="gray")
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    project: Mapped[Project] = relationship()
    tasks: Mapped[list[Task]] = relationship(secondary="task_labels", back_populates="labels")
