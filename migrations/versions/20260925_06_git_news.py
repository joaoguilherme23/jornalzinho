"""Persist git commit cursors and deduplication for generated news.

Revision ID: 20260925_06
Revises: 20260925_05
Create Date: 2026-09-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260925_06"
down_revision = "20260925_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "git_news_cursors",
        sa.Column("repository_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("last_commit_sha", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(repository_id) <> ''", name="ck_git_news_cursors_repository_not_blank"),
        sa.CheckConstraint("btrim(last_commit_sha) <> ''", name="ck_git_news_cursors_sha_not_blank"),
    )
    op.create_table(
        "git_news_commits",
        sa.Column("repository_id", sa.String(length=255), primary_key=True, nullable=False),
        sa.Column("commit_sha", sa.String(length=128), primary_key=True, nullable=False),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("btrim(repository_id) <> ''", name="ck_git_news_commits_repository_not_blank"),
        sa.CheckConstraint("btrim(commit_sha) <> ''", name="ck_git_news_commits_sha_not_blank"),
        sa.ForeignKeyConstraint(
            ["news_id"], ["public_news.id"], name="fk_git_news_commits_news_id_public_news", ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_git_news_commits_repository_created", "git_news_commits", ["repository_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_git_news_commits_repository_created", table_name="git_news_commits")
    op.drop_table("git_news_commits")
    op.drop_table("git_news_cursors")
