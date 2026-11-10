"""Coordinator workflow: review, validate, request information, reject, merge duplicates, handle abuse reports."""
from datetime import datetime, timezone

from flask import Blueprint, request
from flask_login import current_user
from sqlalchemy import and_, select

from app.extensions import db
from app.modules.identity.auth.routes import error

from . import priority
from .common import (
    audit, choice, haversine_m, json_body, moderator, no_store, pagination, safe_text, schema_missing, text,
    validation_error,
)
from .models import (
    ActorRole, CivicIssue, ConcernType, DuplicateLink, EvidenceVisibility, IssueEvidence, IssueHandoff,
    IssueModerationReport, IssueSeverity, IssueState, ReportDisposition, ReportStatus,
)
from .service import (
    COMMUNITY_STATES, MERGE_MAX_DISTANCE_M, InvalidTransition, serialize_issues, supporter_sets, transition,
)
from .issues import fetch_locked, invalid_state

moderation_bp = Blueprint("civic_moderation", __name__)
S = IssueState
QUEUE_STATES = (S.SUBMITTED, S.UNDER_REVIEW, S.NEEDS_INFO, S.VALIDATED)
REDACTED_TEXT = "[Removed by a coordinator: this content did not meet community guidelines.]"


def _not_found():
    db.session.rollback()
    return error("ISSUE_NOT_FOUND", "Issue not found.", 404)


def _respond(issue, status=200):
    item = serialize_issues([issue], viewer_id=current_user.id, moderator=True, detail=True)[0]
    return no_store({"issue": item}, status)


def _reason(body, required=True):
    problems: dict = {}
    value = safe_text(body.get("reason"), "reason", 5 if required else 0, 500, problems, required=required) or ""
    return value, (validation_error(problems) if problems else None)


@moderation_bp.get("/api/civic/admin/issues")
@moderator
def moderation_queue():
    missing = schema_missing()
    if missing:
        return missing
    page = pagination()
    if page is None:
        return validation_error({"limit": "Use limit 1-100 and offset 0 or more."})
    limit, offset = page
    states = list(QUEUE_STATES)
    if request.args.get("state"):
        problems: dict = {}
        state = choice(request.args["state"], "state", IssueState, problems)
        if problems:
            return validation_error(problems)
        states = [state]
    rows = db.session.scalars(
        select(CivicIssue).where(CivicIssue.state.in_(states)).order_by(CivicIssue.created_at.asc())
    ).all()
    payload = serialize_issues(rows[offset:offset + limit], viewer_id=current_user.id, moderator=True)
    return no_store({"issues": payload, "total": len(rows), "limit": limit, "offset": offset})


@moderation_bp.post("/api/civic/admin/issues/<uuid:issue_id>/review")
@moderator
def start_review(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = fetch_locked(issue_id)
    if issue is None:
        return _not_found()
    try:
        transition(issue, S.UNDER_REVIEW, actor_id=current_user.id, role=ActorRole.MODERATOR, reason="Review started.")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    audit("CIVIC_ISSUE_REVIEW_STARTED", "civic_issue", issue.id)
    db.session.commit()
    return _respond(issue)


@moderation_bp.post("/api/civic/admin/issues/<uuid:issue_id>/validate")
@moderator
def validate_issue(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"note", "severity"})
    if failure:
        return failure
    problems: dict = {}
    note = safe_text(body.get("note"), "note", 0, 500, problems, required=False) or ""
    severity = None
    if "severity" in body:
        severity = choice(body["severity"], "severity", IssueSeverity, problems)
    if problems:
        return validation_error(problems)
    issue = fetch_locked(issue_id)
    if issue is None:
        return _not_found()
    try:
        transition(issue, S.VALIDATED, actor_id=current_user.id, role=ActorRole.MODERATOR,
                   reason=note or "Validated by coordinator.")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    if severity and severity != issue.severity:
        audit("CIVIC_SEVERITY_ADJUSTED", "civic_issue", issue.id, {"from": issue.severity.value, "to": severity.value})
        issue.severity = severity
    count = len(supporter_sets([issue.id]).get(issue.id, set()))
    priority.record_snapshot(issue, count, "VALIDATED")
    audit("CIVIC_ISSUE_VALIDATED", "civic_issue", issue.id)
    db.session.commit()
    return _respond(issue)


