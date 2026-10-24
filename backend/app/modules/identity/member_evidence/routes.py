"""Targeted member evidence requests — private, audited, no automatic suspension."""
from datetime import timedelta
from pathlib import Path
from uuid import UUID
from werkzeug.utils import secure_filename

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.access import requires_permission, has_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.documents import storage
from app.modules.identity.models import (
    AuditLog, MemberEvidenceRequest, MemberEvidenceStatus, Membership, User,
    Flat, Household,
)
from app.modules.identity.models.user import utc_now
from app.modules.identity.residential.routes import _membership_summary, _access_state, _unit

member_evidence_bp = Blueprint("member_evidence", __name__)
admin_only = requires_permission("identity.admin.manage")


def _audit(action, entry, context=None):
    db.session.add(AuditLog(actor_user_id=current_user.id, action=action,
        entity_type="MEMBER_EVIDENCE_REQUEST", entity_id=entry.id, details=context or {}))


def _serialize(entry):
    return {"id": str(entry.id), "membership_id": str(entry.membership_id),
        "reason": entry.reason, "evidence_needed": entry.evidence_needed,
        "status": entry.status.value, "created_at": entry.created_at.isoformat(),
        "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
        "resolved_at": entry.resolved_at.isoformat() if entry.resolved_at else None,
        "review_note": entry.review_note,
        "document": ({"filename": entry.original_filename, "mime_type": entry.mime_type,
                      "size_bytes": entry.file_size_bytes,
                      "download_url": f"/api/member-evidence/{entry.id}/file"}
                     if entry.storage_key and entry.deleted_at is None else None),
        "retention_delete_after": (entry.retention_delete_after.isoformat()
                                   if entry.retention_delete_after else None)}


def _visible(entry):
    return entry.membership.user_id == current_user.id or has_permission("identity.admin.manage")


def _pagination():
    try:
        limit = int(request.args.get("limit", 30)); offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


@member_evidence_bp.get("/api/admin/households")
@admin_only
def admin_households():
    """Directory by household, not flat: ownership and tenancy stay separate."""
    page = _pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    count = db.session.scalar(select(func.count()).select_from(Household))
    homes = db.session.scalars(select(Household).join(Flat)
        .order_by(Flat.tower_id, Flat.flat_number, Household.id)
        .limit(limit).offset(offset)).all()
    records = []
    for home in homes:
        members = db.session.scalars(select(Membership).where(Membership.household_id == home.id)
            .order_by(Membership.created_at, Membership.id)).all()
        # Only explicit members of THIS household; never discover by shared flat.
        anchors = {m.id: m for m in members if m.category.value in ("OWNER", "TENANT")}
        rows = []
        for member in members:
            sponsor = anchors.get(member.sponsor_membership_id)
            row = {"membership_id": str(member.id), "display_name": member.user.display_name,
                "category": member.category.value, "membership_status": member.status.value,
                "access_state": _access_state(member),
                "relationship_to_sponsor": member.relationship_to_sponsor,
                "sponsor_membership_id": str(member.sponsor_membership_id) if member.sponsor_membership_id else None,
                "sponsor_display_name": sponsor.user.display_name if sponsor else None,
                "is_current_occupant": member.is_current_occupant,
                "declared_current_occupant": member.declared_current_occupant,
                "valid_from": member.valid_from.isoformat(),
                "valid_until": member.valid_until.isoformat() if member.valid_until else None}
            rows.append(row)
        records.append({"household_id": str(home.id), "household_label": home.label,
            "flat": _unit(home.flat), "members": rows})
    return jsonify({"households": records,
        "pagination": {"limit": limit, "offset": offset, "total": count}}), 200


