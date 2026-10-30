"""Module 4: locality profile, directory, corrections, local events, alerts. Additive only.

Revision ID: e5c1a9d3f742
Revises: d9a4f2c6b871

Creates the Module 4 tables and widens the role_assignments role column and
check to allow LOCALITY_COORDINATOR. Existing rows and Module 1-3 tables are unchanged.
"""
from alembic import op
import sqlalchemy as sa

revision = "e5c1a9d3f742"
down_revision = "d9a4f2c6b871"
branch_labels = None
depends_on = None

OLD_ROLES = "role IN ('APPLICANT', 'RESIDENT', 'COMMITTEE_MEMBER', 'SOCIETY_ADMIN', 'PLATFORM_ADMIN')"
NEW_ROLES = ("role IN ('APPLICANT', 'RESIDENT', 'COMMITTEE_MEMBER', 'SOCIETY_ADMIN', 'PLATFORM_ADMIN', "
             "'LOCALITY_COORDINATOR')")


def _enum(name, *values):
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False, length=30)


def _user(name, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _locality():
    return sa.Column("locality_id", sa.Integer(), sa.ForeignKey("locality_profiles.id", ondelete="RESTRICT"),
                     nullable=False)


def _ts(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


METHODS = ("PHONE_CALL", "SITE_VISIT", "OFFICIAL_SOURCE", "DOCUMENT", "CORRECTION_REVIEW", "DEMO_SEED")


def upgrade():
    with op.batch_alter_table("role_assignments") as batch:
        # LOCALITY_COORDINATOR is 20 characters; the column was sized for the original 16.
        batch.alter_column("role", existing_type=sa.String(16), type_=sa.String(30), existing_nullable=False)
        batch.drop_constraint(op.f("ck_role_assignments_role"), type_="check")
        batch.create_check_constraint(op.f("ck_role_assignments_role"), NEW_ROLES)

    op.create_table(
        "locality_profiles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("center_latitude", sa.Float(), nullable=False),
        sa.Column("center_longitude", sa.Float(), nullable=False),
        sa.Column("coverage_radius_m", sa.Integer(), nullable=False),
        sa.Column("stale_after_days", sa.Integer(), nullable=False),
        sa.Column("is_fictional", sa.Boolean(), nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("society_id", name="uq_locality_profiles_society"),
        sa.CheckConstraint("center_latitude BETWEEN -90 AND 90", name=op.f("ck_locality_profiles_lat")),
        sa.CheckConstraint("center_longitude BETWEEN -180 AND 180", name=op.f("ck_locality_profiles_lng")),
        sa.CheckConstraint("coverage_radius_m BETWEEN 200 AND 20000", name=op.f("ck_locality_profiles_radius")),
        sa.CheckConstraint("stale_after_days BETWEEN 7 AND 3650", name=op.f("ck_locality_profiles_stale")),
    )

    op.create_table(
        "place_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("label", sa.String(80), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("is_emergency", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "places",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("place_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("website_url", sa.String(500), nullable=True),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("data_origin", _enum("place_data_origin", "FICTIONAL_DEMO", "REAL_WORLD"), nullable=False),
        sa.Column("publication_status", _enum("place_publication_status", "ACTIVE", "ARCHIVED"), nullable=False),
        sa.Column("archived_reason", sa.String(500), nullable=True),
        sa.Column("verification_status", _enum("place_verification_status", "UNVERIFIED", "VERIFIED", "NEEDS_RECHECK"),
                  nullable=False),
        _ts("last_verified_at", nullable=True),
        _user("last_verified_by_user_id", nullable=True),
        sa.Column("last_verification_method", _enum("place_verification_method", *METHODS), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        _user("created_by_user_id", nullable=True),
        _user("updated_by_user_id", nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name=op.f("ck_places_coordinates_pair")),
        sa.CheckConstraint("verification_status <> 'VERIFIED' OR last_verified_at IS NOT NULL",
                           name=op.f("ck_places_verified_date")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_places_version")),
    )
    op.create_index("ix_places_locality_id", "places", ["locality_id"])
    op.create_index("ix_places_category_id", "places", ["category_id"])
    op.create_index("ix_places_locality_status_category", "places", ["locality_id", "publication_status", "category_id"])

    op.create_table(
        "place_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("place_id", sa.Uuid(), sa.ForeignKey("places.id", ondelete="RESTRICT"), nullable=False),
        _user("verifier_user_id", nullable=True),
        sa.Column("method", _enum("place_verification_method", *METHODS), nullable=False),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        _ts("verified_at"),
    )
    op.create_index("ix_place_verifications_place_id", "place_verifications", ["place_id"])

    op.create_table(
        "listing_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("place_id", sa.Uuid(), sa.ForeignKey("places.id", ondelete="RESTRICT"), nullable=True),
        _user("reporter_user_id"),
        sa.Column("issue_type", _enum("correction_issue", "WRONG_PHONE", "WRONG_ADDRESS", "WRONG_COORDINATES",
                                      "WRONG_NAME", "WRONG_CATEGORY", "WRONG_WEBSITE", "MOVED_OR_CLOSED",
                                      "DUPLICATE", "MISSING_SERVICE", "OTHER"), nullable=False),
        sa.Column("field", sa.String(30), nullable=True),
        sa.Column("current_value", sa.Text(), nullable=True),
        sa.Column("proposed_value", sa.Text(), nullable=True),
        sa.Column("proposed_latitude", sa.Float(), nullable=True),
        sa.Column("proposed_longitude", sa.Float(), nullable=True),
        sa.Column("proposed_category_id", sa.Integer(), sa.ForeignKey("place_categories.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("place_version", sa.Integer(), nullable=True),
        sa.Column("status", _enum("correction_status", "PENDING", "CLARIFICATION_REQUESTED", "APPROVED", "REJECTED"),
                  nullable=False),
        _user("reviewer_user_id", nullable=True),
        sa.Column("decision_reason", sa.String(1000), nullable=True),
        _ts("reviewed_at", nullable=True),
        _ts("submitted_at"), _ts("updated_at"),
        sa.CheckConstraint("(proposed_latitude IS NULL) = (proposed_longitude IS NULL)",
                           name=op.f("ck_listing_corrections_coordinates")),
        sa.CheckConstraint("place_id IS NOT NULL OR issue_type = 'MISSING_SERVICE'",
                           name=op.f("ck_listing_corrections_place")),
    )
    op.create_index("ix_listing_corrections_locality_id", "listing_corrections", ["locality_id"])
    op.create_index("ix_listing_corrections_reporter_user_id", "listing_corrections", ["reporter_user_id"])
    op.create_index("ix_listing_corrections_place_status", "listing_corrections", ["place_id", "status"])
    op.create_index("ix_listing_corrections_reporter_submitted", "listing_corrections",
                    ["reporter_user_id", "submitted_at"])

    op.create_table(
        "local_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("organizer", sa.String(160), nullable=False),
        sa.Column("venue", sa.String(160), nullable=False),
        sa.Column("category", _enum("local_event_category", "CULTURAL", "HEALTH", "CIVIC", "SPORTS", "MARKET", "OTHER"),
                  nullable=False),
        _ts("starts_at"), _ts("ends_at"),
        sa.Column("source_event_id", sa.Uuid(), sa.ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("status", _enum("local_event_status", "PENDING", "PUBLISHED", "REJECTED", "ARCHIVED"), nullable=False),
        _user("submitted_by_user_id"),
        _user("reviewer_user_id", nullable=True),
        sa.Column("decision_reason", sa.String(1000), nullable=True),
        _ts("published_at", nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_local_events_window")),
        sa.UniqueConstraint("source_event_id", name="uq_local_events_source_event"),
    )
    op.create_index("ix_local_events_locality_id", "local_events", ["locality_id"])
    op.create_index("ix_local_events_submitted_by_user_id", "local_events", ["submitted_by_user_id"])
    op.create_index("ix_local_events_locality_status_starts", "local_events", ["locality_id", "status", "starts_at"])

    op.create_table(
        "local_alerts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", _enum("local_alert_severity", "INFO", "LOW", "MEDIUM", "HIGH"), nullable=False),
        sa.Column("source_type", _enum("local_alert_source", "OFFICIAL_NOTICE", "SOCIETY", "COMMUNITY"), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=True),
        _ts("starts_at"), _ts("expires_at"),
        sa.Column("status", _enum("local_alert_status", "DRAFT", "PUBLISHED", "ARCHIVED"), nullable=False),
        _user("created_by_user_id"),
        _user("reviewer_user_id", nullable=True),
        _ts("published_at", nullable=True), _ts("archived_at", nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("expires_at > starts_at", name=op.f("ck_local_alerts_window")),
        sa.CheckConstraint("source_type <> 'OFFICIAL_NOTICE' OR source_url IS NOT NULL",
                           name=op.f("ck_local_alerts_official_source")),
    )
    op.create_index("ix_local_alerts_locality_id", "local_alerts", ["locality_id"])
    op.create_index("ix_local_alerts_created_by_user_id", "local_alerts", ["created_by_user_id"])
    op.create_index("ix_local_alerts_locality_status_expires", "local_alerts", ["locality_id", "status", "expires_at"])

    op.create_table(
        "locality_content_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("target_type", _enum("locality_report_target", "EVENT", "ALERT"), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        _user("reporter_user_id"),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", _enum("locality_report_status", "OPEN", "DISMISSED", "ACTIONED"), nullable=False),
        _user("reviewer_user_id", nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        _ts("reviewed_at", nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_locality_content_reports_locality_id", "locality_content_reports", ["locality_id"])
    op.create_index("ix_locality_content_reports_reporter_user_id", "locality_content_reports", ["reporter_user_id"])
    op.create_index("ix_locality_content_reports_target", "locality_content_reports", ["target_type", "target_id"])

    op.create_table(
        "locality_history",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _locality(),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.String(40), nullable=False),
        _user("actor_user_id", nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_locality_history_locality_id", "locality_history", ["locality_id"])
    op.create_index("ix_locality_history_entity", "locality_history", ["entity_type", "entity_id", "created_at"])


def downgrade():
    for table in ("locality_history", "locality_content_reports", "local_alerts", "local_events",
                  "listing_corrections", "place_verifications", "places", "place_categories", "locality_profiles"):
        op.drop_table(table)
    # Coordinator grants would violate the narrower check, so they are removed on downgrade.
    op.execute("DELETE FROM role_assignments WHERE role = 'LOCALITY_COORDINATOR'")
    with op.batch_alter_table("role_assignments") as batch:
        batch.drop_constraint(op.f("ck_role_assignments_role"), type_="check")
        batch.create_check_constraint(op.f("ck_role_assignments_role"), OLD_ROLES)
        batch.alter_column("role", existing_type=sa.String(30), type_=sa.String(16), existing_nullable=False)
