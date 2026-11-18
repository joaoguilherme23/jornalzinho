"""add users roles, memberships and administrative audit

Revision ID: 20260923_01
Revises: 20260922_01
Create Date: 2026-09-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260923_01"
down_revision = "20260922_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("global_role", sa.String(length=16), server_default="user", nullable=False))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_check_constraint("ck_users_global_role", "users", "global_role IN ('admin', 'user')")
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('manager', 'member', 'viewer')", name="ck_project_members_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_project_members_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_project_members_project_id_projects", ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
    )
    op.create_index("ix_project_members_user_project", "project_members", ["user_id", "project_id"])
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("subject_user_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("source", sa.String(length=16), server_default="api", nullable=False),
        sa.Column("old_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], name="fk_admin_audit_logs_actor_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["subject_user_id"], ["users.id"], name="fk_admin_audit_logs_subject_user_id_users", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_admin_audit_logs_project_id_projects", ondelete="RESTRICT"),
    )


def downgrade() -> None:
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_project_members_user_project", table_name="project_members")
    op.drop_table("project_members")
    op.drop_constraint("ck_users_global_role", "users", type_="check")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "global_role")