@moderation_bp.post("/api/civic/admin/issues/<uuid:issue_id>/needs-info")
@moderator
def request_information(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"reason"})
    if failure:
        return failure
    reason, failure = _reason(body)
    if failure:
        return failure
    issue = fetch_locked(issue_id)
    if issue is None:
        return _not_found()
    try:
        transition(issue, S.NEEDS_INFO, actor_id=current_user.id, role=ActorRole.MODERATOR, reason=reason)
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    audit("CIVIC_ISSUE_NEEDS_INFO", "civic_issue", issue.id)
    db.session.commit()
    return _respond(issue)


@moderation_bp.post("/api/civic/admin/issues/<uuid:issue_id>/reject")
@moderator
def reject_issue(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"reason"})
    if failure:
        return failure
    reason, failure = _reason(body)
    if failure:
        return failure
    issue = fetch_locked(issue_id)
    if issue is None:
        return _not_found()
    try:
        transition(issue, S.REJECTED, actor_id=current_user.id, role=ActorRole.MODERATOR, reason=reason)
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    audit("CIVIC_ISSUE_REJECTED", "civic_issue", issue.id)
    db.session.commit()
    return _respond(issue)


@moderation_bp.post("/api/civic/admin/issues/<uuid:issue_id>/merge")
@moderator
def merge_issue(issue_id):
    """Link `issue_id` (the duplicate) to a canonical issue. Support is combined by identity, never summed."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"canonical_issue_id", "reason", "acknowledge_distance"})
    if failure:
        return failure
    problems: dict = {}
    import uuid
    try:
        canonical_id = uuid.UUID(str(body.get("canonical_issue_id")))
    except ValueError:
        canonical_id = None
        problems["canonical_issue_id"] = "Provide the canonical issue id."
    reason = safe_text(body.get("reason"), "reason", 5, 500, problems)
    acknowledged = body.get("acknowledge_distance", False)
    if not isinstance(acknowledged, bool):
        problems["acknowledge_distance"] = "Must be true or false."
    if canonical_id == issue_id:
        problems["canonical_issue_id"] = "An issue cannot be merged into itself."
    if problems:
        return validation_error(problems)
    # Lock in a stable order so two concurrent merges cannot deadlock.
    locked = {row.id: row for row in db.session.scalars(
        select(CivicIssue).where(CivicIssue.id.in_([issue_id, canonical_id])).order_by(CivicIssue.id).with_for_update())}
    duplicate, canonical = locked.get(issue_id), locked.get(canonical_id)
    if duplicate is None or canonical is None:
        return _not_found()
    if canonical.state not in COMMUNITY_STATES:
        db.session.rollback()
        return error("INVALID_CANONICAL", "The target issue is not open, so it cannot be a canonical issue.", 409)
    if duplicate.category != canonical.category:
        db.session.rollback()
        return error("CATEGORY_MISMATCH", "Issues in different categories cannot be merged.", 409)
    handed_off = db.session.scalar(select(IssueHandoff.id).where(IssueHandoff.canonical_issue_id == duplicate.id))
    if handed_off:
        db.session.rollback()
        return error("INVALID_STATE", "This issue was already routed and cannot be merged.", 409)
    distance = haversine_m(duplicate.latitude, duplicate.longitude, canonical.latitude, canonical.longitude)
    if distance > MERGE_MAX_DISTANCE_M and not acknowledged:
        db.session.rollback()
        return error(
            "LOCATIONS_TOO_FAR",
            f"These reports are {round(distance)} m apart. Confirm they describe the same issue to merge them.",
            422, fields={"acknowledge_distance": "Set true to confirm."},
        )
    try:
        transition(duplicate, S.MERGED, actor_id=current_user.id, role=ActorRole.MODERATOR,
                   reason=f"Merged into issue {canonical.id}: {reason}")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    # Anything already merged into the duplicate now points at the new canonical issue.
    for link in db.session.scalars(select(DuplicateLink).where(DuplicateLink.canonical_issue_id == duplicate.id)):
        link.canonical_issue_id = canonical.id
    db.session.add(DuplicateLink(
        canonical_issue_id=canonical.id, duplicate_issue_id=duplicate.id, reason=reason,
        distance_m=round(distance, 1), linked_by_user_id=current_user.id,
    ))
    db.session.flush()
    count = len(supporter_sets([canonical.id]).get(canonical.id, set()))
    priority.record_snapshot(canonical, count, "DUPLICATE_MERGED")
    audit("CIVIC_ISSUE_MERGED", "civic_issue", duplicate.id, {"canonical_issue_id": str(canonical.id)})
    db.session.commit()
    return no_store({
        "duplicate": serialize_issues([duplicate], viewer_id=current_user.id, moderator=True)[0],
        "canonical": serialize_issues([canonical], viewer_id=current_user.id, moderator=True)[0],
    })


@moderation_bp.post("/api/civic/admin/evidence/<uuid:evidence_id>/visibility")
@moderator
def set_evidence_visibility(evidence_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"visibility"})
    if failure:
        return failure
    problems: dict = {}
    visibility = choice(body.get("visibility"), "visibility", EvidenceVisibility, problems)
    if problems:
        return validation_error(problems)
    row = db.session.get(IssueEvidence, evidence_id)
    if row is None:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    row.visibility = visibility
    audit("CIVIC_EVIDENCE_VISIBILITY", "civic_issue", row.issue_id,
          {"evidence_id": str(row.id), "visibility": visibility.value})
    db.session.commit()
    return no_store({"evidence": {"id": str(row.id), "visibility": row.visibility.value}})


# ------------------------------------------------------------------ abuse reports

def _report_payload(report: IssueModerationReport) -> dict:
    return {
        "id": str(report.id), "issue_id": str(report.issue_id), "concern_type": report.concern_type.value,
        "concern": report.concern, "status": report.status.value,
        "disposition": report.disposition.value if report.disposition else None,
        "resolution_note": report.resolution_note,
        "created_at": report.created_at.isoformat(),
        "resolved_at": report.resolved_at.isoformat() if report.resolved_at else None,
    }


@moderation_bp.get("/api/civic/admin/reports")
@moderator
def list_reports():
    missing = schema_missing()
    if missing:
        return missing
    problems: dict = {}
    status = choice(request.args.get("status", "OPEN"), "status", ReportStatus, problems)
    if problems:
        return validation_error(problems)
    rows = db.session.scalars(
        select(IssueModerationReport).where(IssueModerationReport.status == status)
        .order_by(IssueModerationReport.created_at.asc()).limit(200)
    ).all()
    return no_store({"reports": [_report_payload(row) for row in rows]})


@moderation_bp.post("/api/civic/admin/reports/<uuid:report_id>/resolve")
@moderator
def resolve_report(report_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"disposition", "note"})
    if failure:
        return failure
    problems: dict = {}
    disposition = choice(body.get("disposition"), "disposition", ReportDisposition, problems)
    note = safe_text(body.get("note"), "note", 5, 500, problems)
    if problems:
        return validation_error(problems)
    report = db.session.scalar(
        select(IssueModerationReport).where(IssueModerationReport.id == report_id).with_for_update())
    if report is None:
        db.session.rollback()
        return error("REPORT_NOT_FOUND", "Report not found.", 404)
    if report.status == ReportStatus.RESOLVED:
        db.session.rollback()
        return error("INVALID_STATE", "This report was already resolved.", 409)
    issue = fetch_locked(report.issue_id)
    try:
        if disposition == ReportDisposition.REDACTED:
            report.original_description = issue.description
            issue.description = REDACTED_TEXT
            for item in db.session.scalars(select(IssueEvidence).where(IssueEvidence.issue_id == issue.id)):
                item.visibility = EvidenceVisibility.PRIVATE
            issue.updated_at = datetime.now(timezone.utc)
        elif disposition == ReportDisposition.CORRECTION_REQUESTED:
            transition(issue, S.NEEDS_INFO, actor_id=current_user.id, role=ActorRole.MODERATOR,
                       reason=f"Correction requested after a concern: {note}")
        elif disposition == ReportDisposition.REMOVED:
            transition(issue, S.REJECTED, actor_id=current_user.id, role=ActorRole.MODERATOR,
                       reason=f"Removed after a concern: {note}")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    report.status = ReportStatus.RESOLVED
    report.disposition = disposition
    report.resolution_note = note
    report.resolved_by_user_id = current_user.id
    report.resolved_at = datetime.now(timezone.utc)
    audit("CIVIC_REPORT_RESOLVED", "civic_issue", issue.id,
          {"report_id": str(report.id), "disposition": disposition.value})
    db.session.commit()
    return no_store({"report": _report_payload(report)})
