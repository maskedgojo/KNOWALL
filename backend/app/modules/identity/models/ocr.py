"""Stores on-demand OCR runs and extracted candidate data, not identity decisions."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from .user import utc_now


class OCRStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class OCRResult(db.Model):
    __tablename__ = "ocr_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')", name="status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("verification_documents.id", ondelete="RESTRICT"), nullable=False, index=True)
    engine_name: Mapped[str] = mapped_column(String(50), nullable=False, default="surya")
    engine_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[OCRStatus] = mapped_column(SAEnum(OCRStatus, name="ocr_status", native_enum=False, create_constraint=False), nullable=False, default=OCRStatus.PENDING)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_fields: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    comparison_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["VerificationDocument"] = relationship("VerificationDocument", back_populates="ocr_results")
