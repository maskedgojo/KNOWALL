"""Phase 7: private evidence upload, OCR runs, extraction results, and private reads."""
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.access import has_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.models import (
    ApplicationStatus, AuditLog, DocumentType, MembershipApplication,
    OCRResult, OCRStatus, VerificationDocument,
)
from app.modules.identity.models.user import utc_now
from . import storage
from .fields import extract_fields, compare_fields


documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")
EDITABLE = {ApplicationStatus.DRAFT, ApplicationStatus.PENDING, ApplicationStatus.NEEDS_CORRECTION}


def _is_admin():
    return has_permission("identity.admin.manage")

def _visible(document):
    return document.application.user_id == current_user.id or _is_admin()


def _doc(document_id):
    document = db.session.get(VerificationDocument, document_id)
    return document if document is not None and document.deleted_at is None and _visible(document) else None


def _audit(action, obj):
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action,
        entity_type="VERIFICATION_DOCUMENT", entity_id=obj.id,
        details={"application_id": str(obj.application_id)},
    ))


def _doc_data(obj):
    return {
        "id": str(obj.id), "application_id": str(obj.application_id),
        "document_type": obj.document_type.value,
        "filename": obj.original_filename,
        "mime_type": obj.mime_type, "size_bytes": obj.file_size_bytes,
        "uploaded_at": obj.uploaded_at.isoformat(),
        "download_url": f"/api/documents/{obj.id}/file",
    }


