"""Resident-facing case tracker, community verification, clarification replies and notifications."""
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, request
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.modules.civic.common import aware, civic_reader, is_moderator
from app.modules.civic.models import CivicIssue
from app.modules.civic.service import can_view, canonical_ids
from app.modules.identity.access import has_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.documents import storage
from app.modules.identity.residential.routes import _eligible_memberships

from .cases import _send_private
from .common import (
    RESIDENT_PERMISSION, SIMULATION_NOTICE, audit, current_officer, is_coordinator, iso, json_body, no_store,
    safe_text, schema_missing, validation_error,
)
from .models import (
    ActorKind, AuthorityCase, CaseClarification, CaseNotification, CaseStatus, ClarificationStatus,
    ResolutionEvidence, ResolutionVerification, Verdict,
)
from .service import (
    STATUS_LABELS, affected_user_ids, apply_verdict_rules, case_for_issue, events_for, evidence_json,
    fetch_case_locked, notify_department, public_status, record, tally,
)

resident_bp = Blueprint("authority_resident", __name__)
C = CaseStatus
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _verification_open(case: AuthorityCase, at: datetime) -> bool:
    return case.status == C.RESOLVED and case.verification_closes_at is not None and \
        aware(case.verification_closes_at) > at


def tracker(case: AuthorityCase, issue: CivicIssue, viewer_id) -> dict:
    """The linked case as the reporter / residents see it. Same status the official sees."""
    now = datetime.now(timezone.utc)
    affected = affected_user_ids(case)
    vote = db.session.scalar(select(ResolutionVerification).where(
        ResolutionVerification.case_id == case.id, ResolutionVerification.round == case.round,
        ResolutionVerification.user_id == viewer_id))
    evidence = db.session.scalars(select(ResolutionEvidence).where(ResolutionEvidence.case_id == case.id)
                                  .order_by(ResolutionEvidence.created_at, ResolutionEvidence.id)).all()
    open_clarification = None
    if issue.creator_id == viewer_id:
        row = db.session.scalar(select(CaseClarification).where(
            CaseClarification.case_id == case.id, CaseClarification.status == ClarificationStatus.OPEN))
        if row:
            open_clarification = {"id": str(row.id), "question": row.question, "asked_at": iso(row.asked_at)}
    events = [{"sequence": row.sequence, "action": row.action, "to_status": row.to_status,
               "status_label": STATUS_LABELS.get(C(row.to_status), row.to_status),
               "summary": row.public_summary, "at": iso(row.created_at)}
              for row in events_for(case) if row.public_summary]
    return {
        **public_status(case),
        "civic_issue_id": str(case.civic_issue_id),
        "timeline": events,
        "evidence": [evidence_json(row) for row in evidence],
        "verification": {
            **tally(case),
            "open": _verification_open(case, now),
            "viewer_is_affected": viewer_id in affected,
            "viewer_can_verify": _verification_open(case, now) and viewer_id in affected and vote is None
            and has_permission(RESIDENT_PERMISSION),
            "viewer_verdict": vote.verdict.value if vote else None,
        },
        "open_clarification": open_clarification,
        "simulation_notice": SIMULATION_NOTICE,
    }


