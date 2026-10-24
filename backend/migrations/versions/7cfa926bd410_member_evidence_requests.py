"""Add exceptional member evidence requests, no new mandatory family review.

Revision ID: 7cfa926bd410
Revises: 5b1f8d7ac921

Legacy family applications remain exactly as they are. No data backfill,
retroactive activation, or destructive change to invitation history.
"""
from alembic import op
import sqlalchemy as sa

revision = "7cfa926bd410"
down_revision = "5b1f8d7ac921"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("memberships") as batch:
        batch.add_column(sa.Column("declared_current_occupant", sa.Boolean(), nullable=True))
    op.create_table("member_evidence_requests",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_needed", sa.String(length=500), nullable=False),
        sa.Column("status", sa.Enum("REQUESTED", "SUBMITTED", "ACCEPTED", "REJECTED", "CANCELLED", name="member_evidence_status", native_enum=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("review_note", sa.Text()),
        sa.Column("original_filename", sa.String(length=255)),
        sa.Column("storage_key", sa.String(length=500), unique=True),
        sa.Column("mime_type", sa.String(length=64)),
        sa.Column("file_size_bytes", sa.Integer()),
        sa.Column("sha256_checksum", sa.String(length=64)),
        sa.Column("retention_delete_after", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_member_evidence_requests_membership_id", "member_evidence_requests", ["membership_id"])
    op.create_index("ix_member_evidence_status_created", "member_evidence_requests", ["status", "created_at"])
    op.create_index("uq_open_member_evidence_request", "member_evidence_requests", ["membership_id"],
                    unique=True, postgresql_where=sa.text("status IN ('REQUESTED', 'SUBMITTED')"),
                    sqlite_where=sa.text("status IN ('REQUESTED', 'SUBMITTED')"))


def downgrade():
    op.drop_index("uq_open_member_evidence_request", table_name="member_evidence_requests")
    op.drop_index("ix_member_evidence_status_created", table_name="member_evidence_requests")
    op.drop_index("ix_member_evidence_requests_membership_id", table_name="member_evidence_requests")
    op.drop_table("member_evidence_requests")
    with op.batch_alter_table("memberships") as batch:
        batch.drop_column("declared_current_occupant")
