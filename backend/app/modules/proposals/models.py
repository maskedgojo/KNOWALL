"""Proposals are not polls and do not accept votes."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


class ProposalStatus(str, Enum):
    SUBMITTED = "SUBMITTED"


class Proposal(db.Model):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint("status = 'SUBMITTED'", name="ck_proposals_status"),
        Index("ix_proposals_society_created", "society_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, name="proposal_status", native_enum=False, create_constraint=False),
        nullable=False,
        default=ProposalStatus.SUBMITTED,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
