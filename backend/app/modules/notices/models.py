"""Society-wide official notices.

Published text, including expiry, is immutable. Expiry hides a notice from
residents without archiving it. Archive is a separate terminal state.
"""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db
from app.modules.identity.models.user import utc_now


class NoticeStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class Notice(db.Model):
    __tablename__ = "notices"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')",
            name="ck_notices_status",
        ),
        CheckConstraint(
            "("
            "status = 'DRAFT' AND published_at IS NULL AND published_by_user_id IS NULL "
            "AND archived_at IS NULL AND archived_by_user_id IS NULL"
            ") OR ("
            "status = 'PUBLISHED' AND published_at IS NOT NULL AND published_by_user_id IS NOT NULL "
            "AND archived_at IS NULL AND archived_by_user_id IS NULL"
            ") OR ("
            "status = 'ARCHIVED' AND archived_at IS NOT NULL AND archived_by_user_id IS NOT NULL"
            ")",
            name="ck_notices_lifecycle",
        ),
        CheckConstraint(
            "replaces_notice_id IS NULL OR replaces_notice_id <> id",
            name="ck_notices_no_self_replacement",
        ),
        Index("ix_notices_society_status", "society_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    society_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("society_profile.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NoticeStatus] = mapped_column(
        SAEnum(NoticeStatus, name="notice_status", native_enum=False, create_constraint=False),
        nullable=False,
        default=NoticeStatus.DRAFT,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaces_notice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("notices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
