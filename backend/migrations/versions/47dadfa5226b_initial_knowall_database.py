"""Initial KNOWALL database

Revision ID: 47dadfa5226b
Revises:
Create Date: 2026-10-21 21:51:23.011133
"""
from alembic import op
import sqlalchemy as sa


# Revision identifiers used by Alembic.
revision = "47dadfa5226b"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "society_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("locality", sa.String(length=100), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.CheckConstraint("id = 1", name=op.f("ck_society_profile_single_society_row")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_society_profile")),
    )

    op.create_table(
        "towers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=10), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_towers")),
        sa.UniqueConstraint("name", name=op.f("uq_towers_name")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "account_status",
            sa.Enum(
                "ACTIVE", "SUSPENDED", "DISABLED",
                name="account_status", native_enum=False, create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "account_status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name=op.f("ck_users_account_status"),
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "flats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tower_id", sa.Uuid(), nullable=False),
        sa.Column("flat_number", sa.String(length=16), nullable=False),
        sa.Column("floor_number", sa.Integer(), nullable=False),
        sa.CheckConstraint("floor_number >= 0", name=op.f("ck_flats_nonnegative_floor")),
        sa.ForeignKeyConstraint(
            ["tower_id"], ["towers.id"],
            name=op.f("fk_flats_tower_id_towers"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flats")),
        sa.UniqueConstraint("tower_id", "flat_number", name="tower_flat_number"),
    )
    with op.batch_alter_table("flats", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_flats_tower_id"), ["tower_id"], unique=False)

    op.create_table(
        "households",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["flat_id"], ["flats.id"],
            name=op.f("fk_households_flat_id_flats"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_households")),
    )
    with op.batch_alter_table("households", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_households_flat_id"), ["flat_id"], unique=False)

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("sponsor_membership_id", sa.Uuid(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "OWNER", "TENANT", "FAMILY_MEMBER",
                name="resident_category", native_enum=False, create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED",
                name="membership_status", native_enum=False, create_constraint=False,
            ),
            nullable=False,
        ),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(category = 'FAMILY_MEMBER' AND sponsor_membership_id IS NOT NULL) "
            "OR (category <> 'FAMILY_MEMBER' AND sponsor_membership_id IS NULL)",
            name=op.f("ck_memberships_sponsor_only_for_family"),
        ),
        sa.CheckConstraint(
            "category IN ('OWNER', 'TENANT', 'FAMILY_MEMBER')",
            name=op.f("ck_memberships_resident_category"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'EXPIRED', 'REVOKED')",
            name=op.f("ck_memberships_membership_status"),
        ),
        sa.CheckConstraint(
            "sponsor_membership_id IS NULL OR sponsor_membership_id <> id",
            name=op.f("ck_memberships_no_self_sponsorship"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name=op.f("ck_memberships_valid_dates"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"], ["households.id"],
            name=op.f("fk_memberships_household_id_households"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sponsor_membership_id"], ["memberships.id"],
            name=op.f("fk_memberships_sponsor_membership_id_memberships"), ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name=op.f("fk_memberships_user_id_users"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memberships")),
    )
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_memberships_household_id"), ["household_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_memberships_sponsor_membership_id"), ["sponsor_membership_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_memberships_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "uq_membership_active_user_household_category",
            ["user_id", "household_id", "category"],
            unique=True,
            postgresql_where=sa.text("status = 'ACTIVE'"),
            sqlite_where=sa.text("status = 'ACTIVE'"),
        )


def downgrade():
    with op.batch_alter_table("memberships", schema=None) as batch_op:
        batch_op.drop_index("uq_membership_active_user_household_category")
        batch_op.drop_index(batch_op.f("ix_memberships_user_id"))
        batch_op.drop_index(batch_op.f("ix_memberships_sponsor_membership_id"))
        batch_op.drop_index(batch_op.f("ix_memberships_household_id"))
    op.drop_table("memberships")

    with op.batch_alter_table("households", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_households_flat_id"))
    op.drop_table("households")

    with op.batch_alter_table("flats", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_flats_tower_id"))
    op.drop_table("flats")

    op.drop_table("users")
    op.drop_table("towers")
    op.drop_table("society_profile")
