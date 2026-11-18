"""add project labels and task associations

Revision ID: 20260923_02
Revises: 20260923_01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260923_02"
down_revision = "20260923_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "labels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("normalized_name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=False, server_default="gray"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_labels_name_not_blank"),
        sa.CheckConstraint("color IN ('teal', 'blue', 'purple', 'orange', 'red', 'gray')", name="ck_labels_color"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_labels_project_id_projects", ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "normalized_name", name="uq_labels_project_id_normalized_name"),
    )
    op.create_index("ix_labels_project_id_archived_name", "labels", ["project_id", "is_archived", "name"])
    op.create_table(
        "task_labels",
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("label_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_labels_task_id_tasks", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["label_id"], ["labels.id"], name="fk_task_labels_label_id_labels", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("task_id", "label_id"),
    )
    op.create_index("ix_task_labels_label_id", "task_labels", ["label_id"])


def downgrade() -> None:
    op.drop_index("ix_task_labels_label_id", table_name="task_labels")
    op.drop_table("task_labels")
    op.drop_index("ix_labels_project_id_archived_name", table_name="labels")
    op.drop_table("labels")
