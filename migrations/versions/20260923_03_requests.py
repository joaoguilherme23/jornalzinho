"""add change requests and binary attachments

Revision ID: 20260923_03
Revises: 20260923_02
"""

from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "20260923_03"
down_revision = "20260923_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer()),
        sa.Column("reviewer_id", sa.Integer()),
        sa.Column("task_id", sa.Integer()),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("area", sa.String(120)),
        sa.Column("project_kind", sa.String(20), nullable=False),
        sa.Column("project_name", sa.String(200)),
        sa.Column("request_type", sa.String(20), nullable=False),
        sa.Column("type_detail", sa.String(200)),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(500)),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("example_url", sa.String(1000)),
        sa.Column("urgency", sa.String(20), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="em_avaliacao"
        ),
        sa.Column("response", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("task_id", name="uq_change_requests_task"),
        sa.CheckConstraint("length(btrim(name)) >= 2", name="ck_change_requests_name"),
        sa.CheckConstraint(
            "length(btrim(description)) >= 5", name="ck_change_requests_description"
        ),
        sa.CheckConstraint(
            "length(btrim(purpose)) >= 5", name="ck_change_requests_purpose"
        ),
        sa.CheckConstraint("version >= 1", name="ck_change_requests_version_positive"),
        sa.CheckConstraint(
            "project_kind IN ('existing','novo_projeto','outro')",
            name="ck_change_requests_project_kind",
        ),
        sa.CheckConstraint(
            "request_type IN ('correcao','dado_novo','melhoria','funcionalidade','novo_projeto','outro')",
            name="ck_change_requests_type",
        ),
        sa.CheckConstraint(
            "urgency IN ('travando','importante','seria_bom')",
            name="ck_change_requests_urgency",
        ),
        sa.CheckConstraint(
            "status IN ('em_avaliacao','ajuste','aprovado','recusado')",
            name="ck_change_requests_status",
        ),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_change_requests_requester_created",
        "change_requests",
        ["requester_id", "created_at"],
    )
    op.create_index(
        "ix_change_requests_project_status", "change_requests", ["project_id", "status"]
    )
    op.create_table(
        "request_attachments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint(
            "size > 0 AND size <= 5242880", name="ck_request_attachments_size_positive"
        ),
        sa.ForeignKeyConstraint(
            ["request_id"], ["change_requests.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_request_attachments_request", "request_attachments", ["request_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_request_attachments_request", table_name="request_attachments")
    op.drop_table("request_attachments")
    op.drop_index("ix_change_requests_project_status", table_name="change_requests")
    op.drop_index("ix_change_requests_requester_created", table_name="change_requests")
    op.drop_table("change_requests")
