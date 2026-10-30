"""Module 2 admin actions: hide discussions, decide proposals, handle disputes. Additive only.

Revision ID: d9a4f2c6b871
Revises: c7e2b4a91f30

Adds nullable moderation/decision/handling columns to discussions, proposals
and disputes, and widens the proposal and dispute status checks. Existing rows
keep SUBMITTED status and stay visible; nothing is deleted or rewritten.
"""
from alembic import op
import sqlalchemy as sa

revision = "d9a4f2c6b871"
down_revision = "c7e2b4a91f30"
branch_labels = None
depends_on = None

# Existing check names were doubled by the metadata naming convention; op.f() keeps them exact.
PROPOSAL_CHECK = "ck_proposals_ck_proposals_status"
DISPUTE_CHECK = "ck_disputes_ck_disputes_status"


def upgrade():
    with op.batch_alter_table("discussions") as batch:
        batch.add_column(sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("hidden_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("hidden_reason", sa.String(length=500), nullable=True))
        batch.create_foreign_key(
            op.f("fk_discussions_hidden_by_user_id_users"), "users",
            ["hidden_by_user_id"], ["id"], ondelete="RESTRICT",
        )

    with op.batch_alter_table("proposals") as batch:
        batch.add_column(sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("decided_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("decision_note", sa.String(length=1000), nullable=True))
        batch.create_foreign_key(
            op.f("fk_proposals_decided_by_user_id_users"), "users",
            ["decided_by_user_id"], ["id"], ondelete="RESTRICT",
        )
        batch.drop_constraint(op.f(PROPOSAL_CHECK), type_="check")
        batch.create_check_constraint(op.f(PROPOSAL_CHECK), "status IN ('SUBMITTED', 'APPROVED', 'REJECTED')")

    with op.batch_alter_table("disputes") as batch:
        batch.add_column(sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("handled_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("admin_response", sa.Text(), nullable=True))
        batch.create_foreign_key(
            op.f("fk_disputes_handled_by_user_id_users"), "users",
            ["handled_by_user_id"], ["id"], ondelete="RESTRICT",
        )
        batch.drop_constraint(op.f(DISPUTE_CHECK), type_="check")
        batch.create_check_constraint(op.f(DISPUTE_CHECK), "status IN ('SUBMITTED', 'IN_REVIEW', 'RESOLVED')")


def downgrade():
    # Rows that left SUBMITTED would violate the narrower checks; return them first.
    op.execute("UPDATE disputes SET status = 'SUBMITTED' WHERE status <> 'SUBMITTED'")
    op.execute("UPDATE proposals SET status = 'SUBMITTED' WHERE status <> 'SUBMITTED'")
    with op.batch_alter_table("disputes") as batch:
        batch.drop_constraint(op.f(DISPUTE_CHECK), type_="check")
        batch.create_check_constraint(op.f(DISPUTE_CHECK), "status = 'SUBMITTED'")
        batch.drop_constraint(op.f("fk_disputes_handled_by_user_id_users"), type_="foreignkey")
        batch.drop_column("admin_response")
        batch.drop_column("handled_by_user_id")
        batch.drop_column("status_changed_at")
    with op.batch_alter_table("proposals") as batch:
        batch.drop_constraint(op.f(PROPOSAL_CHECK), type_="check")
        batch.create_check_constraint(op.f(PROPOSAL_CHECK), "status = 'SUBMITTED'")
        batch.drop_constraint(op.f("fk_proposals_decided_by_user_id_users"), type_="foreignkey")
        batch.drop_column("decision_note")
        batch.drop_column("decided_by_user_id")
        batch.drop_column("decided_at")
    with op.batch_alter_table("discussions") as batch:
        batch.drop_constraint(op.f("fk_discussions_hidden_by_user_id_users"), type_="foreignkey")
        batch.drop_column("hidden_reason")
        batch.drop_column("hidden_by_user_id")
        batch.drop_column("hidden_at")
