"""Private JPG/PNG evidence for civic issues.

Reuses Module 1's private storage (random keys outside /static) and content
checks. Files are served only through an authorised route, never a public URL.
"""
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from app.extensions import db
from app.modules.identity.auth.routes import error
from app.modules.identity.documents import storage

from .common import (
    audit, civic_reader, is_moderator, iso, no_store, resident_civic, safe_text, schema_missing, validation_error,
)
from .models import CivicIssue, EvidenceVisibility, IssueEvidence
from .service import EVIDENCE_EDITABLE, MAX_EVIDENCE_PER_ISSUE, can_view, evidence_visible

evidence_bp = Blueprint("civic_evidence", __name__)
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def evidence_payload(row: IssueEvidence) -> dict:
    return {"id": str(row.id), "caption": row.caption, "visibility": row.visibility.value,
            "mime_type": row.mime_type, "created_at": iso(row.created_at)}


@evidence_bp.post("/api/civic/issues/<uuid:issue_id>/evidence")
@resident_civic
def add_evidence(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = db.session.scalar(select(CivicIssue).where(CivicIssue.id == issue_id).with_for_update())
    if issue is None or issue.creator_id != current_user.id:
        db.session.rollback()
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    if issue.state not in EVIDENCE_EDITABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Evidence can no longer be added to this issue.", 409)
    if request.mimetype != "multipart/form-data":
        db.session.rollback()
        return error("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        db.session.rollback()
        return validation_error({"file": "Choose a photo."})
    if Path(incoming.filename).suffix.lower() not in IMAGE_EXTENSIONS:
        db.session.rollback()
        return error("INVALID_DOCUMENT", "Only JPG and PNG photos are allowed.", 400)
    problems: dict = {}
    caption = safe_text(request.form.get("caption", ""), "caption", 0, 200, problems, required=False) or ""
    try:
        visibility = EvidenceVisibility(request.form.get("visibility", EvidenceVisibility.PRIVATE.value))
    except ValueError:
        problems["visibility"] = "Choose PRIVATE or RESIDENTS."
        visibility = None
    if problems:
        db.session.rollback()
        return validation_error(problems)
    existing = db.session.scalar(
        select(func.count()).select_from(IssueEvidence).where(IssueEvidence.issue_id == issue.id)) or 0
    if existing >= MAX_EVIDENCE_PER_ISSUE:
        db.session.rollback()
        return error("EVIDENCE_LIMIT_REACHED", f"At most {MAX_EVIDENCE_PER_ISSUE} photos are allowed per issue.", 409)
    blob = incoming.stream.read(storage.MAX_FILE_BYTES + 1)
    try:
        mime = storage.validate_document(incoming.filename, blob)
    except (ValueError, RuntimeError) as exc:
        db.session.rollback()
        return error("INVALID_DOCUMENT", str(exc), 400)
    key = None
    try:
        key, checksum = storage.write_private(current_app.config, blob, mime)
        row = IssueEvidence(
            issue_id=issue.id, uploaded_by_user_id=current_user.id, visibility=visibility, caption=caption,
            storage_key=key, sha256_checksum=checksum, mime_type=mime, file_size_bytes=len(blob),
            original_filename=(secure_filename(incoming.filename) or "photo")[:255],
        )
        db.session.add(row)
        db.session.flush()
        audit("CIVIC_EVIDENCE_ADDED", "civic_issue", issue.id, {"evidence_id": str(row.id)})
        db.session.commit()
    except Exception:
        db.session.rollback()
        if key:
            storage.private_path(current_app.config, key).unlink(missing_ok=True)
        current_app.logger.exception("Civic evidence upload failed")
        return error("UPLOAD_FAILED", "Unable to save the photo.", 503)
    return no_store({"evidence": evidence_payload(row)}, 201)


@evidence_bp.delete("/api/civic/issues/<uuid:issue_id>/evidence/<uuid:evidence_id>")
@resident_civic
def remove_evidence(issue_id, evidence_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = db.session.scalar(select(CivicIssue).where(CivicIssue.id == issue_id).with_for_update())
    row = db.session.get(IssueEvidence, evidence_id)
    if issue is None or row is None or row.issue_id != issue.id or issue.creator_id != current_user.id:
        db.session.rollback()
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    if issue.state not in EVIDENCE_EDITABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Evidence can no longer be removed from this issue.", 409)
    key = row.storage_key
    db.session.delete(row)
    audit("CIVIC_EVIDENCE_REMOVED", "civic_issue", issue.id, {"evidence_id": str(evidence_id)})
    db.session.commit()
    try:
        storage.private_path(current_app.config, key).unlink(missing_ok=True)
    except ValueError:
        pass
    return no_store({"removed": True})


@evidence_bp.get("/api/civic/evidence/<uuid:evidence_id>/file")
@civic_reader
def evidence_file(evidence_id):
    missing = schema_missing()
    if missing:
        return missing
    row = db.session.get(IssueEvidence, evidence_id)
    issue = db.session.get(CivicIssue, row.issue_id) if row else None
    # Same 404 for "missing" and "not allowed" so ids cannot be probed.
    if row is None or issue is None or not evidence_visible(row, issue, current_user.id, is_moderator()):
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    try:
        path = storage.private_path(current_app.config, row.storage_key)
    except ValueError:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    if not path.is_file():
        return error("EVIDENCE_NOT_FOUND", "Photo is unavailable.", 404)
    response = send_file(path, mimetype="application/octet-stream", as_attachment=True,
                         download_name=row.original_filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
