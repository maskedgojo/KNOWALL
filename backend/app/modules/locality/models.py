"""Module 4 tables: locality profile, directory, corrections, local events and alerts.

Everything is scoped to a locality, which belongs to a society. Society-private
Module 2/3 data is never copied here; a shared society event keeps only its
public fields plus a reference to the source event.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


def _enum(kind, name):
    return SAEnum(kind, name=name, native_enum=False, create_constraint=False, length=30)


def _uuid_pk():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user_fk(nullable=False, index=True):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable, index=index
    )


def _locality_fk():
    return mapped_column(
        Integer, ForeignKey("locality_profiles.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _created():
    return mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DataOrigin(str, Enum):
    FICTIONAL_DEMO = "FICTIONAL_DEMO"  # invented for the demonstration; never a real business
    REAL_WORLD = "REAL_WORLD"          # entered by a coordinator from a real, cited source


class PublicationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class VerificationStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    NEEDS_RECHECK = "NEEDS_RECHECK"


class VerificationMethod(str, Enum):
    PHONE_CALL = "PHONE_CALL"
    SITE_VISIT = "SITE_VISIT"
    OFFICIAL_SOURCE = "OFFICIAL_SOURCE"
    DOCUMENT = "DOCUMENT"
    CORRECTION_REVIEW = "CORRECTION_REVIEW"  # one reviewed field, not the whole listing
    DEMO_SEED = "DEMO_SEED"                  # simulated verification in fictional seed data


class CorrectionIssue(str, Enum):
    WRONG_PHONE = "WRONG_PHONE"
    WRONG_ADDRESS = "WRONG_ADDRESS"
    WRONG_COORDINATES = "WRONG_COORDINATES"
    WRONG_NAME = "WRONG_NAME"
    WRONG_CATEGORY = "WRONG_CATEGORY"
    WRONG_WEBSITE = "WRONG_WEBSITE"
    MOVED_OR_CLOSED = "MOVED_OR_CLOSED"
    DUPLICATE = "DUPLICATE"
    MISSING_SERVICE = "MISSING_SERVICE"
    OTHER = "OTHER"


class CorrectionStatus(str, Enum):
    PENDING = "PENDING"
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class LocalEventStatus(str, Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"


class LocalEventCategory(str, Enum):
    CULTURAL = "CULTURAL"
    HEALTH = "HEALTH"
    CIVIC = "CIVIC"
    SPORTS = "SPORTS"
    MARKET = "MARKET"
    OTHER = "OTHER"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertSourceType(str, Enum):
    OFFICIAL_NOTICE = "OFFICIAL_NOTICE"  # requires a source URL to the notice
    SOCIETY = "SOCIETY"
    COMMUNITY = "COMMUNITY"


class AlertStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ReportTarget(str, Enum):
    EVENT = "EVENT"
    ALERT = "ALERT"


class ReportStatus(str, Enum):
    OPEN = "OPEN"
    DISMISSED = "DISMISSED"
    ACTIONED = "ACTIONED"


class LocalityProfile(db.Model):
    __tablename__ = "locality_profiles"
    __table_args__ = (
        UniqueConstraint("society_id", name="uq_locality_profiles_society"),
        CheckConstraint("center_latitude BETWEEN -90 AND 90", name="lat"),
        CheckConstraint("center_longitude BETWEEN -180 AND 180", name="lng"),
        CheckConstraint("coverage_radius_m BETWEEN 200 AND 20000", name="radius"),
        CheckConstraint("stale_after_days BETWEEN 7 AND 3650", name="stale"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    center_latitude: Mapped[float] = mapped_column(Float, nullable=False)
    center_longitude: Mapped[float] = mapped_column(Float, nullable=False)
    coverage_radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    stale_after_days: Mapped[int] = mapped_column(Integer, nullable=False, default=180)
    is_fictional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class PlaceCategory(db.Model):
    """Shared category definitions; Module 5 may read these keys."""
    __tablename__ = "place_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    is_emergency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Place(db.Model):
    __tablename__ = "places"
    __table_args__ = (
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinates_pair"),
        CheckConstraint(
            "verification_status <> 'VERIFIED' OR last_verified_at IS NOT NULL", name="verified_date"
        ),
        CheckConstraint("version >= 1", name="version"),
        Index("ix_places_locality_status_category", "locality_id", "publication_status", "category_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("place_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data_origin: Mapped[DataOrigin] = mapped_column(_enum(DataOrigin, "place_data_origin"), nullable=False)
    publication_status: Mapped[PublicationStatus] = mapped_column(
        _enum(PublicationStatus, "place_publication_status"), nullable=False, default=PublicationStatus.ACTIVE
    )
    archived_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        _enum(VerificationStatus, "place_verification_status"), nullable=False, default=VerificationStatus.UNVERIFIED
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    last_verification_method: Mapped[VerificationMethod | None] = mapped_column(
        _enum(VerificationMethod, "place_verification_method"), nullable=True
    )
    # Bumped on every change; corrections remember it to detect edits made after submission.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class PlaceVerification(db.Model):
    """Append-only verification log."""
    __tablename__ = "place_verifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    place_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("places.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    verifier_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    method: Mapped[VerificationMethod] = mapped_column(
        _enum(VerificationMethod, "place_verification_method"), nullable=False
    )
    # "LISTING" for a whole-record check, or the single field a correction review confirmed.
    scope: Mapped[str] = mapped_column(String(30), nullable=False, default="LISTING")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime] = _created()


class ListingCorrection(db.Model):
    __tablename__ = "listing_corrections"
    __table_args__ = (
        CheckConstraint(
            "(proposed_latitude IS NULL) = (proposed_longitude IS NULL)", name="coordinates"
        ),
        CheckConstraint(
            "place_id IS NOT NULL OR issue_type = 'MISSING_SERVICE'", name="place"
        ),
        Index("ix_listing_corrections_place_status", "place_id", "status"),
        Index("ix_listing_corrections_reporter_submitted", "reporter_user_id", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    place_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("places.id", ondelete="RESTRICT"), nullable=True
    )
    reporter_user_id: Mapped[uuid.UUID] = _user_fk()
    issue_type: Mapped[CorrectionIssue] = mapped_column(_enum(CorrectionIssue, "correction_issue"), nullable=False)
    field: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # Snapshot of the published value when submitted; approval refuses if it has since changed.
    current_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    proposed_category_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("place_categories.id", ondelete="RESTRICT"), nullable=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    place_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[CorrectionStatus] = mapped_column(
        _enum(CorrectionStatus, "correction_status"), nullable=False, default=CorrectionStatus.PENDING
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class LocalEvent(db.Model):
    __tablename__ = "local_events"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="window"),
        UniqueConstraint("source_event_id", name="uq_local_events_source_event"),
        Index("ix_local_events_locality_status_starts", "locality_id", "status", "starts_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    organizer: Mapped[str] = mapped_column(String(160), nullable=False)
    venue: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[LocalEventCategory] = mapped_column(
        _enum(LocalEventCategory, "local_event_category"), nullable=False, default=LocalEventCategory.OTHER
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set only when a Module 3 society event that opted in is shared.
    source_event_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("society_events.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[LocalEventStatus] = mapped_column(
        _enum(LocalEventStatus, "local_event_status"), nullable=False, default=LocalEventStatus.PENDING
    )
    submitted_by_user_id: Mapped[uuid.UUID] = _user_fk()
    reviewer_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    decision_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class LocalAlert(db.Model):
    __tablename__ = "local_alerts"
    __table_args__ = (
        CheckConstraint("expires_at > starts_at", name="window"),
        CheckConstraint(
            "source_type <> 'OFFICIAL_NOTICE' OR source_url IS NOT NULL", name="official_source"
        ),
        Index("ix_local_alerts_locality_status_expires", "locality_id", "status", "expires_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(_enum(AlertSeverity, "local_alert_severity"), nullable=False)
    source_type: Mapped[AlertSourceType] = mapped_column(_enum(AlertSourceType, "local_alert_source"), nullable=False)
    source_label: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        _enum(AlertStatus, "local_alert_status"), nullable=False, default=AlertStatus.DRAFT
    )
    created_by_user_id: Mapped[uuid.UUID] = _user_fk()
    reviewer_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class LocalityContentReport(db.Model):
    """A resident flag on published locality content, reviewed by a coordinator."""
    __tablename__ = "locality_content_reports"
    __table_args__ = (Index("ix_locality_content_reports_target", "target_type", "target_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    target_type: Mapped[ReportTarget] = mapped_column(_enum(ReportTarget, "locality_report_target"), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reporter_user_id: Mapped[uuid.UUID] = _user_fk()
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "locality_report_status"), nullable=False, default=ReportStatus.OPEN
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created()


class LocalityHistory(db.Model):
    """Append-only change and decision history for every locality record."""
    __tablename__ = "locality_history"
    __table_args__ = (Index("ix_locality_history_entity", "entity_type", "entity_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = _locality_fk()
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    # {"field": [old, new]} for edits; decision context for reviews.
    changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _created()