@member_evidence_bp.post("/api/admin/memberships/<uuid:membership_id>/evidence-requests")
@admin_only
def request_evidence(membership_id):
    body, failure = json_object({"reason", "evidence_needed"})
    if failure: return failure
    reason = body.get("reason"); needed = body.get("evidence_needed")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1200:
        return error("VALIDATION_ERROR", "A reason of 10–1200 characters is required.", 400)
    if not isinstance(needed, str) or not 5 <= len(needed.strip()) <= 500:
        return error("VALIDATION_ERROR", "Describe the minimally necessary supporting evidence (5–500 characters).", 400)
    member = db.session.get(Membership, membership_id)
    if member is None:
        return error("MEMBERSHIP_NOT_FOUND", "Membership not found.", 404)
    # Prevent a barrage of overlapping open requests for the same member.
    existing = db.session.scalar(select(MemberEvidenceRequest.id).where(
        MemberEvidenceRequest.membership_id == membership_id,
        MemberEvidenceRequest.status.in_([MemberEvidenceStatus.REQUESTED, MemberEvidenceStatus.SUBMITTED])))
    if existing:
        return error("EVIDENCE_REQUEST_ALREADY_OPEN", "Resolve the existing evidence request first.", 409)
    entry = MemberEvidenceRequest(membership_id=membership_id, requested_by_user_id=current_user.id,
        reason=reason.strip(), evidence_needed=needed.strip(), status=MemberEvidenceStatus.REQUESTED)
    try:
        db.session.add(entry)
        db.session.flush()
        _audit("MEMBER_EVIDENCE_REQUESTED", entry, {"membership_id": str(membership_id)})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("EVIDENCE_REQUEST_ALREADY_OPEN", "An unresolved evidence request already exists.", 409)
    return jsonify({"request": _serialize(entry)}), 201


@member_evidence_bp.get("/api/admin/evidence-requests")
@admin_only
def admin_evidence_requests():
    page = _pagination()
    if page is None: return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    count = db.session.scalar(select(func.count()).select_from(MemberEvidenceRequest))
    rows = db.session.scalars(select(MemberEvidenceRequest).order_by(
        MemberEvidenceRequest.created_at.desc()).limit(limit).offset(offset)).all()
    return jsonify({"requests": [_serialize(x) for x in rows],
                    "pagination": {"limit": limit, "offset": offset, "total": count}}), 200


@member_evidence_bp.get("/api/me/evidence-requests")
@login_required
def own_evidence_requests():
    rows = db.session.scalars(select(MemberEvidenceRequest).join(Membership)
        .where(Membership.user_id == current_user.id)
        .order_by(MemberEvidenceRequest.created_at.desc())).all()
    return jsonify({"requests": [_serialize(x) for x in rows]}), 200


