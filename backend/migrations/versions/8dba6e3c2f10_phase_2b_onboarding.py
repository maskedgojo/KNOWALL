"""Phase 2B: invitations, onboarding applications, documents, OCR and reviews.

Revision ID: 8dba6e3c2f10
Revises: 47dadfa5226b
Create Date: 2026-10-22

Keep the original Phase 2A migration unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = "8dba6e3c2f10"
down_revision = "47dadfa5226b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("invited_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at", name=op.f("ck_invitations_valid_expiration")),
        sa.CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name=op.f("ck_invitations_not_used_and_revoked")),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], name=op.f("fk_invitations_flat_id_flats"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name=op.f("fk_invitations_household_id_households"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], name=op.f("fk_invitations_invited_by_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], name=op.f("fk_invitations_accepted_by_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_invitations_token_hash")),
    )
    op.create_index(op.f("ix_invitations_flat_id"), "invitations", ["flat_id"])
    op.create_index(op.f("ix_invitations_invited_by_user_id"), "invitations", ["invited_by_user_id"])

    op.create_table(
        "membership_applications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("flat_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=True),
        sa.Column("sponsor_membership_id", sa.Uuid(), nullable=True),
        sa.Column("invitation_id", sa.Uuid(), nullable=True),
        sa.Column("resulting_membership_id", sa.Uuid(), nullable=True),
        sa.Column("category", sa.Enum("OWNER", "TENANT", "FAMILY_MEMBER", name="application_category", native_enum=False, create_constraint=False), nullable=False),
        sa.Column("status", sa.Enum("DRAFT", "PENDING", "IN_REVIEW", "NEEDS_CORRECTION", "APPROVED", "REJECTED", name="application_status", native_enum=False, create_constraint=False), nullable=False),
        sa.Column("applicant_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("category IN ('OWNER', 'TENANT', 'FAMILY_MEMBER')", name=op.f("ck_membership_applications_category")),
        sa.CheckConstraint("status IN ('DRAFT', 'PENDING', 'IN_REVIEW', 'NEEDS_CORRECTION', 'APPROVED', 'REJECTED')", name=op.f("ck_membership_applications_status")),
        sa.CheckConstraint("category = 'FAMILY_MEMBER' OR sponsor_membership_id IS NULL", name=op.f("ck_membership_applications_sponsor_only_for_family")),
        sa.CheckConstraint("category <> 'FAMILY_MEMBER' OR status = 'DRAFT' OR sponsor_membership_id IS NOT NULL", name=op.f("ck_membership_applications_submitted_family_needs_sponsor")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_membership_applications_user_id_users"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["flat_id"], ["flats.id"], name=op.f("fk_membership_applications_flat_id_flats"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"], name=op.f("fk_membership_applications_household_id_households"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["sponsor_membership_id"], ["memberships.id"], name=op.f("fk_membership_applications_sponsor_membership_id_memberships"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"], name=op.f("fk_membership_applications_invitation_id_invitations"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resulting_membership_id"], ["memberships.id"], name=op.f("fk_membership_applications_resulting_membership_id_memberships"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_membership_applications")),
        sa.UniqueConstraint("invitation_id", name=op.f("uq_membership_applications_invitation_id")),
    )
    op.create_index(op.f("ix_membership_applications_user_id"), "membership_applications", ["user_id"])
    op.create_index(op.f("ix_membership_applications_flat_id"), "membership_applications", ["flat_id"])
    op.create_index(
        "uq_open_application_user_flat_category", "membership_applications",
        ["user_id", "flat_id", "category"], unique=True,
        postgresql_where=sa.text("status IN ('DRAFT','PENDING','IN_REVIEW','NEEDS_CORRECTION')"),
        sqlite_where=sa.text("status IN ('DRAFT','PENDING','IN_REVIEW','NEEDS_CORRECTION')"),
    )

    op.create_table(
        "verification_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.Enum("RENTAL_AGREEMENT", "OCCUPANCY_LETTER", "OTHER_RESIDENCE_EVIDENCE", name="document_type", native_enum=False, create_constraint=False), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256_checksum", sa.String(64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("document_type IN ('RENTAL_AGREEMENT', 'OCCUPANCY_LETTER', 'OTHER_RESIDENCE_EVIDENCE')", name=op.f("ck_verification_documents_document_type")),
        sa.CheckConstraint("file_size_bytes > 0 AND file_size_bytes <= 5242880", name=op.f("ck_verification_documents_file_size_limit")),
        sa.CheckConstraint("mime_type IN ('application/pdf', 'image/jpeg', 'image/png')", name=op.f("ck_verification_documents_allowed_mime_type")),
        sa.ForeignKeyConstraint(["application_id"], ["membership_applications.id"], name=op.f("fk_verification_documents_application_id_membership_applications"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], name=op.f("fk_verification_documents_uploaded_by_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_verification_documents")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_verification_documents_storage_key")),
    )
    op.create_index(op.f("ix_verification_documents_application_id"), "verification_documents", ["application_id"])

    op.create_table(
        "ocr_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("engine_name", sa.String(50), nullable=False),
        sa.Column("engine_version", sa.String(50), nullable=True),
        sa.Column("status", sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="ocr_status", native_enum=False, create_constraint=False), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extracted_fields", sa.JSON(), nullable=True),
        sa.Column("comparison_results", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')", name=op.f("ck_ocr_results_status")),
        sa.ForeignKeyConstraint(["document_id"], ["verification_documents.id"], name=op.f("fk_ocr_results_document_id_verification_documents"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ocr_results")),
    )
    op.create_index(op.f("ix_ocr_results_document_id"), "ocr_results", ["document_id"])

    op.create_table(
        "application_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("application_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_user_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.Enum("APPROVED", "REJECTED", "NEEDS_CORRECTION", name="review_decision", native_enum=False, create_constraint=False), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('APPROVED', 'REJECTED', 'NEEDS_CORRECTION')", name=op.f("ck_application_reviews_decision")),
        sa.CheckConstraint("decision = 'APPROVED' OR (reason IS NOT NULL AND length(trim(reason)) > 0)", name=op.f("ck_application_reviews_reason_for_negative_decision")),
        sa.ForeignKeyConstraint(["application_id"], ["membership_applications.id"], name=op.f("fk_application_reviews_application_id_membership_applications"), ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], name=op.f("fk_application_reviews_reviewer_user_id_users"), ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_application_reviews")),
    )
    op.create_index(op.f("ix_application_reviews_application_id"), "application_reviews", ["application_id"])
    op.create_index(op.f("ix_application_reviews_reviewer_user_id"), "application_reviews", ["reviewer_user_id"])


def downgrade():
    op.drop_index(op.f("ix_application_reviews_reviewer_user_id"), table_name="application_reviews")
    op.drop_index(op.f("ix_application_reviews_application_id"), table_name="application_reviews")
    op.drop_table("application_reviews")

    op.drop_index(op.f("ix_ocr_results_document_id"), table_name="ocr_results")
    op.drop_table("ocr_results")

    op.drop_index(op.f("ix_verification_documents_application_id"), table_name="verification_documents")
    op.drop_table("verification_documents")

    op.drop_index("uq_open_application_user_flat_category", table_name="membership_applications")
    op.drop_index(op.f("ix_membership_applications_flat_id"), table_name="membership_applications")
    op.drop_index(op.f("ix_membership_applications_user_id"), table_name="membership_applications")
    op.drop_table("membership_applications")

    op.drop_index(op.f("ix_invitations_invited_by_user_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_flat_id"), table_name="invitations")
    op.drop_table("invitations")
