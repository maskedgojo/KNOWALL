"""Informal polls. One response per eligible resident. Not a formal ballot."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


class Poll(db.Model):
    __tablename__ = "polls"
    __table_args__ = (
        CheckConstraint("closes_at > opens_at", name="ck_polls_window"),
        Index("ix_polls_society_opens", "society_id", "opens_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(String(200), nullable=False)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class PollOption(db.Model):
    __tablename__ = "poll_options"
    __table_args__ = (
        UniqueConstraint("poll_id", "id", name="uq_poll_options_poll_id"),
        UniqueConstraint("poll_id", "position", name="uq_poll_options_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("polls.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class PollVote(db.Model):
    __tablename__ = "poll_votes"
    __table_args__ = (
        UniqueConstraint("poll_id", "user_id", name="uq_poll_votes_one_resident"),
        ForeignKeyConstraint(
            ["poll_id", "option_id"],
            ["poll_options.poll_id", "poll_options.id"],
            name="fk_poll_votes_option_same_poll",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    poll_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("polls.id", ondelete="RESTRICT"), nullable=False)
    option_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
