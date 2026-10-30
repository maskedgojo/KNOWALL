"""Private photo evidence for maintenance tickets and project milestones.

Reuses Module 1's private storage (random keys under OCR_PRIVATE_DIR, never
/static) and its content checks. Only PNG and JPEG are accepted. Files are
downloaded through an authorised route, never a public URL.

Who may upload:  ticket reporter (until confirmed) or a Society Admin;
                 milestone photos: Society Admin only.
Who may view:    ticket photos follow ticket privacy (reporter + admin);
                 milestone photos: eligible residents and admins.
"""
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import func, select
from werkzeug.utils import secure_filename

from app.extensions import db
from app.modules.identity.access import has_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.documents import storage

from .common import audit, iso, manage_operations, names, no_store, schema_missing, society_or_error
from .models import (
    DevelopmentProject, MaintenanceRequest, OperationPhoto, PhotoSubject, ProjectMilestone, TicketStatus,
)

photos_bp = Blueprint("operations_photos", __name__)
MAX_PHOTOS_PER_SUBJECT = 6
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def photos_for(subject: PhotoSubject, subject_ids) -> dict:
    """Photo metadata grouped by subject id, for embedding in ticket/milestone payloads."""
    ids = list(subject_ids)
    if not ids:
        return {}
    rows = db.session.scalars(select(OperationPhoto).where(
        OperationPhoto.subject_type == subject, OperationPhoto.subject_id.in_(ids),
    ).order_by(OperationPhoto.created_at.asc(), OperationPhoto.id.asc())).all()
    people = names(row.uploaded_by_user_id for row in rows)
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.subject_id, []).append({
            "id": str(row.id), "caption": row.caption, "uploaded_by_staff": row.uploaded_by_staff,
            "uploaded_by_display_name": people.get(row.uploaded_by_user_id, ""), "created_at": iso(row.created_at),
        })
    return grouped