@resident_bp.get("/api/civic/issues/<uuid:issue_id>/case-status")
@civic_reader
def case_status(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = db.session.get(CivicIssue, issue_id)
    if issue is None or not can_view(issue, current_user.id, is_moderator()):
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    canonical_id = canonical_ids([issue.id]).get(issue.id, issue.id)
    case = case_for_issue(canonical_id)
    if case is None:
        return no_store({"case": None, "canonical_issue_id": str(canonical_id),
                         "simulation_notice": SIMULATION_NOTICE})
    canonical = db.session.get(CivicIssue, canonical_id)
    return no_store({"case": tracker(case, canonical, current_user.id), "canonical_issue_id": str(canonical_id),
                     "simulation_notice": SIMULATION_NOTICE})


def _read_verification_body():
    """JSON, or multipart when the resident attaches a photo to a dispute."""
    if request.mimetype == "multipart/form-data":
        allowed = {"verdict", "reason"}
        unknown = sorted(set(request.form) - allowed)
        if unknown:
            return None, None, error("VALIDATION_ERROR", "Unexpected fields are not accepted.", 400,
                                     fields={name: "Unknown field." for name in unknown})
        return dict(request.form), request.files.get("photo"), None
    body, failure = json_body({"verdict", "reason"})
    return body, None, failure


@resident_bp.post("/api/authority/cases/<uuid:case_id>/verify")
@login_required
def verify(case_id):
    missing = schema_missing()
    if missing:
        return missing
    if not has_permission(RESIDENT_PERMISSION):
        return error("FORBIDDEN", "Only verified residents can verify a fix.", 403)
    body, photo, failure = _read_verification_body()
    if failure:
        return failure
    problems: dict = {}
    try:
        verdict = Verdict(body.get("verdict"))
    except ValueError:
        verdict = None
        problems["verdict"] = "Choose CONFIRMED or DISPUTED."
    minimum = 10 if verdict == Verdict.DISPUTED else 0
    reason = safe_text(body.get("reason", ""), "reason", minimum, 1000, problems, required=minimum > 0) or ""
    if photo is not None and photo.filename and Path(photo.filename).suffix.lower() not in IMAGE_EXTENSIONS:
        problems["photo"] = "Only JPG and PNG photos are allowed."
    if photo is not None and photo.filename and verdict == Verdict.CONFIRMED:
        problems["photo"] = "A photo can be attached only when disputing the fix."
    if problems:
        return validation_error(problems)
    case = fetch_case_locked(case_id)
    if case is None:
        db.session.rollback()
        return error("CASE_NOT_FOUND", "Case not found.", 404)
    now = datetime.now(timezone.utc)
    if not _verification_open(case, now):
        db.session.rollback()
        return error("VERIFICATION_CLOSED", "This case is not waiting for resident verification.", 409)
    if current_user.id not in affected_user_ids(case):
        db.session.rollback()
        return error("NOT_AFFECTED", "Only the reporter and residents who supported this issue can verify it.", 403)
    memberships = _eligible_memberships()
    if not memberships:
        db.session.rollback()
        return error("FORBIDDEN", "An active residential membership is required.", 403)
    already = db.session.scalar(select(ResolutionVerification.id).where(
        ResolutionVerification.case_id == case.id, ResolutionVerification.round == case.round,
        ResolutionVerification.user_id == current_user.id))
    if already:
        db.session.rollback()
        return error("ALREADY_VERIFIED", "You already gave your verdict for this fix.", 409)
    key = mime = filename = None
    if photo is not None and photo.filename:
        blob = photo.stream.read(storage.MAX_FILE_BYTES + 1)
        try:
            mime = storage.validate_document(photo.filename, blob)
        except (ValueError, RuntimeError) as exc:
            db.session.rollback()
            return error("INVALID_DOCUMENT", str(exc), 400)
        if mime not in ("image/png", "image/jpeg"):
            db.session.rollback()
            return error("INVALID_DOCUMENT", "Only JPG and PNG photos are allowed.", 400)
        key, _checksum = storage.write_private(current_app.config, blob, mime)
        filename = (secure_filename(photo.filename) or "photo")[:255]
    row = ResolutionVerification(
        case_id=case.id, round=case.round, user_id=current_user.id, membership_id=memberships[0].id,
        verdict=verdict, reason=reason, photo_storage_key=key, photo_mime_type=mime, photo_filename=filename,
        created_at=now,
    )
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        if key:
            storage.private_path(current_app.config, key).unlink(missing_ok=True)
        return error("ALREADY_VERIFIED", "You already gave your verdict for this fix.", 409)
    label = "confirmed the fix" if verdict == Verdict.CONFIRMED else "disputed the fix"
    record(case, action="VERIFICATION_" + verdict.value, to_status=case.status, actor_id=current_user.id,
           actor_kind=ActorKind.RESIDENT, reason=reason, check=False, at=now,
           public_summary=f"An affected resident {label}.",
           details={"round": case.round, "verification_id": str(row.id), "has_photo": key is not None})
    outcome = apply_verdict_rules(case, now)
    if verdict == Verdict.DISPUTED and outcome is None:
        notify_department(case, "FIX_DISPUTED", f"A resident disputed the fix on case {case.reference}: {reason}")
    audit("AUTHORITY_VERIFICATION", "authority_case", case.id, {"verdict": verdict.value, "outcome": outcome})
    db.session.commit()
    issue = db.session.get(CivicIssue, case.civic_issue_id)
    return no_store({"case": tracker(case, issue, current_user.id), "outcome": outcome}, 201)


@resident_bp.post("/api/authority/cases/<uuid:case_id>/respond-clarification")
@login_required
def respond_clarification(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"response"})
    if failure:
        return failure
    problems: dict = {}
    response = safe_text(body.get("response"), "response", 5, 1000, problems)
    if problems:
        return validation_error(problems)
    case = fetch_case_locked(case_id)
    issue = db.session.get(CivicIssue, case.civic_issue_id) if case else None
    if case is None or issue is None or issue.creator_id != current_user.id:
        db.session.rollback()
        return error("CASE_NOT_FOUND", "Case not found.", 404)
    row = db.session.scalar(select(CaseClarification).where(
        CaseClarification.case_id == case.id, CaseClarification.status == ClarificationStatus.OPEN).with_for_update())
    if row is None or case.status != C.CLARIFICATION_REQUESTED:
        db.session.rollback()
        return error("NO_OPEN_CLARIFICATION", "The department is not waiting for a reply.", 409)
    now = datetime.now(timezone.utc)
    row.response, row.responder_user_id, row.responded_at = response, current_user.id, now
    row.status = ClarificationStatus.ANSWERED
    record(case, action="CLARIFICATION_ANSWERED", to_status=C(row.resume_status), actor_id=current_user.id,
           actor_kind=ActorKind.RESIDENT, reason=response, at=now,
           public_summary="The reporter answered the department's question.")
    notify_department(case, "CLARIFICATION_ANSWERED", f"Reporter replied on case {case.reference}: {response}")
    audit("AUTHORITY_CLARIFICATION_ANSWERED", "authority_case", case.id)
    db.session.commit()
    return no_store({"case": tracker(case, issue, current_user.id)})


