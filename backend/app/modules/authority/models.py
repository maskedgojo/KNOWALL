"""Module 6 tables: authority cases that start from a Module 5 handoff.

Every department and official here is SIMULATED for the demo. No real
government body participates, and nothing is sent to one.

Module 6 owns the case status. Module 5 keeps the civic issue, its support and
its history; this module never edits them (it only calls
`civic.handoff.acknowledge_handoff` once at intake).

Append-only tables (`authority_case_events`, `authority_case_transfers`,
`authority_resolution_evidence`, `authority_resolution_verifications`) are
protected by a session guard in `service.py`: updates and deletes are refused.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON, Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, Uuid, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


def _enum(kind, name):
    return SAEnum(kind, name=name, native_enum=False, create_constraint=False)


def _uuid_pk():
    return mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _user_fk(nullable=False, index=False):
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable, index=index
    )


def _case_fk():
    return mapped_column(
        Uuid(as_uuid=True), ForeignKey("authority_cases.id", ondelete="RESTRICT"), nullable=False, index=True
    )


def _department_fk(nullable=False, index=True):
    return mapped_column(
        Integer, ForeignKey("authority_departments.id", ondelete="RESTRICT"), nullable=nullable, index=index
    )


def _created():
    return mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class CaseStatus(str, Enum):
    ROUTED = "ROUTED"                                    # with a department, awaiting acceptance
    ACKNOWLEDGED = "ACKNOWLEDGED"                        # department accepted the case
    CLARIFICATION_REQUESTED = "CLARIFICATION_REQUESTED"  # waiting on the reporter
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"                                # official claims fixed; community verification open
    REOPENED = "REOPENED"                                # claimed fix rejected; same case continues
    CLOSED = "CLOSED"                                    # closed after verification (terminal)


class ActorKind(str, Enum):
    OFFICIAL = "OFFICIAL"        # simulated department official
    COORDINATOR = "COORDINATOR"  # society coordinator (shared admin grant)
    RESIDENT = "RESIDENT"
    SYSTEM = "SYSTEM"            # periodic job or automatic rule


class EvidenceType(str, Enum):
    PROGRESS = "PROGRESS"
    RESOLUTION = "RESOLUTION"


class Verdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"


class EscalationKind(str, Enum):
    AUTO_OVERDUE = "AUTO_OVERDUE"
    MANUAL = "MANUAL"


class EscalationOutcome(str, Enum):
    OPEN = "OPEN"
    RESPONDED = "RESPONDED"  # department posted an update after the escalation
    CLOSED = "CLOSED"        # case resolved/closed before a response


class ClosureBasis(str, Enum):
    COMMUNITY_VERIFIED = "COMMUNITY_VERIFIED"    # confirmation threshold reached
    WINDOW_MAJORITY = "WINDOW_MAJORITY"          # window ended with more confirmations than disputes
    COORDINATOR_AFTER_WINDOW = "COORDINATOR_AFTER_WINDOW"  # window ended with no votes; coordinator closed


class ClarificationStatus(str, Enum):
    OPEN = "OPEN"
    ANSWERED = "ANSWERED"


class Department(db.Model):
    """Simulated department. `is_demo` is always true in V1 and is shown on every screen."""
    __tablename__ = "authority_departments"
    __table_args__ = (UniqueConstraint("society_id", "code", name="uq_authority_department_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contact_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")  # fictional routing desk
    escalation_department_id: Mapped[int | None] = _department_fk(nullable=True, index=False)
    requires_resolution_proof: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = _created()


class JurisdictionRule(db.Model):
    """Which civic categories, in which locality, a department accepts. Lower `priority` wins at intake."""
    __tablename__ = "authority_jurisdiction_rules"
    __table_args__ = (
        UniqueConstraint("department_id", "locality_id", "category", name="uq_authority_jurisdiction"),
        Index("ix_authority_jurisdiction_lookup", "locality_id", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = _department_fk()
    locality_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("civic_localities.id", ondelete="RESTRICT"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(20), nullable=False)  # civic IssueCategory value
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class EscalationRule(db.Model):
    """Demo SLA: a case is overdue `threshold_hours` after intake (or after a revised timeline)."""
    __tablename__ = "authority_escalation_rules"
    __table_args__ = (
        UniqueConstraint("department_id", name="uq_authority_escalation_rule_department"),
        CheckConstraint("threshold_hours BETWEEN 1 AND 2160", name="ck_authority_escalation_threshold"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    department_id: Mapped[int] = _department_fk(index=False)
    threshold_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    target_label: Mapped[str] = mapped_column(String(160), nullable=False)  # who is notified, e.g. "Ward Office (demo)"


class AuthorityOfficer(db.Model):
    """A verified account acting as a SIMULATED official for exactly one department."""
    __tablename__ = "authority_officers"
    __table_args__ = (
        Index(
            "uq_authority_officer_active", "user_id", unique=True,
            postgresql_where=text("revoked_at IS NULL"), sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk(index=True)
    department_id: Mapped[int] = _department_fk()
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="Demo official")
    granted_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    granted_at: Mapped[datetime] = _created()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthorityCase(db.Model):
    """One case per canonical civic issue. Reopening continues the same case (new `round`)."""
    __tablename__ = "authority_cases"
    __table_args__ = (
        UniqueConstraint("civic_issue_id", name="uq_authority_case_one_per_issue"),
        UniqueConstraint("reference", name="uq_authority_case_reference"),
        Index("ix_authority_cases_department_status", "department_id", "status"),
        Index("ix_authority_cases_due", "status", "due_at"),
        CheckConstraint("round >= 1", name="ck_authority_case_round"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    reference: Mapped[str] = mapped_column(String(20), nullable=False)
    civic_issue_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("civic_issues.id", ondelete="RESTRICT"), nullable=False
    )
    department_id: Mapped[int] = _department_fk(index=False)
    status: Mapped[CaseStatus] = mapped_column(_enum(CaseStatus, "authority_case_status"), nullable=False)
    owner_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)  # official who accepted it
    created_by_user_id: Mapped[uuid.UUID] = _user_fk()
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reopen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closure_basis: Mapped[ClosureBasis | None] = mapped_column(
        _enum(ClosureBasis, "authority_closure_basis"), nullable=True
    )
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # last event sequence
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class CaseEvent(db.Model):
    """Append-only case history. `sequence` orders events even when timestamps tie."""
    __tablename__ = "authority_case_events"
    __table_args__ = (UniqueConstraint("case_id", "sequence", name="uq_authority_case_event_sequence"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    actor_kind: Mapped[ActorKind] = mapped_column(_enum(ActorKind, "authority_actor_kind"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    public_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")  # resident-facing text
    department_id: Mapped[int | None] = _department_fk(nullable=True, index=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = _created()


class CaseTransfer(db.Model):
    """Append-only reassignment record."""
    __tablename__ = "authority_case_transfers"
    __table_args__ = (
        CheckConstraint("from_department_id <> to_department_id", name="ck_authority_transfer_distinct"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    from_department_id: Mapped[int] = _department_fk(index=False)
    to_department_id: Mapped[int] = _department_fk(index=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = _created()


class EscalationEvent(db.Model):
    """One escalation per kind per due cycle, so a re-run of the periodic job never duplicates it."""
    __tablename__ = "authority_escalation_events"
    __table_args__ = (
        UniqueConstraint("case_id", "kind", "due_at_snapshot", name="uq_authority_escalation_once_per_cycle"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    kind: Mapped[EscalationKind] = mapped_column(_enum(EscalationKind, "authority_escalation_kind"), nullable=False)
    due_at_snapshot: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    triggered_by_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    triggered_at: Mapped[datetime] = _created()
    outcome: Mapped[EscalationOutcome] = mapped_column(
        _enum(EscalationOutcome, "authority_escalation_outcome"), nullable=False, default=EscalationOutcome.OPEN
    )
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ResolutionEvidence(db.Model):
    """Append-only official photo. Files live in private storage and are served by authorised routes only."""
    __tablename__ = "authority_resolution_evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_type: Mapped[EvidenceType] = mapped_column(_enum(EvidenceType, "authority_evidence_type"), nullable=False)
    caption: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(40), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    submitted_by_user_id: Mapped[uuid.UUID] = _user_fk()
    created_at: Mapped[datetime] = _created()


class ResolutionVerification(db.Model):
    """One verdict per affected resident per resolution round. Append-only."""
    __tablename__ = "authority_resolution_verifications"
    __table_args__ = (
        UniqueConstraint("case_id", "round", "user_id", name="uq_authority_verification_once_per_round"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[uuid.UUID] = _user_fk()
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False
    )
    verdict: Mapped[Verdict] = mapped_column(_enum(Verdict, "authority_verdict"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    photo_storage_key: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    photo_mime_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    photo_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = _created()


class CaseClarification(db.Model):
    """Official asks the reporter for missing details; the reporter answers once."""
    __tablename__ = "authority_case_clarifications"

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    asked_by_user_id: Mapped[uuid.UUID] = _user_fk()
    question: Mapped[str] = mapped_column(Text, nullable=False)
    resume_status: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[ClarificationStatus] = mapped_column(
        _enum(ClarificationStatus, "authority_clarification_status"), nullable=False,
        default=ClarificationStatus.OPEN,
    )
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responder_user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    asked_at: Mapped[datetime] = _created()
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseNotification(db.Model):
    """In-app notification outbox. Stands in for a shared notification service that does not exist yet."""
    __tablename__ = "authority_case_notifications"
    __table_args__ = (Index("ix_authority_notifications_recipient", "recipient_user_id", "created_at"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    case_id: Mapped[uuid.UUID] = _case_fk()
    recipient_user_id: Mapped[uuid.UUID] = _user_fk()
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)  # CASE_ASSIGNED, CASE_UPDATED, ...
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = _created()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseMetricSnapshot(db.Model):
    """Counts recorded each time the periodic job runs, for trend checks."""
    __tablename__ = "authority_metric_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    counts: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = _created()
