"""One user account per person; memberships and roles are separate records."""
import uuid
from datetime import date, datetime, timezone
from enum import Enum

from flask_login import UserMixin
from sqlalchemy import CheckConstraint, Date, DateTime, Enum as SAEnum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISABLED = "DISABLED"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            "account_status IN ('ACTIVE', 'SUSPENDED', 'DISABLED')",
            name="account_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status", native_enum=False, create_constraint=False),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    memberships: Mapped[list["Membership"]] = relationship("Membership", back_populates="user", foreign_keys="Membership.user_id")

    @property
    def is_active(self) -> bool:
        """Flask-Login must not log in suspended or disabled accounts."""
        return self.account_status == AccountStatus.ACTIVE

    def get_id(self) -> str:
        return str(self.id)

    @validates("email")
    def normalize_email(self, key: str, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValueError("A valid email address is required.")
        return normalized
