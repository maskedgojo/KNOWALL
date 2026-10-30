"""Phase 2C: roles, authentication tokens and audit trail.

Revision ID: c0a62a80f34d
Revises: 8dba6e3c2f10
Create Date: 2026-10-22

Only adds tables; does not change Phase 2A or Phase 2B history.
"""
from alembic import op
import sqlalchemy as sa

revision = "c0a62a80f34d"
down_revision = "8dba6e3c2f10"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "role_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("granted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.Enum(
            "APPLICANT", "RESIDENT", "COMMITTEE_MEMBER", "SOCIETY_ADMIN", "PLATFORM_ADMIN",
            name="permission_role", native_enum=False, create_constraint=False,
        ), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('APPLICANT', 'RESIDENT', 'COMMITTEE_MEMBER', 'SOCIETY_ADMIN', 'PLATFORM_ADMIN')",
            name=op.f("ck_role_assignments_role"),
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= granted_at",
            name=op.f("ck_role_assignments_valid_revocation"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_role_assignments_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"],
            name=op.f("fk_role_assignments_granted_by_user_id_users"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_assignments")),
    )
    op.create_index(op.f("ix_role_assignments_user_id"), "role_assignments", ["user_id"])
    op.create_index(
        "uq_active_user_permission_role", "role_assignments", ["user_id", "role"],
        unique=True, postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.Enum(
            "EMAIL_VERIFICATION", "PASSWORD_RESET", name="auth_token_purpose",
            native_enum=False, create_constraint=False,
        ), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')",
            name=op.f("ck_auth_tokens_purpose"),
        ),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_auth_tokens_valid_expiration")),
        sa.CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name=op.f("ck_auth_tokens_not_used_and_revoked")),
        sa.CheckConstraint("length(token_hash) = 64", name=op.f("ck_auth_tokens_sha256_hash_length")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_tokens_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_auth_tokens_token_hash")),
    )
    op.create_index(op.f("ix_auth_tokens_user_id"), "auth_tokens", ["user_id"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name=op.f("fk_audit_logs_actor_user_id_users"), ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(op.f("ix_audit_logs_actor_user_id"), "audit_logs", ["actor_user_id"])
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])


def downgrade():
    # Destructive operation: audit and token records are deleted if you downgrade.
    op.drop_index("ix_audit_logs_entity", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_actor_user_id"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_auth_tokens_user_id"), table_name="auth_tokens")
    op.drop_table("auth_tokens")

    op.drop_index("uq_active_user_permission_role", table_name="role_assignments")
    op.drop_index(op.f("ix_role_assignments_user_id"), table_name="role_assignments")
    op.drop_table("role_assignments")
