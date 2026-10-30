"""Bind invitation category and sponsor; store requested tenancy dates.

Revision ID: d6f160b71a25
Revises: c0a62a80f34d
"""
from alembic import op
import sqlalchemy as sa

revision = "d6f160b71a25"
down_revision = "c0a62a80f34d"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("invitations") as batch:
        batch.add_column(sa.Column("category", sa.Enum("OWNER", "TENANT", "FAMILY_MEMBER", name="invitation_category", native_enum=False, create_constraint=False), nullable=True))
        batch.add_column(sa.Column("sponsor_membership_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_invitations_sponsor_membership_id_memberships", "memberships", ["sponsor_membership_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_invitations_invitation_category_sponsor", "(category IS NULL AND sponsor_membership_id IS NULL) OR (category = 'FAMILY_MEMBER' AND sponsor_membership_id IS NOT NULL) OR (category IN ('OWNER','TENANT') AND sponsor_membership_id IS NULL)")
    with op.batch_alter_table("membership_applications") as batch:
        batch.add_column(sa.Column("requested_valid_from", sa.Date(), nullable=True))
        batch.add_column(sa.Column("requested_valid_until", sa.Date(), nullable=True))
        batch.create_check_constraint("ck_membership_applications_requested_valid_dates", "requested_valid_until IS NULL OR requested_valid_from IS NULL OR requested_valid_until >= requested_valid_from")


def downgrade():
    with op.batch_alter_table("membership_applications") as batch:
        batch.drop_constraint("ck_membership_applications_requested_valid_dates", type_="check")
        batch.drop_column("requested_valid_until")
        batch.drop_column("requested_valid_from")
    with op.batch_alter_table("invitations") as batch:
        batch.drop_constraint("ck_invitations_invitation_category_sponsor", type_="check")
        batch.drop_constraint("fk_invitations_sponsor_membership_id_memberships", type_="foreignkey")
        batch.drop_column("sponsor_membership_id")
        batch.drop_column("category")
