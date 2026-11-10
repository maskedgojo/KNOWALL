"""Add Module 5 civic issue tables. Additive only.

Revision ID: d9a4c6e1b752
Revises: c7e2b4a91f30

Creates civic_localities, civic_issues, civic_issue_evidence, civic_issue_supports,
civic_duplicate_links, civic_issue_transitions, civic_priority_snapshots,
civic_issue_reports and civic_issue_handoffs. Does not alter earlier tables and
inserts no rows (use backend/scripts/seed_civic_demo.py for demo data).

NOTE: if another module's migration also revises c7e2b4a91f30, Alembic will report
two heads. Resolve with `flask db merge heads` after the team agrees on ordering.
"""
from alembic import op
import sqlalchemy as sa

revision = "d9a4c6e1b752"
down_revision = "c7e2b4a91f30"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def _user(name, nullable=False, index=True):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable, index=index)


def _issue(name="issue_id", index=True):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("civic_issues.id", ondelete="RESTRICT"), nullable=False, index=index)


def _created():
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "civic_localities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("center_lat", sa.Float(), nullable=False),
        sa.Column("center_lon", sa.Float(), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("society_id", "name", name="uq_civic_localities_society_name"),
        sa.CheckConstraint("center_lat BETWEEN -90 AND 90 AND center_lon BETWEEN -180 AND 180", name="ck_civic_locality_center"),
        sa.CheckConstraint("radius_m > 0", name="ck_civic_locality_radius"),
    )
    op.create_index("ix_civic_localities_society_id", "civic_localities", ["society_id"])

    op.create_table(
        "civic_issues",
        _id(),
        sa.Column("locality_id", sa.Integer(), sa.ForeignKey("civic_localities.id", ondelete="RESTRICT"), nullable=False),
        _user("creator_id", index=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("address_hint", sa.String(160), nullable=False),
        sa.Column("privacy", sa.String(12), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_civic_issue_geo"),
    )
    op.create_index("ix_civic_issues_locality_state", "civic_issues", ["locality_id", "state"])
    op.create_index("ix_civic_issues_creator", "civic_issues", ["creator_id", "created_at"])
    op.create_index("ix_civic_issues_geo", "civic_issues", ["latitude", "longitude"])

    op.create_table(
        "civic_issue_evidence",
        _id(), _issue(), _user("uploaded_by_user_id", index=False),
        sa.Column("visibility", sa.String(10), nullable=False),
        sa.Column("caption", sa.String(200), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        _created(),
    )

    op.create_table(
        "civic_issue_supports",
        _id(), _issue(), _user("user_id"), _created(),
        sa.UniqueConstraint("issue_id", "user_id", name="uq_civic_support_one_per_user"),
    )

    op.create_table(
        "civic_duplicate_links",
        _id(), _issue("canonical_issue_id"), _issue("duplicate_issue_id", index=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        _user("linked_by_user_id", index=False),
        _created(),
        sa.UniqueConstraint("duplicate_issue_id", name="uq_civic_duplicate_links_once"),
        sa.CheckConstraint("canonical_issue_id <> duplicate_issue_id", name="ck_civic_duplicate_distinct"),
    )

    op.create_table(
        "civic_issue_transitions",
        _id(), _issue(), _user("actor_user_id", nullable=True, index=False),
        sa.Column("actor_role", sa.String(10), nullable=False),
        sa.Column("from_state", sa.String(30), nullable=True),
        sa.Column("to_state", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _created(),
    )

    op.create_table(
        "civic_priority_snapshots",
        _id(), _issue(),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("band", sa.String(10), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        _created(),
    )

    op.create_table(
        "civic_issue_reports",
        _id(), _issue(), _user("reporter_id", index=False),
        sa.Column("concern_type", sa.String(20), nullable=False),
        sa.Column("concern", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("disposition", sa.String(20), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=False),
        sa.Column("original_description", sa.Text(), nullable=True),
        _user("resolved_by_user_id", nullable=True, index=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.UniqueConstraint("issue_id", "reporter_id", name="uq_civic_report_one_per_resident"),
    )
    op.create_index("ix_civic_issue_reports_status", "civic_issue_reports", ["status"])

    op.create_table(
        "civic_issue_handoffs",
        _id(), _issue("canonical_issue_id"), _user("routed_by_user_id", index=False),
        sa.Column("routed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("routing_status", sa.String(20), nullable=False),
        sa.Column("authority_case_id", sa.String(64), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("canonical_issue_id", name="uq_civic_handoff_one_per_issue"),
    )


def downgrade() -> None:
    for table in (
        "civic_issue_handoffs", "civic_issue_reports", "civic_priority_snapshots", "civic_issue_transitions",
        "civic_duplicate_links", "civic_issue_supports", "civic_issue_evidence", "civic_issues", "civic_localities",
    ):
        op.drop_table(table)
