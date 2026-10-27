"""Module 3 tables. Society-private; nothing here is published to the locality."""
import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


def _enum(kind, name):
    return SAEnum(kind, name=name, native_enum=False, create_constraint=False)


def _uuid_pk():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user_fk(nullable=False, index=True):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable, index=index
    )


def _society_fk():
    return mapped_column(Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True)


class BookingStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"
    CLOSED = "CLOSED"


class RsvpStatus(str, Enum):
    GOING = "GOING"
    WAITLISTED = "WAITLISTED"
    CANCELLED = "CANCELLED"


class MaintenanceStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"


class TicketType(str, Enum):
    LIFT = "LIFT"
    PLUMBING = "PLUMBING"
    ELECTRICAL = "ELECTRICAL"
    COMMON_AREA = "COMMON_AREA"
    OTHER = "OTHER"


class TicketStatus(str, Enum):
    REPORTED = "REPORTED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CONFIRMED = "CONFIRMED"
    REOPENED = "REOPENED"


class TicketUpdateKind(str, Enum):
    STATUS = "STATUS"
    CLARIFICATION = "CLARIFICATION"
    FEEDBACK = "FEEDBACK"


class PhotoSubject(str, Enum):
    MAINTENANCE_REQUEST = "MAINTENANCE_REQUEST"
    PROJECT_MILESTONE = "PROJECT_MILESTONE"


class ProjectStatus(str, Enum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


# ---------------------------------------------------------------- amenities

class Facility(db.Model):
    __tablename__ = "facilities"
    __table_args__ = (
        CheckConstraint("close_minute > open_minute", name="ck_facilities_hours"),
        CheckConstraint("slot_minutes > 0", name="ck_facilities_slot"),
        UniqueConstraint("society_id", "name", name="uq_facilities_society_name"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    society_id: Mapped[int] = _society_fk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    location: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Society local time, minutes after midnight (e.g. 360 = 06:00).
    open_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    close_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    slot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_minutes_per_booking: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    booking_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Optional usage cap: upcoming PENDING/CONFIRMED bookings one resident may hold here. None = no cap.
    max_upcoming_per_resident: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class FacilityBlackout(db.Model):
    __tablename__ = "facility_blackouts"
    __table_args__ = (CheckConstraint("ends_at > starts_at", name="ck_facility_blackouts_window"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Booking(db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_bookings_window"),
        Index("ix_bookings_facility_window", "facility_id", "starts_at", "ends_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    facility_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("facilities.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    purpose: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(_enum(BookingStatus, "booking_status"), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    decision_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BookingEvent(db.Model):
    """Append-only booking history."""
    __tablename__ = "booking_events"

    id: Mapped[uuid.UUID] = _uuid_pk()
    booking_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ---------------------------------------------------------------- events

class SocietyEvent(db.Model):
    __tablename__ = "society_events"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_society_events_window"),
        CheckConstraint("capacity > 0", name="ck_society_events_capacity"),
        Index("ix_society_events_society_starts", "society_id", "starts_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    society_id: Mapped[int] = _society_fk()
    organizer_user_id: Mapped[uuid.UUID] = _user_fk()
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    venue: Mapped[str] = mapped_column(String(160), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    volunteer_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[EventStatus] = mapped_column(_enum(EventStatus, "society_event_status"), nullable=False)
    # Opt-in flag only; Module 4 decides whether anything becomes locality content.
    locality_publish_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class EventRsvp(db.Model):
    __tablename__ = "event_rsvps"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_rsvps_one_resident"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    status: Mapped[RsvpStatus] = mapped_column(_enum(RsvpStatus, "event_rsvp_status"), nullable=False)
    attended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class EventVolunteer(db.Model):
    __tablename__ = "event_volunteers"
    __table_args__ = (UniqueConstraint("event_id", "user_id", name="uq_event_volunteers_one_resident"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = _user_fk()
    note: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class EventUpdate(db.Model):
    """Append-only organiser announcements on an event (venue change, reminder)."""
    __tablename__ = "event_updates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ---------------------------------------------------------------- maintenance

class MaintenanceItem(db.Model):
    """Admin-published planned maintenance or downtime notice."""
    __tablename__ = "maintenance_items"
    __table_args__ = (CheckConstraint("scheduled_end > scheduled_start", name="ck_maintenance_items_window"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    society_id: Mapped[int] = _society_fk()
    asset: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[MaintenanceStatus] = mapped_column(_enum(MaintenanceStatus, "maintenance_status"), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MaintenanceUpdate(db.Model):
    __tablename__ = "maintenance_updates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("maintenance_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MaintenanceRequest(db.Model):
    """Resident ticket for an internal fault. Private to reporter and admins."""
    __tablename__ = "maintenance_requests"
    __table_args__ = (Index("ix_maintenance_requests_reporter", "reporter_user_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    society_id: Mapped[int] = _society_fk()
    flat_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("flats.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False
    )
    reporter_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    issue_type: Mapped[TicketType] = mapped_column(_enum(TicketType, "maintenance_ticket_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location_note: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    status: Mapped[TicketStatus] = mapped_column(_enum(TicketStatus, "maintenance_ticket_status"), nullable=False)
    assignee_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MaintenanceRequestUpdate(db.Model):
    """Append-only ticket timeline."""
    __tablename__ = "maintenance_request_updates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("maintenance_requests.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    kind: Mapped[TicketUpdateKind] = mapped_column(_enum(TicketUpdateKind, "maintenance_update_kind"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ---------------------------------------------------------------- development

class DevelopmentProject(db.Model):
    __tablename__ = "development_projects"

    id: Mapped[uuid.UUID] = _uuid_pk()
    society_id: Mapped[int] = _society_fk()
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus, "development_project_status"), nullable=False)
    budget_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    expected_completion: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProjectMilestone(db.Model):
    __tablename__ = "project_milestones"
    __table_args__ = (CheckConstraint("percent >= 0 AND percent <= 100", name="ck_project_milestones_percent"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("development_projects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(_enum(ProjectStatus, "project_milestone_status"), nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


# ---------------------------------------------------------------- photos

class OperationPhoto(db.Model):
    """Private PNG/JPEG evidence on a ticket or milestone. Files live in OCR_PRIVATE_DIR, never /static.

    Who may view depends on the subject: ticket photos follow ticket privacy;
    milestone photos are visible to eligible residents.
    """
    __tablename__ = "operation_photos"
    __table_args__ = (Index("ix_operation_photos_subject", "subject_type", "subject_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    subject_type: Mapped[PhotoSubject] = mapped_column(_enum(PhotoSubject, "operation_photo_subject"), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    uploaded_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    uploaded_by_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    caption: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
