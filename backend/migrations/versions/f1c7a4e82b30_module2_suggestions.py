"""Add resident suggestions. Additive only.

Revision ID: f1c7a4e82b30
Revises: e4b8c2d71a05

Creates suggestions only. Does not alter Module 1 tables, notices, or
discussions, and does not insert or update existing rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "f1c7a4e82b30"
down_revision = "e4b8c2d71a05"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "suggestions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum("MAINTENANCE", "SAFETY", "AMENITIES", "COMMUNITY", "OTHER", name="suggestion_category", native_enum=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("SUBMITTED", name="suggestion_status", native_enum=False),
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('MAINTENANCE', 'SAFETY', 'AMENITIES', 'COMMUNITY', 'OTHER')",
            name="ck_suggestions_category",
        ),
        sa.CheckConstraint("status = 'SUBMITTED'", name="ck_suggestions_status"),
    )
    op.create_index("ix_suggestions_society_id", "suggestions", ["society_id"])
    op.create_index("ix_suggestions_society_created", "suggestions", ["society_id", "created_at"])
    op.create_index("ix_suggestions_created_by_user_id", "suggestions", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_suggestions_created_by_user_id", table_name="suggestions")
    op.drop_index("ix_suggestions_society_created", table_name="suggestions")
    op.drop_index("ix_suggestions_society_id", table_name="suggestions")
    op.drop_table("suggestions")
