"""support anonymous public change requests

Revision ID: 20260925_04
Revises: 20260923_03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260925_04"
down_revision = "20260923_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("change_requests", "requester_id", nullable=True)
    op.add_column(
        "change_requests",
        sa.Column("origin", sa.String(length=16), nullable=False, server_default="internal"),
    )
    op.add_column("change_requests", sa.Column("contact", sa.String(length=320)))
    op.add_column("change_requests", sa.Column("protocol", sa.String(length=64)))
    op.add_column("change_requests", sa.Column("public_key_hash", sa.String(length=64)))
    op.add_column(
        "change_requests", sa.Column("public_idempotency_hash", sa.String(length=64))
    )
    op.add_column(
        "change_requests", sa.Column("public_payload_hash", sa.String(length=64))
    )
    op.create_check_constraint(
        "ck_change_requests_origin",
        "change_requests",
        "origin IN ('internal','public')",
    )
    op.create_unique_constraint("uq_change_requests_protocol", "change_requests", ["protocol"])
    op.create_unique_constraint(
        "uq_change_requests_public_idempotency",
        "change_requests",
        ["public_idempotency_hash"],
    )
    op.create_index("ix_change_requests_protocol", "change_requests", ["protocol"])
    op.create_table(
        "public_request_rate_limits",
        sa.Column("network_hash", sa.String(length=64), primary_key=True),
        sa.Column(
            "window_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint("request_count >= 1", name="ck_public_request_rate_limit_count"),
    )
def downgrade() -> None:
    op.drop_table("public_request_rate_limits")
    op.drop_index("ix_change_requests_protocol", table_name="change_requests")
    op.drop_constraint(
        "uq_change_requests_public_idempotency", "change_requests", type_="unique"
    )
    op.drop_constraint("uq_change_requests_protocol", "change_requests", type_="unique")
    op.drop_constraint("ck_change_requests_origin", "change_requests", type_="check")
    op.drop_column("change_requests", "public_payload_hash")
    op.drop_column("change_requests", "public_idempotency_hash")
    op.drop_column("change_requests", "public_key_hash")
    op.drop_column("change_requests", "protocol")
    op.drop_column("change_requests", "contact")
    op.drop_column("change_requests", "origin")
    # A revisao anterior exige autoria interna; dados anonimos nao podem ser
    # representados depois do downgrade e seus anexos caem por cascade.
    op.execute("DELETE FROM change_requests WHERE requester_id IS NULL")
    op.alter_column("change_requests", "requester_id", nullable=False)