@member_evidence_bp.post("/api/me/evidence-requests/<uuid:entry_id>/upload")
@login_required
def submit_evidence(entry_id):
    # Lock before checking status; two concurrent submissions cannot overwrite.
    db.session.execute(select(MemberEvidenceRequest.id).where(
        MemberEvidenceRequest.id == entry_id).with_for_update()).first()
    entry = db.session.get(MemberEvidenceRequest, entry_id)
    if entry is None or entry.membership.user_id != current_user.id:
        db.session.rollback()
        return error("EVIDENCE_REQUEST_NOT_FOUND", "Evidence request not found.", 404)
    if entry.status != MemberEvidenceStatus.REQUESTED or entry.storage_key is not None:
        db.session.rollback()
        return error("INVALID_EVIDENCE_STATE", "This request does not accept an upload.", 409)
    if request.mimetype != "multipart/form-data":
        db.session.rollback()
        return error("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Select a supporting document.", 400)
    blob = incoming.stream.read(storage.MAX_FILE_BYTES + 1)
    try:
        mime = storage.validate_document(incoming.filename, blob)
    except (ValueError, RuntimeError) as exc:
        db.session.rollback()
        return error("INVALID_DOCUMENT", str(exc), 400)
    key = None
    try:
        key, checksum = storage.write_private(current_app.config, blob, mime)
        entry.storage_key = key
        entry.sha256_checksum = checksum
        entry.original_filename = (secure_filename(incoming.filename) or "evidence")[:255]
        entry.mime_type = mime
        entry.file_size_bytes = len(blob)
        entry.status = MemberEvidenceStatus.SUBMITTED
        entry.submitted_at = utc_now()
        _audit("MEMBER_EVIDENCE_SUBMITTED", entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if key: storage.private_path(current_app.config, key).unlink(missing_ok=True)
        current_app.logger.exception("Member evidence upload failed")
        return error("UPLOAD_FAILED", "Unable to save evidence.", 503)
    return jsonify({"request": _serialize(entry)}), 200


@member_evidence_bp.get("/api/member-evidence/<uuid:entry_id>/file")
@login_required
def view_evidence(entry_id):
    entry = db.session.get(MemberEvidenceRequest, entry_id)
    if entry is None or not _visible(entry) or not entry.storage_key or entry.deleted_at:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    try:
        file = storage.private_path(current_app.config, entry.storage_key)
    except ValueError:
        return error("DOCUMENT_NOT_FOUND", "Document not found.", 404)
    if not file.is_file(): return error("DOCUMENT_NOT_FOUND", "Document is unavailable.", 404)
    response = send_file(file, mimetype="application/octet-stream", as_attachment=True,
                         download_name=entry.original_filename, max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@member_evidence_bp.post("/api/admin/evidence-requests/<uuid:entry_id>/resolve")
@admin_only
def resolve_evidence(entry_id):
    body, failure = json_object({"decision", "review_note"})
    if failure: return failure
    try: decision = MemberEvidenceStatus(body.get("decision"))
    except (TypeError, ValueError):
        return error("VALIDATION_ERROR", "decision must be ACCEPTED, REJECTED or CANCELLED.", 400)
    if decision not in (MemberEvidenceStatus.ACCEPTED, MemberEvidenceStatus.REJECTED, MemberEvidenceStatus.CANCELLED):
        return error("VALIDATION_ERROR", "Invalid review decision.", 400)
    note = body.get("review_note")
    if not isinstance(note, str) or not 3 <= len(note.strip()) <= 1200:
        return error("VALIDATION_ERROR", "A review note of 3–1200 characters is required.", 400)
    db.session.execute(select(MemberEvidenceRequest.id).where(
        MemberEvidenceRequest.id == entry_id).with_for_update()).first()
    entry = db.session.get(MemberEvidenceRequest, entry_id)
    if entry is None:
        db.session.rollback()
        return error("EVIDENCE_REQUEST_NOT_FOUND", "Evidence request not found.", 404)
    if not ((entry.status == MemberEvidenceStatus.SUBMITTED and decision in (MemberEvidenceStatus.ACCEPTED, MemberEvidenceStatus.REJECTED))
            or (entry.status == MemberEvidenceStatus.REQUESTED and decision == MemberEvidenceStatus.CANCELLED)):
        db.session.rollback()
        return error("INVALID_EVIDENCE_STATE", "Resolution is invalid for this request state.", 409)
    entry.status = decision
    entry.review_note = note.strip()
    entry.resolved_by_user_id = current_user.id
    entry.resolved_at = utc_now()
    if entry.storage_key:
        entry.retention_delete_after = entry.resolved_at + timedelta(days=90)
    _audit("MEMBER_EVIDENCE_" + decision.value, entry)
    db.session.commit()
    return jsonify({"request": _serialize(entry)}), 200


def register_cli(app):
    @app.cli.command("purge-expired-member-evidence")
    def purge_expired_member_evidence():
        """Purge expired resolved attachments, retaining metadata and audit history."""
        now = utc_now()
        rows = db.session.scalars(select(MemberEvidenceRequest).where(
            MemberEvidenceRequest.retention_delete_after <= now,
            MemberEvidenceRequest.deleted_at.is_(None),
            MemberEvidenceRequest.storage_key.is_not(None))).all()
        count = 0
        for entry in rows:
            try:
                storage.private_path(app.config, entry.storage_key).unlink(missing_ok=True)
            except OSError:
                app.logger.exception("Failed to purge evidence attachment %s", entry.id)
                continue
            entry.deleted_at = now
            # Never put original tokens, hashes or evidence contents in audit logs.
            db.session.add(AuditLog(action="MEMBER_EVIDENCE_PURGED",
                entity_type="MEMBER_EVIDENCE_REQUEST", entity_id=entry.id,
                details={"policy": "resolved-plus-90-days"}))
            count += 1
        db.session.commit()
        print(f"Purged {count} resolved member-evidence attachment(s).")
