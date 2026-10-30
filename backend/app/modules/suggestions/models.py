"""Resident suggestions. Status stays SUBMITTED; no decision workflow is stored."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


class SuggestionCategory(str, Enum):
    MAINTENANCE = "MAINTENANCE"
    SAFETY = "SAFETY"
    AMENITIES = "AMENITIES"
    COMMUNITY = "COMMUNITY"
    OTHER = "OTHER"


class SuggestionStatus(str, Enum):
    SUBMITTED = "SUBMITTED"


class Suggestion(db.Model):
    __tablename__ = "suggestions"
    __table_args__ = (
        CheckConstraint(
            "category IN ('MAINTENANCE', 'SAFETY', 'AMENITIES', 'COMMUNITY', 'OTHER')",
            name="ck_suggestions_category",
        ),
        CheckConstraint("status = 'SUBMITTED'", name="ck_suggestions_status"),
        Index("ix_suggestions_society_created", "society_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[SuggestionCategory] = mapped_column(
        SAEnum(SuggestionCategory, name="suggestion_category", native_enum=False, create_constraint=False),
        nullable=False,
    )
    status: Mapped[SuggestionStatus] = mapped_column(
        SAEnum(SuggestionStatus, name="suggestion_status", native_enum=False, create_constraint=False),
        nullable=False,
        default=SuggestionStatus.SUBMITTED,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
