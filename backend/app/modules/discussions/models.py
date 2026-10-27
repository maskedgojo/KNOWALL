"""Community discussions and threaded comments.

Posts are society-wide. A comment parent must belong to the same discussion.
Reporting and moderation are not part of this model.
"""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


class Discussion(db.Model):
    __tablename__ = "discussions"
    __table_args__ = (
        Index("ix_discussions_society_updated", "society_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class DiscussionComment(db.Model):
    __tablename__ = "discussion_comments"
    __table_args__ = (
        UniqueConstraint("discussion_id", "id", name="uq_discussion_comments_discussion_id"),
        ForeignKeyConstraint(
            ["discussion_id", "parent_comment_id"],
            ["discussion_comments.discussion_id", "discussion_comments.id"],
            name="fk_discussion_comments_parent_same_discussion",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "parent_comment_id IS NULL OR parent_comment_id <> id",
            name="ck_discussion_comments_no_self_parent",
        ),
        Index("ix_discussion_comments_discussion_created", "discussion_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discussion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("discussions.id", ondelete="RESTRICT"), nullable=False
    )
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
