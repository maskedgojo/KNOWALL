"""Add informal polls, private disputes, and proposals. Additive only.

Revision ID: b4e8c1a27d90
Revises: f1c7a4e82b30

Creates polls, poll_options, poll_votes, disputes, and proposals.
Does not alter earlier tables and does not insert rows. Proposals have no ballot table.
"""
from alembic import op
import sqlalchemy as sa

revision = "b4e8c1a27d90"
down_revision = "f1c7a4e82b30"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "polls",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("question", sa.String(length=200), nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closes_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("closes_at > opens_at", name="ck_polls_window"),
    )
    op.create_index("ix_polls_society_id", "polls", ["society_id"])
    op.create_index("ix_polls_society_opens", "polls", ["society_id", "opens_at"])
    op.create_index("ix_polls_created_by_user_id", "polls", ["created_by_user_id"])
    op.create_table(
        "poll_options",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("poll_id", sa.Uuid(), sa.ForeignKey("polls.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("poll_id", "id", name="uq_poll_options_poll_id"),
        sa.UniqueConstraint("poll_id", "position", name="uq_poll_options_position"),
    )
    op.create_index("ix_poll_options_poll_id", "poll_options", ["poll_id"])
    op.create_table(
        "poll_votes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("poll_id", sa.Uuid(), sa.ForeignKey("polls.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("option_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("poll_id", "user_id", name="uq_poll_votes_one_resident"),
        sa.ForeignKeyConstraint(
            ["poll_id", "option_id"],
            ["poll_options.poll_id", "poll_options.id"],
            name="fk_poll_votes_option_same_poll",
            ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "disputes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("SUBMITTED", name="dispute_status", native_enum=False), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'SUBMITTED'", name="ck_disputes_status"),
    )
    op.create_index("ix_disputes_society_id", "disputes", ["society_id"])
    op.create_index("ix_disputes_created_by_user_id", "disputes", ["created_by_user_id"])
    op.create_index("ix_disputes_owner_created", "disputes", ["created_by_user_id", "created_at"])
    op.create_table(
        "proposals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("status", sa.Enum("SUBMITTED", name="proposal_status", native_enum=False), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status = 'SUBMITTED'", name="ck_proposals_status"),
    )
    op.create_index("ix_proposals_society_id", "proposals", ["society_id"])
    op.create_index("ix_proposals_society_created", "proposals", ["society_id", "created_at"])
    op.create_index("ix_proposals_created_by_user_id", "proposals", ["created_by_user_id"])


def downgrade():
    op.drop_index("ix_proposals_created_by_user_id", table_name="proposals")
    op.drop_index("ix_proposals_society_created", table_name="proposals")
    op.drop_index("ix_proposals_society_id", table_name="proposals")
    op.drop_table("proposals")
    op.drop_index("ix_disputes_owner_created", table_name="disputes")
    op.drop_index("ix_disputes_created_by_user_id", table_name="disputes")
    op.drop_index("ix_disputes_society_id", table_name="disputes")
    op.drop_table("disputes")
    op.drop_table("poll_votes")
    op.drop_index("ix_poll_options_poll_id", table_name="poll_options")
    op.drop_table("poll_options")
    op.drop_index("ix_polls_created_by_user_id", table_name="polls")
    op.drop_index("ix_polls_society_opens", table_name="polls")
    op.drop_index("ix_polls_society_id", table_name="polls")
    op.drop_table("polls")