def _store(subject: PhotoSubject, subject_id, *, staff: bool):
    """Validate and save request.files['file']. Caller holds a lock on the subject row."""
    if request.mimetype != "multipart/form-data":
        db.session.rollback()
        return None, error("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        db.session.rollback()
        return None, error("VALIDATION_ERROR", "Choose a photo.", 400, fields={"file": "Choose a photo."})
    if Path(incoming.filename).suffix.lower() not in IMAGE_EXTENSIONS:
        db.session.rollback()
        return None, error("INVALID_DOCUMENT", "Only JPG and PNG photos are allowed.", 400)
    caption = (request.form.get("caption") or "").strip()
    if len(caption) > 200:
        db.session.rollback()
        return None, error("VALIDATION_ERROR", "Caption is too long.", 400, fields={"caption": "At most 200 characters."})
    existing = db.session.scalar(select(func.count()).select_from(OperationPhoto).where(
        OperationPhoto.subject_type == subject, OperationPhoto.subject_id == subject_id,
    )) or 0
    if existing >= MAX_PHOTOS_PER_SUBJECT:
        db.session.rollback()
        return None, error("PHOTO_LIMIT_REACHED", f"At most {MAX_PHOTOS_PER_SUBJECT} photos are allowed here.", 409)
    blob = incoming.stream.read(storage.MAX_FILE_BYTES + 1)
    try:
        mime = storage.validate_document(incoming.filename, blob)
    except (ValueError, RuntimeError) as exc:
        db.session.rollback()
        return None, error("INVALID_DOCUMENT", str(exc), 400)
    key = None
    try:
        key, checksum = storage.write_private(current_app.config, blob, mime)
        photo = OperationPhoto(
            subject_type=subject, subject_id=subject_id, uploaded_by_user_id=current_user.id,
            uploaded_by_staff=staff, caption=caption, storage_key=key, sha256_checksum=checksum,
            mime_type=mime, file_size_bytes=len(blob),
            original_filename=(secure_filename(incoming.filename) or "photo")[:255],
        )
        db.session.add(photo)
        db.session.flush()
        audit("OPERATION_PHOTO_ADDED", subject.value, subject_id, {"photo_id": str(photo.id), "staff": staff})
        db.session.commit()
    except Exception:
        db.session.rollback()
        if key:
            storage.private_path(current_app.config, key).unlink(missing_ok=True)
        current_app.logger.exception("Operations photo upload failed")
        return None, error("UPLOAD_FAILED", "Unable to save the photo.", 503)
    return photo, None


@photos_bp.post("/api/maintenance/requests/<uuid:request_id>/photos")
@login_required
def add_ticket_photo(request_id):
    missing = schema_missing()
    if missing:
        return missing
    staff = has_permission("society.operations.manage")
    if not staff and not has_permission("society.maintenance.create"):
        return error("FORBIDDEN", "You do not have permission for this action.", 403)
    ticket = db.session.scalar(select(MaintenanceRequest).where(MaintenanceRequest.id == request_id).with_for_update())
    if ticket is None or (not staff and ticket.reporter_user_id != current_user.id):
        db.session.rollback()
        return error("REQUEST_NOT_FOUND", "Maintenance request not found.", 404)
    if not staff and ticket.status == TicketStatus.CONFIRMED:
        db.session.rollback()
        return error("INVALID_STATE", "This request is closed.", 409)
    photo, failure = _store(PhotoSubject.MAINTENANCE_REQUEST, ticket.id, staff=staff)
    if failure:
        return failure
    return no_store({"photos": photos_for(PhotoSubject.MAINTENANCE_REQUEST, [ticket.id]).get(ticket.id, [])}, 201)


@photos_bp.post("/api/development/<uuid:project_id>/milestones/<uuid:milestone_id>/photos")
@manage_operations
def add_milestone_photo(project_id, milestone_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    milestone = db.session.scalar(
        select(ProjectMilestone).join(DevelopmentProject, DevelopmentProject.id == ProjectMilestone.project_id)
        .where(ProjectMilestone.id == milestone_id, ProjectMilestone.project_id == project_id,
               DevelopmentProject.society_id == society.id)
        .with_for_update()
    )
    if milestone is None:
        db.session.rollback()
        return error("MILESTONE_NOT_FOUND", "Milestone not found.", 404)
    photo, failure = _store(PhotoSubject.PROJECT_MILESTONE, milestone.id, staff=True)
    if failure:
        return failure
    return no_store({"photos": photos_for(PhotoSubject.PROJECT_MILESTONE, [milestone.id]).get(milestone.id, [])}, 201)


def _can_view(photo: OperationPhoto) -> bool:
    if has_permission("society.operations.manage"):
        return True
    if photo.subject_type == PhotoSubject.MAINTENANCE_REQUEST:
        reporter = db.session.scalar(select(MaintenanceRequest.reporter_user_id).where(
            MaintenanceRequest.id == photo.subject_id))
        return reporter == current_user.id and has_permission("society.maintenance.create")
    return has_permission("society.notices.read")


@photos_bp.get("/api/operations/photos/<uuid:photo_id>/file")
@login_required
def photo_file(photo_id):
    missing = schema_missing()
    if missing:
        return missing
    photo = db.session.get(OperationPhoto, photo_id)
    # Same 404 for "missing" and "not yours" so ids cannot be probed.
    if photo is None or not _can_view(photo):
        return error("DOCUMENT_NOT_FOUND", "Photo not found.", 404)
    try:
        path = storage.private_path(current_app.config, photo.storage_key)
    except ValueError:
        return error("DOCUMENT_NOT_FOUND", "Photo not found.", 404)
    if not path.is_file():
        return error("DOCUMENT_NOT_FOUND", "Photo is unavailable.", 404)
    response = send_file(path, mimetype="application/octet-stream", as_attachment=True,
                         download_name=photo.original_filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
