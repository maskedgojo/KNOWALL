"""Module 5 tables: locality civic issues before they reach an authority.

Civic issues concern public/locality infrastructure only. Society-private
matters belong to Modules 2 and 3 and must never be stored here.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, Enum as SAEnum, Float, ForeignKey, Index, Integer, String, Text,
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


def _issue_fk():
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("civic_issues.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class IssueCategory(str, Enum):
    ROAD_DAMAGE = "ROAD_DAMAGE"
    STREETLIGHT = "STREETLIGHT"
    GARBAGE = "GARBAGE"
    DRAINAGE = "DRAINAGE"
    WATER_SUPPLY = "WATER_SUPPLY"
    FOOTPATH = "FOOTPATH"
    TRAFFIC = "TRAFFIC"
    PUBLIC_SPACE = "PUBLIC_SPACE"
    OTHER = "OTHER"


class IssueSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssuePrivacy(str, Enum):
    ANONYMOUS = "ANONYMOUS"      # other residents see "A resident"
    PUBLIC_NAME = "PUBLIC_NAME"  # other residents see the display name; never contact details


class IssueState(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    NEEDS_INFO = "NEEDS_INFO"
    VALIDATED = "VALIDATED"
    READY_FOR_ROUTING = "READY_FOR_ROUTING"
    REJECTED = "REJECTED"
    MERGED = "MERGED"        # linked to a canonical issue; history and supporters retained
    WITHDRAWN = "WITHDRAWN"  # soft delete by the reporter; history retained


class EvidenceVisibility(str, Enum):
    PRIVATE = "PRIVATE"      # reporter and moderators only (default)
    RESIDENTS = "RESIDENTS"  # any eligible resident who can view the issue


class ActorRole(str, Enum):
    REPORTER = "REPORTER"
    MODERATOR = "MODERATOR"
    SYSTEM = "SYSTEM"


class ConcernType(str, Enum):
    ABUSIVE = "ABUSIVE"
    SENSITIVE_IMAGE = "SENSITIVE_IMAGE"
    PERSONAL_INFO = "PERSONAL_INFO"
    FALSE_INFO = "FALSE_INFO"
    OFF_TOPIC = "OFF_TOPIC"
    OTHER = "OTHER"


class ReportStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ReportDisposition(str, Enum):
    DISMISSED = "DISMISSED"
    REDACTED = "REDACTED"
    CORRECTION_REQUESTED = "CORRECTION_REQUESTED"
    REMOVED = "REMOVED"


class RoutingStatus(str, Enum):
    PENDING_INTAKE = "PENDING_INTAKE"  # handed to Module 6, not yet acknowledged
    ACKNOWLEDGED = "ACKNOWLEDGED"      # Module 6 created an authority case


class CivicLocality(db.Model):
    """Coverage area for civic reporting.

    STUB until Module 4 owns the locality boundary: one row for Green Valley.
    When Module 4 lands, point this at their table instead of keeping a copy.
    """
    __tablename__ = "civic_localities"
    __table_args__ = (
        UniqueConstraint("society_id", "name", name="uq_civic_localities_society_name"),
        CheckConstraint(
            "center_lat BETWEEN -90 AND 90 AND center_lon BETWEEN -180 AND 180", name="ck_civic_locality_center"
        ),
        CheckConstraint("radius_m > 0", name="ck_civic_locality_radius"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lon: Mapped[float] = mapped_column(Float, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CivicIssue(db.Model):
    __tablename__ = "civic_issues"
    __table_args__ = (
        Index("ix_civic_issues_locality_state", "locality_id", "state"),
        Index("ix_civic_issues_creator", "creator_id", "created_at"),
        Index("ix_civic_issues_geo", "latitude", "longitude"),
        CheckConstraint("latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180", name="ck_civic_issue_geo"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    locality_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("civic_localities.id", ondelete="RESTRICT"), nullable=False
    )
    creator_id: Mapped[uuid.UUID] = _user_fk(index=False)
    category: Mapped[IssueCategory] = mapped_column(_enum(IssueCategory, "civic_issue_category"), nullable=False)
    severity: Mapped[IssueSeverity] = mapped_column(_enum(IssueSeverity, "civic_issue_severity"), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    address_hint: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    privacy: Mapped[IssuePrivacy] = mapped_column(_enum(IssuePrivacy, "civic_issue_privacy"), nullable=False)
    state: Mapped[IssueState] = mapped_column(_enum(IssueState, "civic_issue_state"), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IssueEvidence(db.Model):
    """Private PNG/JPEG evidence. Files live in OCR_PRIVATE_DIR and are served only by an authorised route."""
    __tablename__ = "civic_issue_evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    issue_id: Mapped[uuid.UUID] = _issue_fk()
    uploaded_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    visibility: Mapped[EvidenceVisibility] = mapped_column(
        _enum(EvidenceVisibility, "civic_evidence_visibility"), nullable=False, default=EvidenceVisibility.PRIVATE
    )
    caption: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IssueSupport(db.Model):
    """One support per verified account per issue, enforced by the database."""
    __tablename__ = "civic_issue_supports"
    __table_args__ = (UniqueConstraint("issue_id", "user_id", name="uq_civic_support_one_per_user"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    issue_id: Mapped[uuid.UUID] = _issue_fk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DuplicateLink(db.Model):
    """Moderator decision that `duplicate_issue_id` repeats `canonical_issue_id`. Rows are never deleted."""
    __tablename__ = "civic_duplicate_links"
    __table_args__ = (
        UniqueConstraint("duplicate_issue_id", name="uq_civic_duplicate_links_once"),
        CheckConstraint("canonical_issue_id <> duplicate_issue_id", name="ck_civic_duplicate_distinct"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    canonical_issue_id: Mapped[uuid.UUID] = _issue_fk()
    duplicate_issue_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("civic_issues.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    linked_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IssueTransition(db.Model):
    """Append-only lifecycle history."""
    __tablename__ = "civic_issue_transitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    issue_id: Mapped[uuid.UUID] = _issue_fk()
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    actor_role: Mapped[ActorRole] = mapped_column(_enum(ActorRole, "civic_actor_role"), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PrioritySnapshot(db.Model):
    """Stored copy of the transparent priority inputs at a lifecycle moment."""
    __tablename__ = "civic_priority_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    issue_id: Mapped[uuid.UUID] = _issue_fk()
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    band: Mapped[str] = mapped_column(String(10), nullable=False)
    inputs: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IssueModerationReport(db.Model):
    """A resident's abuse/sensitivity concern about an issue. One report per resident per issue."""
    __tablename__ = "civic_issue_reports"
    __table_args__ = (UniqueConstraint("issue_id", "reporter_id", name="uq_civic_report_one_per_resident"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    issue_id: Mapped[uuid.UUID] = _issue_fk()
    reporter_id: Mapped[uuid.UUID] = _user_fk(index=False)
    concern_type: Mapped[ConcernType] = mapped_column(_enum(ConcernType, "civic_concern_type"), nullable=False)
    concern: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus, "civic_report_status"), nullable=False, default=ReportStatus.OPEN, index=True
    )
    disposition: Mapped[ReportDisposition | None] = mapped_column(
        _enum(ReportDisposition, "civic_report_disposition"), nullable=True
    )
    resolution_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    original_description: Mapped[str | None] = mapped_column(Text, nullable=True)  # moderator-only, kept if redacted
    resolved_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True, index=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class IssueHandoff(db.Model):
    """Routing payload given to Module 6. `authority_case_id` is filled when Module 6 acknowledges."""
    __tablename__ = "civic_issue_handoffs"
    __table_args__ = (UniqueConstraint("canonical_issue_id", name="uq_civic_handoff_one_per_issue"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    canonical_issue_id: Mapped[uuid.UUID] = _issue_fk()
    routed_by_user_id: Mapped[uuid.UUID] = _user_fk(index=False)
    routed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    routing_status: Mapped[RoutingStatus] = mapped_column(
        _enum(RoutingStatus, "civic_routing_status"), nullable=False, default=RoutingStatus.PENDING_INTAKE
    )
    authority_case_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
