"""Add community discussions and comments. Additive only.

Revision ID: e4b8c2d71a05
Revises: c3a91e7b4d20

Creates discussions and discussion_comments. Does not alter Module 1 tables
or the notices table, and does not insert or update existing rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "e4b8c2d71a05"
down_revision = "c3a91e7b4d20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discussions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_discussions_society_id", "discussions", ["society_id"])
    op.create_index("ix_discussions_society_updated", "discussions", ["society_id", "updated_at"])
    op.create_index("ix_discussions_created_by_user_id", "discussions", ["created_by_user_id"])
    op.create_table(
        "discussion_comments",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("discussion_id", sa.Uuid(), sa.ForeignKey("discussions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("parent_comment_id", sa.Uuid(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("discussion_id", "id", name="uq_discussion_comments_discussion_id"),
        sa.ForeignKeyConstraint(
            ["discussion_id", "parent_comment_id"],
            ["discussion_comments.discussion_id", "discussion_comments.id"],
            name="fk_discussion_comments_parent_same_discussion",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "parent_comment_id IS NULL OR parent_comment_id <> id",
            name="ck_discussion_comments_no_self_parent",
        ),
    )
    op.create_index("ix_discussion_comments_discussion_created", "discussion_comments", ["discussion_id", "created_at"])
    op.create_index("ix_discussion_comments_created_by_user_id", "discussion_comments", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_discussion_comments_created_by_user_id", table_name="discussion_comments")
    op.drop_index("ix_discussion_comments_discussion_created", table_name="discussion_comments")
    op.drop_table("discussion_comments")
    op.drop_index("ix_discussions_created_by_user_id", table_name="discussions")
    op.drop_index("ix_discussions_society_updated", table_name="discussions")
    op.drop_index("ix_discussions_society_id", table_name="discussions")
    op.drop_table("discussions")
