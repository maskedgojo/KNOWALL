"""Optional, targeted evidence requests. One private submission per request.

A member stays active while evidence is pending; any exceptional suspension must
use the existing audited membership-status operation with its own justification.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class MemberEvidenceStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class MemberEvidenceRequest(db.Model):
    __tablename__ = "member_evidence_requests"
    __table_args__ = (
        Index("ix_member_evidence_status_created", "status", "created_at"),
        Index("uq_open_member_evidence_request", "membership_id", unique=True,
              postgresql_where=text("status IN ('REQUESTED', 'SUBMITTED')"),
              sqlite_where=text("status IN ('REQUESTED', 'SUBMITTED')")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    membership_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=False, index=True)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_needed: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[MemberEvidenceStatus] = mapped_column(SAEnum(MemberEvidenceStatus, name="member_evidence_status", native_enum=False), nullable=False, default=MemberEvidenceStatus.REQUESTED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    review_note: Mapped[str | None] = mapped_column(Text)
    # Files use the same private storage/validator as residence evidence.
    original_filename: Mapped[str | None] = mapped_column(String(255))
    storage_key: Mapped[str | None] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str | None] = mapped_column(String(64))
    file_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sha256_checksum: Mapped[str | None] = mapped_column(String(64))
    # Resolved attachments are purged by a deliberate CLI command after 90 days.
    retention_delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    membership: Mapped["Membership"] = relationship("Membership")
