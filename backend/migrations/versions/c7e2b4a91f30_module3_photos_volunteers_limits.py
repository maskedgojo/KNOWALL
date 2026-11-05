"""Module 3 additions: photo evidence, event volunteers and updates, booking caps. Additive only.

Revision ID: c7e2b4a91f30
Revises: a3d5f9c1e6b2

Adds facilities.max_upcoming_per_resident (nullable, no cap by default) and
society_events.volunteer_slots (default 0), and creates event_volunteers,
event_updates and operation_photos. Existing rows keep their behaviour.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7e2b4a91f30"
down_revision = "a3d5f9c1e6b2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("facilities") as batch:
        batch.add_column(sa.Column("max_upcoming_per_resident", sa.Integer(), nullable=True))
    with op.batch_alter_table("society_events") as batch:
        batch.add_column(sa.Column("volunteer_slots", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "event_volunteers",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_volunteers_one_resident"),
    )
    op.create_index("ix_event_volunteers_event_id", "event_volunteers", ["event_id"])
    op.create_index("ix_event_volunteers_user_id", "event_volunteers", ["user_id"])

    op.create_table(
        "event_updates",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_event_updates_event_id", "event_updates", ["event_id"])

    op.create_table(
        "operation_photos",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("subject_type", sa.Enum(
            "MAINTENANCE_REQUEST", "PROJECT_MILESTONE", name="operation_photo_subject",
            native_enum=False, create_constraint=False,
        ), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("uploaded_by_staff", sa.Boolean(), nullable=False),
        sa.Column("caption", sa.String(length=200), nullable=False),
        sa.Column("storage_key", sa.String(length=80), nullable=False),
        sa.Column("sha256_checksum", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=40), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storage_key", name="uq_operation_photos_storage_key"),
    )
    op.create_index("ix_operation_photos_subject", "operation_photos", ["subject_type", "subject_id"])


def downgrade():
    op.drop_table("operation_photos")
    op.drop_table("event_updates")
    op.drop_table("event_volunteers")
    with op.batch_alter_table("society_events") as batch:
        batch.drop_column("volunteer_slots")
    with op.batch_alter_table("facilities") as batch:
        batch.drop_column("max_upcoming_per_resident")
