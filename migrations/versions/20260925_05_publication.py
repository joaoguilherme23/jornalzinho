"""Camada explícita de publicação pública.

Revision ID: 20260925_05
Revises: 20260925_04
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260925_05"
down_revision = "20260925_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_publications",
        sa.Column("project_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_project_publications_name_not_blank"),
        sa.CheckConstraint("version >= 1", name="ck_project_publications_version_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_publications_project_id_projects", ondelete="RESTRICT"),
    )
    op.create_index("ix_project_publications_published", "project_publications", ["published"])
    op.create_table(
        "task_publications",
        sa.Column("task_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_task_publications_title_not_blank"),
        sa.CheckConstraint("version >= 1", name="ck_task_publications_version_positive"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_publications_task_id_tasks", ondelete="RESTRICT"),
    )
    op.create_index("ix_task_publications_published", "task_publications", ["published"])
    op.create_table(
        "column_publications",
        sa.Column("column_id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('planned', 'in_progress', 'waiting')", name="ck_column_publications_status"),
        sa.ForeignKeyConstraint(["column_id"], ["board_columns.id"], name="fk_column_publications_column_id_board_columns", ondelete="CASCADE"),
    )
    op.create_table(
        "public_news",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_public_news_title_not_blank"),
        sa.CheckConstraint("btrim(body) <> ''", name="ck_public_news_body_not_blank"),
        sa.CheckConstraint("version >= 1", name="ck_public_news_version_positive"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_public_news_project_id_projects", ondelete="RESTRICT"),
    )
    op.create_index("ix_public_news_published_at", "public_news", ["published", "published_at"])
    op.create_index("ix_public_news_project_id", "public_news", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_public_news_project_id", table_name="public_news")
    op.drop_index("ix_public_news_published_at", table_name="public_news")
    op.drop_table("public_news")
    op.drop_table("column_publications")
    op.drop_index("ix_task_publications_published", table_name="task_publications")
    op.drop_table("task_publications")
    op.drop_index("ix_project_publications_published", table_name="project_publications")
    op.drop_table("project_publications")
