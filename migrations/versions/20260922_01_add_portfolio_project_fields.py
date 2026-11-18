"""add portfolio metadata to projects

Revision ID: 20260922_01
Revises: 20260921_01
Create Date: 2026-09-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260922_01"
down_revision = "20260921_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("priority", sa.String(length=16), nullable=True))
    op.add_column("projects", sa.Column("status", sa.String(length=16), nullable=True))
    op.add_column("projects", sa.Column("owner_id", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("projects", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("milestone_title", sa.String(length=300), nullable=True))
    op.add_column("projects", sa.Column("milestone_due_date", sa.Date(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("links", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "projects", sa.Column("portfolio_version", sa.Integer(), server_default=sa.text("1"), nullable=False)
    )
    op.create_foreign_key("fk_projects_owner_id_users", "projects", "users", ["owner_id"], ["id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_projects_priority", "projects", "priority IS NULL OR priority IN ('low', 'medium', 'high')")
    op.create_check_constraint(
        "ck_projects_portfolio_status", "projects",
        "status IS NULL OR status IN ('planned', 'in_progress', 'waiting', 'completed')",
    )
    op.create_check_constraint("ck_projects_portfolio_version_positive", "projects", "portfolio_version >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_projects_portfolio_version_positive", "projects", type_="check")
    op.drop_constraint("ck_projects_portfolio_status", "projects", type_="check")
    op.drop_constraint("ck_projects_priority", "projects", type_="check")
    op.drop_constraint("fk_projects_owner_id_users", "projects", type_="foreignkey")
    op.drop_column("projects", "portfolio_version")
    op.drop_column("projects", "links")
    op.drop_column("projects", "milestone_due_date")
    op.drop_column("projects", "milestone_title")
    op.drop_column("projects", "objective")
    op.drop_column("projects", "due_date")
    op.drop_column("projects", "owner_id")
    op.drop_column("projects", "status")
    op.drop_column("projects", "priority")
