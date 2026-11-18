"""Conserva hashes rotacionados para revogacao concorrente de sessoes.

Revision ID: 20260929_01
Revises: 20260925_06
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_01"
down_revision = "20260925_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "retired_refresh_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name="pk_retired_refresh_tokens"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_retired_refresh_tokens_sha256"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name="fk_retired_refresh_tokens_session_id", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_retired_refresh_tokens_session_id", "retired_refresh_tokens", ["session_id"])
    op.create_index("ix_retired_refresh_tokens_expires_at", "retired_refresh_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_retired_refresh_tokens_expires_at", table_name="retired_refresh_tokens")
    op.drop_index("ix_retired_refresh_tokens_session_id", table_name="retired_refresh_tokens")
    op.drop_table("retired_refresh_tokens")
