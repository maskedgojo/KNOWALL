"""Applicant workflow. Application state is distinct from membership status."""
import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now
from .membership import ResidentCategory


class ApplicationStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MembershipApplication(db.Model):
    __tablename__ = "membership_applications"
    __table_args__ = (
        CheckConstraint("category IN ('OWNER', 'TENANT', 'FAMILY_MEMBER')", name="category"),
        CheckConstraint(
            "status IN ('DRAFT', 'PENDING', 'IN_REVIEW', 'NEEDS_CORRECTION', 'APPROVED', 'REJECTED')",
            name="status",
        ),
        CheckConstraint(
            "category = 'FAMILY_MEMBER' OR sponsor_membership_id IS NULL",
            name="sponsor_only_for_family",
        ),
        CheckConstraint(
            "category <> 'FAMILY_MEMBER' OR status = 'DRAFT' OR sponsor_membership_id IS NOT NULL",
            name="submitted_family_needs_sponsor",
        ),
        CheckConstraint("category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL",
                        name="relation_only_for_family"),
        CheckConstraint(
            "requested_valid_until IS NULL OR requested_valid_from IS NULL "
            "OR requested_valid_until >= requested_valid_from", name="requested_valid_dates",
        ),
        # Ignore previous rejected/approved applications and retain their history.
        Index(
            "uq_open_application_user_flat_category", "user_id", "flat_id", "category",
            unique=True,
            postgresql_where=text("status IN ('DRAFT','PENDING','IN_REVIEW','NEEDS_CORRECTION')"),
            sqlite_where=text("status IN ('DRAFT','PENDING','IN_REVIEW','NEEDS_CORRECTION')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    flat_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("flats.id", ondelete="RESTRICT"), nullable=False, index=True)
    household_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("households.id", ondelete="RESTRICT"), nullable=True)
    sponsor_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=True)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("invitations.id", ondelete="RESTRICT"), nullable=True, unique=True)
    resulting_membership_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=True)
    category: Mapped[ResidentCategory] = mapped_column(SAEnum(ResidentCategory, name="application_category", native_enum=False, create_constraint=False), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(SAEnum(ApplicationStatus, name="application_status", native_enum=False, create_constraint=False), nullable=False, default=ApplicationStatus.DRAFT)
    applicant_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_to_sponsor: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # Self-declaration is NOT administrative confirmation of current occupancy.
    declared_current_occupant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    requested_valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")
    flat: Mapped["Flat"] = relationship("Flat")
    household: Mapped["Household | None"] = relationship("Household")
    sponsor: Mapped["Membership | None"] = relationship("Membership", foreign_keys=[sponsor_membership_id])
    resulting_membership: Mapped["Membership | None"] = relationship("Membership", foreign_keys=[resulting_membership_id])
    invitation: Mapped["Invitation | None"] = relationship("Invitation", back_populates="applications")
    documents: Mapped[list["VerificationDocument"]] = relationship("VerificationDocument", back_populates="application")
    reviews: Mapped[list["ApplicationReview"]] = relationship("ApplicationReview", back_populates="application")