def _ocr_data(run):
    return {
        "id": str(run.id), "document_id": str(run.document_id),
        "status": run.status.value, "engine_name": run.engine_name,
        "engine_version": run.engine_version,
        "extracted_text": run.extracted_text,
        "extracted_fields": run.extracted_fields,
        "comparison_results": run.comparison_results,
        "warnings": run.warnings or [],
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@documents_bp.post("/upload")
@login_required
def upload_document():
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify email before uploading.", 403)
    if request.mimetype != "multipart/form-data":
        return error("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    from uuid import UUID
    try:
        application_id = UUID(request.form.get("application_id", ""))
    except (ValueError, TypeError):
        return error("VALIDATION_ERROR", "Valid application_id required.", 400)
    application = db.session.get(MembershipApplication, application_id)
    if application is None or application.user_id != current_user.id:
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    if application.status not in EDITABLE:
        return error("INVALID_APPLICATION_STATE", "Cannot upload for application in this state.", 409)
    try:
        doc_type = DocumentType(request.form.get("document_type", ""))
    except ValueError:
        return error("VALIDATION_ERROR", "Valid document_type required.", 400)
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        return error("VALIDATION_ERROR", "Choose a document file.", 400)
    # Read strictly up to 5 MB + 1, independently of user-supplied size header.
    blob = incoming.stream.read(storage.MAX_FILE_BYTES + 1)
    try:
        mime = storage.validate_document(incoming.filename, blob)
    except ValueError as exc:
        return error("INVALID_DOCUMENT", str(exc), 400)
    key = None
    try:
        key, checksum = storage.write_private(current_app.config, blob, mime)
        doc = VerificationDocument(
            application_id=application.id, uploaded_by_user_id=current_user.id,
            document_type=doc_type, original_filename=(secure_filename(incoming.filename) or "document")[:255],
            storage_key=key, mime_type=mime, file_size_bytes=len(blob),
            sha256_checksum=checksum,
        )
        db.session.add(doc)
        db.session.flush()
        _audit("DOCUMENT_UPLOADED", doc)
        db.session.commit()
        return jsonify({"document": _doc_data(doc)}), 201
    except Exception:
        db.session.rollback()
        if key:
            storage.private_path(current_app.config, key).unlink(missing_ok=True)
        current_app.logger.exception("Document upload failed")
        return error("UPLOAD_FAILED", "Document could not be saved.", 503)


@documents_bp.get("/application/<uuid:application_id>")
@login_required
def documents_for_application(application_id):
    application = db.session.get(MembershipApplication, application_id)
    if application is None or (application.user_id != current_user.id and not _is_admin()):
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    documents = db.session.scalars(select(VerificationDocument)
        .where(VerificationDocument.application_id == application.id,
               VerificationDocument.deleted_at.is_(None))
        .order_by(VerificationDocument.uploaded_at.desc())).all()
    return jsonify({"documents": [_doc_data(doc) for doc in documents]}), 200


@documents_bp.get("/<uuid:document_id>")
@login_required
def document_detail(document_id):
    doc = _doc(document_id)
    if not doc:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    return jsonify({"document": _doc_data(doc)}), 200


@documents_bp.get("/<uuid:document_id>/file")
@login_required
def download_document(document_id):
    doc = _doc(document_id)
    if not doc:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    try:
        path = storage.private_path(current_app.config, doc.storage_key)
    except ValueError:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    if not path.is_file():
        return error("DOCUMENT_UNAVAILABLE", "Stored document is missing.", 404)
    response = send_file(path, mimetype="application/octet-stream", as_attachment=True,
                         download_name=doc.original_filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@documents_bp.post("/<uuid:document_id>/ocr")
@login_required
def run_ocr(document_id):
    doc = _doc(document_id)
    if not doc:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify email first.", 403)
    if (doc.application.user_id != current_user.id and not _is_admin()) or doc.application.status in (ApplicationStatus.APPROVED, ApplicationStatus.REJECTED):
        return error("INVALID_APPLICATION_STATE", "OCR is not available for this application.", 409)
    # Lock document row while claiming OCR (PostgreSQL serializes competing claims).
    db.session.execute(select(VerificationDocument.id)
                       .where(VerificationDocument.id == doc.id).with_for_update())
    latest = db.session.scalar(select(OCRResult).where(OCRResult.document_id == doc.id)
                               .order_by(OCRResult.created_at.desc(), OCRResult.id.desc()).limit(1))
    if latest and latest.status == OCRStatus.COMPLETED:
        db.session.rollback()
        return jsonify({"ocr": _ocr_data(latest), "reused": True}), 200
    if latest and latest.status == OCRStatus.PROCESSING:
        db.session.rollback()
        return error("OCR_IN_PROGRESS", "OCR is already processing this document.", 409)
    run = OCRResult(document_id=doc.id, engine_name="surya", status=OCRStatus.PROCESSING,
                    engine_version="0.22.1")
    db.session.add(run)
    db.session.commit()
    try:
        path = storage.private_path(current_app.config, doc.storage_key)
        if not path.is_file():
            raise FileNotFoundError("Private document not found")
        # Import only when extraction is requested: no model loading during pytest or startup.
        from .surya_engine import extract_text
        text = extract_text(path, doc.mime_type)
        fields = extract_fields(text)
        expected = doc.application
        comparison, warnings = compare_fields(
            fields, name=expected.user.display_name,
            tower=expected.flat.tower.name, flat=expected.flat.flat_number,
            category=expected.category.value,
        )
        if not text:
            warnings.append("OCR produced no readable text; manual document review required")
        run.extracted_text = text[:100000]  # avoid unlimited DB payloads
        run.extracted_fields = fields
        run.comparison_results = comparison
        run.warnings = warnings
        run.status = OCRStatus.COMPLETED
        run.completed_at = utc_now()
        _audit("DOCUMENT_OCR_COMPLETED", doc)
        db.session.commit()
        return jsonify({"ocr": _ocr_data(run), "reused": False}), 200
    except Exception:
        current_app.logger.exception("OCR extraction failed for document ID %s", doc.id)
        db.session.rollback()
        run = db.session.get(OCRResult, run.id)
        run.status = OCRStatus.FAILED
        run.error_message = "OCR unavailable. Document remains available for manual review."
        run.warnings = ["OCR unavailable; request manual review or retry later"]
        run.completed_at = utc_now()
        _audit("DOCUMENT_OCR_FAILED", doc)
        db.session.commit()
        return error("OCR_UNAVAILABLE", "OCR could not process the document; manual review remains possible.", 503)


@documents_bp.get("/<uuid:document_id>/ocr")
@login_required
def get_ocr(document_id):
    doc = _doc(document_id)
    if not doc:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    rows = db.session.scalars(select(OCRResult).where(OCRResult.document_id == doc.id)
                              .order_by(OCRResult.created_at.desc(), OCRResult.id.desc())).all()
    return jsonify({"results": [_ocr_data(row) for row in rows]}), 200
