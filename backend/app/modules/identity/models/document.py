"""Metadata only: real document bytes are stored privately, outside public/static folders."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class DocumentType(str, Enum):
    RENTAL_AGREEMENT = "RENTAL_AGREEMENT"
    OCCUPANCY_LETTER = "OCCUPANCY_LETTER"
    OTHER_RESIDENCE_EVIDENCE = "OTHER_RESIDENCE_EVIDENCE"


class VerificationDocument(db.Model):
    __tablename__ = "verification_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('RENTAL_AGREEMENT', 'OCCUPANCY_LETTER', 'OTHER_RESIDENCE_EVIDENCE')",
            name="document_type",
        ),
        CheckConstraint("file_size_bytes > 0 AND file_size_bytes <= 5242880", name="file_size_limit"),
        CheckConstraint("mime_type IN ('application/pdf', 'image/jpeg', 'image/png')", name="allowed_mime_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("membership_applications.id", ondelete="RESTRICT"), nullable=False, index=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    document_type: Mapped[DocumentType] = mapped_column(SAEnum(DocumentType, name="document_type", native_enum=False, create_constraint=False), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    application: Mapped["MembershipApplication"] = relationship("MembershipApplication", back_populates="documents")
    uploaded_by: Mapped["User"] = relationship("User")
    ocr_results: Mapped[list["OCRResult"]] = relationship("OCRResult", back_populates="document")
