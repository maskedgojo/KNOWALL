"""Add Module 3 society operations tables. Additive only.

Revision ID: a3d5f9c1e6b2
Revises: b4e8c1a27d90

Creates facilities, facility_blackouts, bookings, booking_events,
society_events, event_rsvps, maintenance_items, maintenance_updates,
maintenance_requests, maintenance_request_updates, development_projects and
project_milestones. Does not alter earlier tables and does not insert rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "a3d5f9c1e6b2"
down_revision = "b4e8c1a27d90"
branch_labels = None
depends_on = None


def _id():
    return sa.Column("id", sa.Uuid(), primary_key=True, nullable=False)


def _society():
    return sa.Column("society_id", sa.Integer(), sa.ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False)


def _user(name, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable)


def _ref(name, table):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(f"{table}.id", ondelete="RESTRICT"), nullable=False)


def _ts(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _enum(name, *values):
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=False)


def upgrade():
    op.create_table(
        "facilities",
        _id(), _society(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location", sa.String(length=160), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("open_minute", sa.Integer(), nullable=False),
        sa.Column("close_minute", sa.Integer(), nullable=False),
        sa.Column("slot_minutes", sa.Integer(), nullable=False),
        sa.Column("max_minutes_per_booking", sa.Integer(), nullable=False),
        sa.Column("booking_window_days", sa.Integer(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _ts("created_at"),
        sa.CheckConstraint("close_minute > open_minute", name="ck_facilities_hours"),
        sa.CheckConstraint("slot_minutes > 0", name="ck_facilities_slot"),
        sa.UniqueConstraint("society_id", "name", name="uq_facilities_society_name"),
    )
    op.create_index("ix_facilities_society_id", "facilities", ["society_id"])

    op.create_table(
        "facility_blackouts",
        _id(), _ref("facility_id", "facilities"), _ts("starts_at"), _ts("ends_at"),
        sa.Column("reason", sa.String(length=300), nullable=False),
        _user("created_by_user_id"), _ts("created_at"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_facility_blackouts_window"),
    )
    op.create_index("ix_facility_blackouts_facility_id", "facility_blackouts", ["facility_id"])

    op.create_table(
        "bookings",
        _id(), _ref("facility_id", "facilities"), _user("user_id"), _ref("membership_id", "memberships"),
        _ts("starts_at"), _ts("ends_at"),
        sa.Column("purpose", sa.String(length=300), nullable=False),
        sa.Column("status", _enum("booking_status", "PENDING", "CONFIRMED", "REJECTED", "CANCELLED"), nullable=False),
        _user("reviewer_user_id", nullable=True),
        sa.Column("decision_reason", sa.String(length=300), nullable=True),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_bookings_window"),
    )
    op.create_index("ix_bookings_facility_id", "bookings", ["facility_id"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_facility_window", "bookings", ["facility_id", "starts_at", "ends_at"])

    op.create_table(
        "booking_events",
        _id(), _ref("booking_id", "bookings"), _user("actor_user_id", nullable=True),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_booking_events_booking_id", "booking_events", ["booking_id"])

    op.create_table(
        "society_events",
        _id(), _society(), _user("organizer_user_id"),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("venue", sa.String(length=160), nullable=False),
        _ts("starts_at"), _ts("ends_at"),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("status", _enum("society_event_status", "DRAFT", "PUBLISHED", "CANCELLED", "CLOSED"), nullable=False),
        sa.Column("locality_publish_requested", sa.Boolean(), nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_society_events_window"),
        sa.CheckConstraint("capacity > 0", name="ck_society_events_capacity"),
    )
    op.create_index("ix_society_events_society_id", "society_events", ["society_id"])
    op.create_index("ix_society_events_organizer_user_id", "society_events", ["organizer_user_id"])
    op.create_index("ix_society_events_society_starts", "society_events", ["society_id", "starts_at"])

    op.create_table(
        "event_rsvps",
        _id(), _ref("event_id", "society_events"), _user("user_id"),
        sa.Column("status", _enum("event_rsvp_status", "GOING", "WAITLISTED", "CANCELLED"), nullable=False),
        sa.Column("attended", sa.Boolean(), nullable=False),
        _ts("created_at"), _ts("updated_at"),
        sa.UniqueConstraint("event_id", "user_id", name="uq_event_rsvps_one_resident"),
    )
    op.create_index("ix_event_rsvps_event_id", "event_rsvps", ["event_id"])
    op.create_index("ix_event_rsvps_user_id", "event_rsvps", ["user_id"])

    op.create_table(
        "maintenance_items",
        _id(), _society(),
        sa.Column("asset", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        _ts("scheduled_start"), _ts("scheduled_end"),
        sa.Column("status", _enum("maintenance_status", "PLANNED", "IN_PROGRESS", "RESOLVED"), nullable=False),
        _user("created_by_user_id"), _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("scheduled_end > scheduled_start", name="ck_maintenance_items_window"),
    )
    op.create_index("ix_maintenance_items_society_id", "maintenance_items", ["society_id"])
    op.create_index("ix_maintenance_items_created_by_user_id", "maintenance_items", ["created_by_user_id"])

    op.create_table(
        "maintenance_updates",
        _id(), _ref("item_id", "maintenance_items"), _user("actor_user_id"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        _ts("created_at"),
    )
    op.create_index("ix_maintenance_updates_item_id", "maintenance_updates", ["item_id"])

    op.create_table(
        "maintenance_requests",
        _id(), _society(), _ref("flat_id", "flats"), _ref("membership_id", "memberships"), _user("reporter_user_id"),
        sa.Column("issue_type", _enum(
            "maintenance_ticket_type", "LIFT", "PLUMBING", "ELECTRICAL", "COMMON_AREA", "OTHER",
        ), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location_note", sa.String(length=160), nullable=False),
        sa.Column("status", _enum(
            "maintenance_ticket_status", "REPORTED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CONFIRMED", "REOPENED",
        ), nullable=False),
        sa.Column("assignee_label", sa.String(length=120), nullable=True),
        _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_maintenance_requests_society_id", "maintenance_requests", ["society_id"])
    op.create_index("ix_maintenance_requests_flat_id", "maintenance_requests", ["flat_id"])
    op.create_index("ix_maintenance_requests_reporter", "maintenance_requests", ["reporter_user_id", "created_at"])

    op.create_table(
        "maintenance_request_updates",
        _id(), _ref("request_id", "maintenance_requests"), _user("actor_user_id"),
        sa.Column("kind", _enum("maintenance_update_kind", "STATUS", "CLARIFICATION", "FEEDBACK"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("from_status", sa.String(length=20), nullable=True),
        sa.Column("to_status", sa.String(length=20), nullable=True),
        _ts("created_at"),
    )
    op.create_index("ix_maintenance_request_updates_request_id", "maintenance_request_updates", ["request_id"])

    op.create_table(
        "development_projects",
        _id(), _society(),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", _enum("development_project_status", "PLANNED", "IN_PROGRESS", "COMPLETED"), nullable=False),
        sa.Column("budget_note", sa.String(length=300), nullable=True),
        sa.Column("expected_completion", sa.Date(), nullable=True),
        _user("created_by_user_id"), _ts("created_at"), _ts("updated_at"),
    )
    op.create_index("ix_development_projects_society_id", "development_projects", ["society_id"])
    op.create_index("ix_development_projects_created_by_user_id", "development_projects", ["created_by_user_id"])

    op.create_table(
        "project_milestones",
        _id(), _ref("project_id", "development_projects"),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", _enum("project_milestone_status", "PLANNED", "IN_PROGRESS", "COMPLETED"), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False),
        sa.Column("progress_note", sa.Text(), nullable=False),
        _user("updated_by_user_id"), _ts("created_at"), _ts("updated_at"),
        sa.CheckConstraint("percent >= 0 AND percent <= 100", name="ck_project_milestones_percent"),
    )
    op.create_index("ix_project_milestones_project_id", "project_milestones", ["project_id"])


def downgrade():
    for table in (
        "project_milestones", "development_projects", "maintenance_request_updates", "maintenance_requests",
        "maintenance_updates", "maintenance_items", "event_rsvps", "society_events", "booking_events",
        "bookings", "facility_blackouts", "facilities",
    ):
        op.drop_table(table)
