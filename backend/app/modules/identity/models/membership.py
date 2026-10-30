"""Memberships independently connect accounts with a household and resident category."""
import uuid
from datetime import date, datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ResidentCategory(str, Enum):
    OWNER = "OWNER"
    TENANT = "TENANT"
    FAMILY_MEMBER = "FAMILY_MEMBER"


RELATIONSHIPS_TO_SPONSOR = frozenset({"SPOUSE", "CHILD", "PARENT", "SIBLING", "GRANDPARENT", "GRANDCHILD", "OTHER"})


class MembershipStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class Membership(db.Model):
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="valid_dates"),
        CheckConstraint(
            "(category = 'FAMILY_MEMBER' AND sponsor_membership_id IS NOT NULL) "
            "OR (category <> 'FAMILY_MEMBER' AND sponsor_membership_id IS NULL)",
            name="sponsor_only_for_family",
        ),
        CheckConstraint(
            "sponsor_membership_id IS NULL OR sponsor_membership_id <> id", name="no_self_sponsorship"
        ),
        CheckConstraint("category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL",
                        name="relation_only_for_family"),
        # Preserve history; prohibit only duplicate CURRENT active associations.
        Index(
            "uq_membership_active_user_household_category",
            "user_id", "household_id", "category",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
            sqlite_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    household_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("households.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sponsor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    category: Mapped[ResidentCategory] = mapped_column(
        SAEnum(ResidentCategory, name="resident_category", native_enum=False, create_constraint=True),
        nullable=False,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SAEnum(MembershipStatus, name="membership_status", native_enum=False, create_constraint=True),
        default=MembershipStatus.ACTIVE,
        nullable=False,
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    relationship_to_sponsor: Mapped[str | None] = mapped_column(String(24), nullable=True)
    declared_current_occupant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # None means unknown / not reviewed, never automatically infer residency.
    is_current_occupant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    occupancy_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    occupancy_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="memberships", foreign_keys=[user_id])
    household: Mapped["Household"] = relationship("Household", back_populates="memberships")
    sponsor: Mapped["Membership | None"] = relationship(
        "Membership", back_populates="dependents", remote_side="Membership.id",
        foreign_keys=[sponsor_membership_id],
    )
    dependents: Mapped[list["Membership"]] = relationship(
        "Membership", back_populates="sponsor", foreign_keys=[sponsor_membership_id]
    )
