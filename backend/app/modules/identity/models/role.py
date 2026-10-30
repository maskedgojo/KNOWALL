"""Explicit V1 permission roles; owner/tenant/family are membership categories, not roles."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Index, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class PermissionRole(str, Enum):
    APPLICANT = "APPLICANT"
    RESIDENT = "RESIDENT"
    COMMITTEE_MEMBER = "COMMITTEE_MEMBER"
    SOCIETY_ADMIN = "SOCIETY_ADMIN"
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    # Module 4: maintains locality directory, corrections, events and alerts. Not a society admin.
    LOCALITY_COORDINATOR = "LOCALITY_COORDINATOR"


class RoleAssignment(db.Model):
    __tablename__ = "role_assignments"
    __table_args__ = (
        CheckConstraint(
            "role IN ('APPLICANT', 'RESIDENT', 'COMMITTEE_MEMBER', "
            "'SOCIETY_ADMIN', 'PLATFORM_ADMIN', 'LOCALITY_COORDINATOR')", name="role"
        ),
        CheckConstraint("revoked_at IS NULL OR revoked_at >= granted_at", name="valid_revocation"),
        # Keep revoked history, but allow only one current assignment of each role per user.
        Index(
            "uq_active_user_permission_role", "user_id", "role", unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Nullable only for initial bootstrap/system grants. All normal admin grants record actor ID.
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    role: Mapped[PermissionRole] = mapped_column(
        SAEnum(PermissionRole, name="permission_role", native_enum=False, create_constraint=False, length=30),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    granted_by: Mapped["User | None"] = relationship("User", foreign_keys=[granted_by_user_id])
