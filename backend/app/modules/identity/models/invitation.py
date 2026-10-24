"""Single-use household or admin invitations; tokens are stored only as hashes."""
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.extensions import db
from .user import utc_now
from .membership import ResidentCategory


class Invitation(db.Model):
    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint("expires_at > created_at", name="valid_expiration"),
        CheckConstraint("used_at IS NULL OR revoked_at IS NULL", name="not_used_and_revoked"),
        CheckConstraint("category = 'FAMILY_MEMBER' OR relationship_to_sponsor IS NULL",
                        name="relation_only_for_family"),
        CheckConstraint(
            "(category IS NULL AND sponsor_membership_id IS NULL) OR "
            "(category = 'FAMILY_MEMBER' AND sponsor_membership_id IS NOT NULL) OR "
            "(category IN ('OWNER', 'TENANT') AND sponsor_membership_id IS NULL)",
            name="invitation_category_sponsor",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flat_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("flats.id", ondelete="RESTRICT"), nullable=False, index=True)
    household_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("households.id", ondelete="RESTRICT"), nullable=True)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Nullable for compatibility with legacy invitations; all new invitations set this.
    category: Mapped[ResidentCategory | None] = mapped_column(
        SAEnum(ResidentCategory, name="invitation_category", native_enum=False, create_constraint=False), nullable=True,
    )
    sponsor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("memberships.id", ondelete="RESTRICT"), nullable=True,
    )
    # An optional inviter-provided hint, confirmed/edited by the invitee.
    relationship_to_sponsor: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    flat: Mapped["Flat"] = relationship("Flat")
    household: Mapped["Household | None"] = relationship("Household")
    invited_by: Mapped["User"] = relationship("User", foreign_keys=[invited_by_user_id])
    accepted_by: Mapped["User | None"] = relationship("User", foreign_keys=[accepted_by_user_id])
    applications: Mapped[list["MembershipApplication"]] = relationship("MembershipApplication", back_populates="invitation")
    sponsor: Mapped["Membership | None"] = relationship("Membership", foreign_keys=[sponsor_membership_id])

    @validates("invited_email")
    def normalize_email(self, key: str, value: str) -> str:
        email = value.strip().lower()
        if not email or "@" not in email:
            raise ValueError("Invitation email is required.")
        return email
