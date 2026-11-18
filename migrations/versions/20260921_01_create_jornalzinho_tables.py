"""Create Jornalzinho transactional tables.

Revision ID: 20260921_01
Revises:
Create Date: 2026-09-21 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260921_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_users_name_not_blank"),
        sa.CheckConstraint("btrim(email) <> ''", name="ck_users_email_not_blank"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_normalized"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_sessions_token_hash_sha256"),
        sa.CheckConstraint("expires_at > created_at", name="ck_sessions_expiry_after_creation"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_index("ix_sessions_user_id_expires_at", "sessions", ["user_id", "expires_at"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("legacy_app_id", sa.String(length=255), nullable=True),
        sa.Column("next_task_number", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_projects_name_not_blank"),
        sa.CheckConstraint("key ~ '^[A-Z][A-Z0-9_]{0,31}$'", name="ck_projects_key_format"),
        sa.CheckConstraint("next_task_number >= 1", name="ck_projects_next_task_number_positive"),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("key", name="uq_projects_key"),
        sa.UniqueConstraint("legacy_app_id", name="uq_projects_legacy_app_id"),
    )

    op.create_table(
        "boards",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("default_column_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_boards_name_not_blank"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_boards_project_id_projects", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_boards"),
        sa.UniqueConstraint("project_id", name="uq_boards_project_id"),
    )

    op.create_table(
        "board_columns",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_done", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_board_columns_name_not_blank"),
        sa.CheckConstraint("position >= 0", name="ck_board_columns_position_nonnegative"),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], name="fk_board_columns_board_id_boards", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_board_columns"),
        sa.UniqueConstraint("board_id", "id", name="uq_board_columns_board_id_id"),
        sa.UniqueConstraint("board_id", "name", name="uq_board_columns_board_id_name"),
        sa.UniqueConstraint("board_id", "position", name="uq_board_columns_board_id_position"),
    )
    op.create_foreign_key(
        "fk_boards_default_column_belongs_to_board",
        "boards",
        "board_columns",
        ["id", "default_column_id"],
        ["board_id", "id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("board_id", sa.Integer(), nullable=False),
        sa.Column("column_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=16), server_default=sa.text("'medium'"), nullable=False),
        sa.Column("type", sa.String(length=16), server_default=sa.text("'task'"), nullable=False),
        sa.Column("reporter_id", sa.Integer(), nullable=False),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("position", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(title) <> ''", name="ck_tasks_title_not_blank"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="ck_tasks_priority"),
        sa.CheckConstraint("type IN ('task', 'bug', 'improvement')", name="ck_tasks_type"),
        sa.CheckConstraint("number >= 1", name="ck_tasks_number_positive"),
        sa.CheckConstraint("position >= 0", name="ck_tasks_position_nonnegative"),
        sa.CheckConstraint("version >= 1", name="ck_tasks_version_positive"),
        sa.ForeignKeyConstraint(["board_id"], ["boards.id"], name="fk_tasks_board_id_boards", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["board_id", "column_id"],
            ["board_columns.board_id", "board_columns.id"],
            name="fk_tasks_column_belongs_to_board",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["reporter_id"], ["users.id"], name="fk_tasks_reporter_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], name="fk_tasks_assignee_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_tasks"),
        sa.UniqueConstraint("board_id", "number", name="uq_tasks_board_id_number"),
    )
    op.create_index("ix_tasks_board_id_column_id_position", "tasks", ["board_id", "column_id", "position"], unique=False)
    op.create_index("ix_tasks_assignee_id", "tasks", ["assignee_id"], unique=False)
    op.create_index("ix_tasks_reporter_id", "tasks", ["reporter_id"], unique=False)

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(body) <> ''", name="ck_comments_body_not_blank"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_comments_task_id_tasks", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], name="fk_comments_author_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_comments"),
    )
    op.create_index("ix_comments_task_id_created_at", "comments", ["task_id", "created_at"], unique=False)

    op.create_table(
        "task_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("event", sa.String(length=80), nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(event) <> ''", name="ck_task_history_event_not_blank"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], name="fk_task_history_task_id_tasks", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_task_history_actor_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_task_history"),
    )
    op.create_index("ix_task_history_task_id_created_at", "task_history", ["task_id", "created_at"], unique=False)

    op.create_table(
        "idempotency_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("request_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("btrim(operation) <> ''", name="ck_idempotency_requests_operation_not_blank"),
        sa.CheckConstraint("payload_hash ~ '^[0-9a-f]{64}$'", name="ck_idempotency_requests_payload_hash_sha256"),
        sa.CheckConstraint("btrim(resource_type) <> ''", name="ck_idempotency_requests_resource_type_not_blank"),
        sa.CheckConstraint("resource_id > 0", name="ck_idempotency_requests_resource_id_positive"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_idempotency_requests_user_id_users", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_idempotency_requests"),
        sa.UniqueConstraint("user_id", "operation", "request_key", name="uq_idempotency_requests_user_operation_key"),
    )
    op.create_index("ix_idempotency_requests_user_id_created_at", "idempotency_requests", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_idempotency_requests_user_id_created_at", table_name="idempotency_requests")
    op.drop_table("idempotency_requests")
    op.drop_index("ix_task_history_task_id_created_at", table_name="task_history")
    op.drop_table("task_history")
    op.drop_index("ix_comments_task_id_created_at", table_name="comments")
    op.drop_table("comments")
    op.drop_index("ix_tasks_reporter_id", table_name="tasks")
    op.drop_index("ix_tasks_assignee_id", table_name="tasks")
    op.drop_index("ix_tasks_board_id_column_id_position", table_name="tasks")
    op.drop_table("tasks")
    op.drop_constraint("fk_boards_default_column_belongs_to_board", "boards", type_="foreignkey")
    op.drop_table("board_columns")
    op.drop_table("boards")
    op.drop_table("projects")
    op.drop_index("ix_sessions_user_id_expires_at", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
