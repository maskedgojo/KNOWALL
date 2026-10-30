"""Append-only administrator decision records for a membership application."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class ReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"


class ApplicationReview(db.Model):
    __tablename__ = "application_reviews"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('APPROVED', 'REJECTED', 'NEEDS_CORRECTION')", name="decision"
        ),
        CheckConstraint(
            "decision = 'APPROVED' OR (reason IS NOT NULL AND length(trim(reason)) > 0)",
            name="reason_for_negative_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("membership_applications.id", ondelete="RESTRICT"), nullable=False, index=True)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    decision: Mapped[ReviewDecision] = mapped_column(SAEnum(ReviewDecision, name="review_decision", native_enum=False, create_constraint=False), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    application: Mapped["MembershipApplication"] = relationship("MembershipApplication", back_populates="reviews")
    reviewer: Mapped["User"] = relationship("User")