# --------------------------------------------------------------- files visible to residents

@resident_bp.get("/api/authority/evidence/<uuid:evidence_id>/file")
@login_required
def resolution_evidence_file(evidence_id):
    """Official photos: the assigned department, coordinators, and residents who can view the civic issue."""
    missing = schema_missing()
    if missing:
        return missing
    row = db.session.get(ResolutionEvidence, evidence_id)
    case = db.session.get(AuthorityCase, row.case_id) if row else None
    if row is None or case is None:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    officer = current_officer()
    allowed = is_coordinator() or (officer is not None and officer.department_id == case.department_id)
    if not allowed and has_permission(RESIDENT_PERMISSION):
        issue = db.session.get(CivicIssue, case.civic_issue_id)
        allowed = issue is not None and can_view(issue, current_user.id, False)
    if not allowed:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    return _send_private(row.storage_key, row.original_filename)


@resident_bp.get("/api/authority/verifications/<uuid:verification_id>/photo")
@login_required
def dispute_photo(verification_id):
    """A resident's dispute photo: the resident, the assigned department and coordinators."""
    missing = schema_missing()
    if missing:
        return missing
    row = db.session.get(ResolutionVerification, verification_id)
    case = db.session.get(AuthorityCase, row.case_id) if row else None
    if row is None or case is None or row.photo_storage_key is None:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    officer = current_officer()
    allowed = row.user_id == current_user.id or is_coordinator() or \
        (officer is not None and officer.department_id == case.department_id)
    if not allowed:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    return _send_private(row.photo_storage_key, row.photo_filename or "photo")


# --------------------------------------------------------------- notifications

@resident_bp.get("/api/authority/notifications")
@login_required
def notifications():
    missing = schema_missing()
    if missing:
        return missing
    rows = db.session.scalars(select(CaseNotification).where(CaseNotification.recipient_user_id == current_user.id)
                              .order_by(CaseNotification.created_at.desc()).limit(50)).all()
    return no_store({"notifications": [{
        "id": str(row.id), "case_id": str(row.case_id), "event_type": row.event_type, "message": row.message,
        "created_at": iso(row.created_at), "read_at": iso(row.read_at)} for row in rows],
        "unread": sum(1 for row in rows if row.read_at is None)})


@resident_bp.post("/api/authority/notifications/<uuid:notification_id>/read")
@login_required
def mark_read(notification_id):
    missing = schema_missing()
    if missing:
        return missing
    row = db.session.get(CaseNotification, notification_id)
    if row is None or row.recipient_user_id != current_user.id:
        return error("NOTIFICATION_NOT_FOUND", "Notification not found.", 404)
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        db.session.commit()
    return no_store({"id": str(row.id), "read_at": iso(row.read_at)})
