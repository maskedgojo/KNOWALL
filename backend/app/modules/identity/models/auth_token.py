"""One-time authentication tokens. Store SHA-256 hashes, never raw reset/verification links."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class AuthTokenPurpose(str, Enum):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION"
    PASSWORD_RESET = "PASSWORD_RESET"


class AuthToken(db.Model):
    __tablename__ = "auth_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET')", name="purpose"
        ),
        CheckConstraint("expires_at > created_at", name="valid_expiration"),
        CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name="not_used_and_revoked"),
        CheckConstraint("length(token_hash) = 64", name="sha256_hash_length"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purpose: Mapped[AuthTokenPurpose] = mapped_column(
        SAEnum(AuthTokenPurpose, name="auth_token_purpose", native_enum=False, create_constraint=False),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User")
