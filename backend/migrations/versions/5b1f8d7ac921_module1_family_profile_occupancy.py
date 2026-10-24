"""Optional personal profiles, declared family links and verified occupancy.

Revision ID: 5b1f8d7ac921
Revises: d6f160b71a25

Legacy family relationships and occupancy remain NULL (unknown) on purpose.
"""
from alembic import op
import sqlalchemy as sa

revision = "5b1f8d7ac921"
down_revision = "d6f160b71a25"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("date_of_birth", sa.Date(), nullable=True))
        batch.add_column(sa.Column("occupation", sa.String(100), nullable=True))
    with op.batch_alter_table("invitations") as batch:
        batch.add_column(sa.Column("relationship_to_sponsor", sa.String(24), nullable=True))
        batch.create_check_constraint("ck_invitations_relation_only_for_family", "category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL")
    with op.batch_alter_table("membership_applications") as batch:
        batch.add_column(sa.Column("relationship_to_sponsor", sa.String(24), nullable=True))
        batch.add_column(sa.Column("declared_current_occupant", sa.Boolean(), nullable=True))
        batch.create_check_constraint("ck_membership_applications_relation_only_for_family", "category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL")
    with op.batch_alter_table("memberships") as batch:
        batch.add_column(sa.Column("relationship_to_sponsor", sa.String(24), nullable=True))
        batch.add_column(sa.Column("is_current_occupant", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("occupancy_confirmed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("occupancy_confirmed_by_user_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_memberships_occupancy_confirmed_by_user_id_users", "users", ["occupancy_confirmed_by_user_id"], ["id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_memberships_relation_only_for_family", "category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL")


def downgrade():
    with op.batch_alter_table("memberships") as batch:
        batch.drop_constraint("ck_memberships_relation_only_for_family", type_="check")
        batch.drop_constraint("fk_memberships_occupancy_confirmed_by_user_id_users", type_="foreignkey")
        batch.drop_column("occupancy_confirmed_by_user_id")
        batch.drop_column("occupancy_confirmed_at")
        batch.drop_column("is_current_occupant")
        batch.drop_column("relationship_to_sponsor")
    with op.batch_alter_table("membership_applications") as batch:
        batch.drop_constraint("ck_membership_applications_relation_only_for_family", type_="check")
        batch.drop_column("declared_current_occupant")
        batch.drop_column("relationship_to_sponsor")
    with op.batch_alter_table("invitations") as batch:
        batch.drop_constraint("ck_invitations_relation_only_for_family", type_="check")
        batch.drop_column("relationship_to_sponsor")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("occupation")
        batch.drop_column("date_of_birth")
