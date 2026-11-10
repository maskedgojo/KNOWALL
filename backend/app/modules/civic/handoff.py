"""Hand-off of a validated, ready civic issue to Module 6 (authority resolution).

Module 5 sends a payload keyed by the stable canonical issue id and records the
`authority_case_id` Module 6 returns. Module 6 owns the case status afterwards;
this module only displays it and never keeps a competing copy.
"""
from datetime import datetime, timezone

from flask import Blueprint
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.identity.auth.routes import error

from . import priority
from .common import audit, iso, json_body, moderator, no_store, safe_text, schema_missing, validation_error
from .models import (
    ActorRole, CivicIssue, DuplicateLink, IssueEvidence, IssueHandoff, IssueState, RoutingStatus,
)
from .service import InvalidTransition, readiness, serialize_issues, supporter_sets, transition
from .issues import fetch_locked, invalid_state

handoff_bp = Blueprint("civic_handoff", __name__)


def build_payload(issue: CivicIssue, supporters: int, evidence: list[IssueEvidence]) -> dict:
    merged = [str(item) for item in db.session.scalars(
        select(DuplicateLink.duplicate_issue_id).where(DuplicateLink.canonical_issue_id == issue.id))]
    return {
        "canonical_issue_id": str(issue.id),
        "category": issue.category.value,
        "severity": issue.severity.value,
        "title": issue.title,
        "summary": issue.description,
        "location": {
            "locality_id": issue.locality_id, "latitude": issue.latitude, "longitude": issue.longitude,
            "address_hint": issue.address_hint,
        },
        "evidence": [{
            "evidence_id": str(row.id), "mime_type": row.mime_type, "caption": row.caption,
            "visibility": row.visibility.value,
        } for row in evidence],
        "community_support": supporters,
        "priority": priority.compute(issue, supporters),
        "merged_duplicate_issue_ids": merged,
        "validated_at": iso(issue.validated_at),
        "demonstration_data": True,
    }


def _handoff_json(row: IssueHandoff) -> dict:
    return {
        "id": str(row.id), "canonical_issue_id": str(row.canonical_issue_id),
        "routing_status": row.routing_status.value, "routed_at": iso(row.routed_at),
        "authority_case_id": row.authority_case_id, "acknowledged_at": iso(row.acknowledged_at),
        "payload": row.payload,
    }


@handoff_bp.post("/api/civic/issues/<uuid:issue_id>/route")
@moderator
def route_issue(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = fetch_locked(issue_id)
    if issue is None:
        db.session.rollback()
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    if db.session.scalar(select(IssueHandoff.id).where(IssueHandoff.canonical_issue_id == issue.id)):
        db.session.rollback()
        return error("ALREADY_ROUTED", "This issue was already handed off.", 409)
    supporters = len(supporter_sets([issue.id]).get(issue.id, set()))
    evidence = db.session.scalars(
        select(IssueEvidence).where(IssueEvidence.issue_id == issue.id).order_by(IssueEvidence.created_at)).all()
    unmet = readiness(issue, supporters, len(evidence))
    if unmet:
        db.session.rollback()
        return error("NOT_READY_FOR_ROUTING", "This issue does not meet the readiness criteria yet.", 409,
                     fields={f"criterion_{index + 1}": reason for index, reason in enumerate(unmet)})
    try:
        transition(issue, IssueState.READY_FOR_ROUTING, actor_id=current_user.id, role=ActorRole.MODERATOR,
                   reason="Readiness criteria met; handed off for routing.")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    row = IssueHandoff(
        canonical_issue_id=issue.id, routed_by_user_id=current_user.id,
        payload=build_payload(issue, supporters, evidence),
    )
    db.session.add(row)
    priority.record_snapshot(issue, supporters, "ROUTED")
    db.session.flush()
    audit("CIVIC_ISSUE_ROUTED", "civic_issue", issue.id, {"handoff_id": str(row.id)})
    db.session.commit()
    return no_store({
        "handoff": _handoff_json(row),
        "issue": serialize_issues([issue], viewer_id=current_user.id, moderator=True, detail=True)[0],
    }, 201)


def acknowledge_handoff(issue_id, authority_case_id: str) -> IssueHandoff:
    """Called when Module 6 creates a case. Idempotent for the same case id; caller commits.

    Raises LookupError if the issue was not routed, ValueError if a different case is already linked.
    """
    row = db.session.scalar(
        select(IssueHandoff).where(IssueHandoff.canonical_issue_id == issue_id).with_for_update())
    if row is None:
        raise LookupError("Issue has not been routed.")
    if row.authority_case_id and row.authority_case_id != authority_case_id:
        raise ValueError("A different authority case is already linked.")
    if row.authority_case_id is None:
        row.authority_case_id = authority_case_id
        row.routing_status = RoutingStatus.ACKNOWLEDGED
        row.acknowledged_at = datetime.now(timezone.utc)
    return row


@handoff_bp.post("/api/civic/issues/<uuid:issue_id>/handoff/acknowledge")
@moderator
def acknowledge_route(issue_id):
    """Demonstration intake acknowledgement until Module 6 calls `acknowledge_handoff` itself."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"authority_case_id"})
    if failure:
        return failure
    problems: dict = {}
    case_id = safe_text(body.get("authority_case_id"), "authority_case_id", 3, 64, problems)
    if problems:
        return validation_error(problems)
    try:
        row = acknowledge_handoff(issue_id, case_id)
    except LookupError:
        db.session.rollback()
        return error("HANDOFF_NOT_FOUND", "This issue has not been routed.", 404)
    except ValueError as exc:
        db.session.rollback()
        return error("CASE_ALREADY_LINKED", str(exc), 409)
    audit("CIVIC_HANDOFF_ACKNOWLEDGED", "civic_issue", issue_id, {"authority_case_id": case_id})
    db.session.commit()
    return no_store({"handoff": _handoff_json(row)})
