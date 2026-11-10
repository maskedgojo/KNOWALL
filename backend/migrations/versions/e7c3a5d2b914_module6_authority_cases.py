"""Add Module 6 authority case tables. Additive only.

Revision ID: e7c3a5d2b914
Revises: d9a4c6e1b752

Creates authority_departments, authority_jurisdiction_rules, authority_escalation_rules,
authority_officers, authority_cases, authority_case_events, authority_case_transfers,
authority_escalation_events, authority_resolution_evidence, authority_resolution_verifications,
authority_case_clarifications, authority_case_notifications and authority_metric_snapshots.
Does not alter earlier tables and inserts no rows (use backend/scripts/seed_authority_demo.py).
"""
from alembic import op
import sqlalchemy as sa

revision = "e7c3a5d2b914"
down_revision = "d9a4c6e1b752"
branch_labels = None
depends_on = None


def _uuid_id():
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def _int_id():
    return sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True)


def _user(name, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _case():
    return sa.Column("case_id", sa.Uuid(), sa.ForeignKey("authority_cases.id", ondelete="RESTRICT"), nullable=False)


def _department(name="department_id", nullable=False):
    return sa.Column(name, sa.Integer(), sa.ForeignKey("authority_departments.id", ondelete="RESTRICT"),
                     nullable=nullable)


def _time(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "authority_departments",
        _int_id(),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("contact_label", sa.String(160), nullable=False),
        _department("escalation_department_id", nullable=True),
        sa.Column("requires_resolution_proof", sa.Boolean(), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _time("created_at"),
        sa.UniqueConstraint("society_id", "code", name="uq_authority_department_code"),
    )
    op.create_index("ix_authority_departments_society_id", "authority_departments", ["society_id"])

    op.create_table(
        "authority_jurisdiction_rules",
        _int_id(),
        _department(),
        sa.Column("locality_id", sa.Integer(), sa.ForeignKey("civic_localities.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.UniqueConstraint("department_id", "locality_id", "category", name="uq_authority_jurisdiction"),
    )
    op.create_index("ix_authority_jurisdiction_rules_department_id", "authority_jurisdiction_rules", ["department_id"])
    op.create_index("ix_authority_jurisdiction_lookup", "authority_jurisdiction_rules", ["locality_id", "category"])

    op.create_table(
        "authority_escalation_rules",
        _int_id(),
        _department(),
        sa.Column("threshold_hours", sa.Integer(), nullable=False),
        sa.Column("target_label", sa.String(160), nullable=False),
        sa.UniqueConstraint("department_id", name="uq_authority_escalation_rule_department"),
        sa.CheckConstraint("threshold_hours BETWEEN 1 AND 2160", name="ck_authority_escalation_threshold"),
    )

    op.create_table(
        "authority_officers",
        _uuid_id(),
        _user("user_id"),
        _department(),
        sa.Column("title", sa.String(120), nullable=False),
        _user("granted_by_user_id", nullable=True),
        _time("granted_at"),
        _time("revoked_at", nullable=True),
    )
    op.create_index("ix_authority_officers_user_id", "authority_officers", ["user_id"])
    op.create_index("ix_authority_officers_department_id", "authority_officers", ["department_id"])
    op.create_index(
        "uq_authority_officer_active", "authority_officers", ["user_id"], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"), sqlite_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "authority_cases",
        _uuid_id(),
        sa.Column("reference", sa.String(20), nullable=False),
        sa.Column("civic_issue_id", sa.Uuid(), sa.ForeignKey("civic_issues.id", ondelete="RESTRICT"), nullable=False),
        _department(),
        sa.Column("status", sa.String(23), nullable=False),
        _user("owner_user_id", nullable=True),
        _user("created_by_user_id"),
        _time("due_at"),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("reopen_count", sa.Integer(), nullable=False),
        _time("resolved_at", nullable=True),
        _time("verification_closes_at", nullable=True),
        _time("closed_at", nullable=True),
        sa.Column("closure_basis", sa.String(24), nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False),
        _time("created_at"),
        _time("updated_at"),
        sa.UniqueConstraint("civic_issue_id", name="uq_authority_case_one_per_issue"),
        sa.UniqueConstraint("reference", name="uq_authority_case_reference"),
        sa.CheckConstraint("round >= 1", name="ck_authority_case_round"),
    )
    op.create_index("ix_authority_cases_department_status", "authority_cases", ["department_id", "status"])
    op.create_index("ix_authority_cases_due", "authority_cases", ["status", "due_at"])

    op.create_table(
        "authority_case_events",
        _uuid_id(),
        _case(),
        sa.Column("sequence", sa.Integer(), nullable=False),
        _user("actor_user_id", nullable=True),
        sa.Column("actor_kind", sa.String(11), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("public_summary", sa.Text(), nullable=False),
        _department(nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        _time("created_at"),
        sa.UniqueConstraint("case_id", "sequence", name="uq_authority_case_event_sequence"),
    )
    op.create_index("ix_authority_case_events_case_id", "authority_case_events", ["case_id"])

    op.create_table(
        "authority_case_transfers",
        _uuid_id(),
        _case(),
        _department("from_department_id"),
        _department("to_department_id"),
        sa.Column("reason", sa.Text(), nullable=False),
        _user("requested_by_user_id"),
        _time("created_at"),
        sa.CheckConstraint("from_department_id <> to_department_id", name="ck_authority_transfer_distinct"),
    )
    op.create_index("ix_authority_case_transfers_case_id", "authority_case_transfers", ["case_id"])

    op.create_table(
        "authority_escalation_events",
        _uuid_id(),
        _case(),
        sa.Column("kind", sa.String(12), nullable=False),
        _time("due_at_snapshot"),
        sa.Column("target_label", sa.String(160), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        _user("triggered_by_user_id", nullable=True),
        _time("triggered_at"),
        sa.Column("outcome", sa.String(9), nullable=False),
        _time("outcome_at", nullable=True),
        sa.UniqueConstraint("case_id", "kind", "due_at_snapshot", name="uq_authority_escalation_once_per_cycle"),
    )
    op.create_index("ix_authority_escalation_events_case_id", "authority_escalation_events", ["case_id"])

    op.create_table(
        "authority_resolution_evidence",
        _uuid_id(),
        _case(),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(10), nullable=False),
        sa.Column("caption", sa.String(200), nullable=False),
        sa.Column("storage_key", sa.String(80), nullable=False, unique=True),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("mime_type", sa.String(40), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        _user("submitted_by_user_id"),
        _time("created_at"),
    )
    op.create_index("ix_authority_resolution_evidence_case_id", "authority_resolution_evidence", ["case_id"])

    op.create_table(
        "authority_resolution_verifications",
        _uuid_id(),
        _case(),
        sa.Column("round", sa.Integer(), nullable=False),
        _user("user_id"),
        sa.Column("membership_id", sa.Uuid(), sa.ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("verdict", sa.String(9), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("photo_storage_key", sa.String(80), nullable=True, unique=True),
        sa.Column("photo_mime_type", sa.String(40), nullable=True),
        sa.Column("photo_filename", sa.String(255), nullable=True),
        _time("created_at"),
        sa.UniqueConstraint("case_id", "round", "user_id", name="uq_authority_verification_once_per_round"),
    )
    op.create_index("ix_authority_resolution_verifications_case_id", "authority_resolution_verifications",
                    ["case_id"])

    op.create_table(
        "authority_case_clarifications",
        _uuid_id(),
        _case(),
        _user("asked_by_user_id"),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("resume_status", sa.String(30), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        _user("responder_user_id", nullable=True),
        _time("asked_at"),
        _time("responded_at", nullable=True),
    )
    op.create_index("ix_authority_case_clarifications_case_id", "authority_case_clarifications", ["case_id"])

    op.create_table(
        "authority_case_notifications",
        _uuid_id(),
        _case(),
        _user("recipient_user_id"),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        _time("created_at"),
        _time("read_at", nullable=True),
    )
    op.create_index("ix_authority_case_notifications_case_id", "authority_case_notifications", ["case_id"])
    op.create_index("ix_authority_notifications_recipient", "authority_case_notifications",
                    ["recipient_user_id", "created_at"])

    op.create_table(
        "authority_metric_snapshots",
        _uuid_id(),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        _time("created_at"),
    )


def downgrade() -> None:
    for name in (
        "authority_metric_snapshots", "authority_case_notifications", "authority_case_clarifications",
        "authority_resolution_verifications", "authority_resolution_evidence", "authority_escalation_events",
        "authority_case_transfers", "authority_case_events", "authority_cases", "authority_officers",
        "authority_escalation_rules", "authority_jurisdiction_rules", "authority_departments",
    ):
        op.drop_table(name)
