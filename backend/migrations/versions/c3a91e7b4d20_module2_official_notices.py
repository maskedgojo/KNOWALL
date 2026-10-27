"""Add official notices. Additive only; does not alter Module 1 tables.

Revision ID: c3a91e7b4d20
Revises: 7cfa926bd410

Notice rows reference the existing singleton society_profile. This revision
does not insert, update, or delete society, user, membership, or audit data.
"""
from alembic import op
import sqlalchemy as sa

revision = "c3a91e7b4d20"
down_revision = "7cfa926bd410"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notices",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "PUBLISHED", "ARCHIVED", name="notice_status", native_enum=False), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaces_notice_id", sa.Uuid(), sa.ForeignKey("notices.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("archived_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_notices_status"),
        sa.CheckConstraint(
            "("
            "status = 'DRAFT' AND published_at IS NULL AND published_by_user_id IS NULL "
            "AND archived_at IS NULL AND archived_by_user_id IS NULL"
            ") OR ("
            "status = 'PUBLISHED' AND published_at IS NOT NULL AND published_by_user_id IS NOT NULL "
            "AND archived_at IS NULL AND archived_by_user_id IS NULL"
            ") OR ("
            "status = 'ARCHIVED' AND archived_at IS NOT NULL AND archived_by_user_id IS NOT NULL"
            ")",
            name="ck_notices_lifecycle",
        ),
        sa.CheckConstraint(
            "replaces_notice_id IS NULL OR replaces_notice_id <> id",
            name="ck_notices_no_self_replacement",
        ),
    )
    op.create_index("ix_notices_society_id", "notices", ["society_id"])
    op.create_index("ix_notices_society_status", "notices", ["society_id", "status"])
    op.create_index("ix_notices_replaces_notice_id", "notices", ["replaces_notice_id"])
    op.create_index("ix_notices_created_by_user_id", "notices", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_notices_created_by_user_id", table_name="notices")
    op.drop_index("ix_notices_replaces_notice_id", table_name="notices")
    op.drop_index("ix_notices_society_status", table_name="notices")
    op.drop_index("ix_notices_society_id", table_name="notices")
    op.drop_table("notices")
