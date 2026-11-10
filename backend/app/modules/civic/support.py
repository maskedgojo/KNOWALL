"""Issue support: one verified identity, one support, enforced by a unique constraint."""
from flask import Blueprint
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.auth.routes import error

from .common import audit, no_store, schema_missing, supporter
from .models import CivicIssue, IssueSupport
from .service import COMMUNITY_STATES, IssueState, SUPPORTABLE_STATES, canonical_ids, serialize_issues, supporter_sets

support_bp = Blueprint("civic_support", __name__)


def _locked_issue(issue_id):
    return db.session.scalar(select(CivicIssue).where(CivicIssue.id == issue_id).with_for_update())


def _summary(issue):
    item = serialize_issues([issue], viewer_id=current_user.id, moderator=False)[0]
    return {"support_count": item["support_count"], "viewer_has_supported": item["viewer_has_supported"],
            "priority": item["priority"]}


def _visible_or_404(issue):
    if issue is None or issue.state not in COMMUNITY_STATES | {IssueState.MERGED}:
        db.session.rollback()
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    if issue.state not in SUPPORTABLE_STATES | {IssueState.MERGED}:
        db.session.rollback()
        return error("NOT_OPEN_FOR_SUPPORT", "Support opens once a coordinator has validated this issue.", 409)
    return None


@support_bp.post("/api/civic/issues/<uuid:issue_id>/support")
@supporter
def add_support(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = _locked_issue(issue_id)
    failure = _visible_or_404(issue)
    if failure:
        return failure
    if issue.state == IssueState.MERGED:
        canonical = canonical_ids([issue.id]).get(issue.id)
        db.session.rollback()
        return error(
            "ISSUE_MERGED", "This report was merged into another issue. Support that issue instead.", 409,
            fields={"canonical_issue_id": str(canonical)} if canonical else None,
        )
    if issue.creator_id == current_user.id:
        db.session.rollback()
        return error("OWN_ISSUE", "Your own report already counts. Ask neighbours to support it.", 409)
    if current_user.id in supporter_sets([issue.id]).get(issue.id, set()):
        db.session.rollback()
        return error("ALREADY_SUPPORTED", "You have already supported this issue.", 409)
    db.session.add(IssueSupport(issue_id=issue.id, user_id=current_user.id))
    try:
        db.session.flush()
    except IntegrityError:
        # A second session raced us; the unique constraint is the final authority.
        db.session.rollback()
        return error("ALREADY_SUPPORTED", "You have already supported this issue.", 409)
    audit("CIVIC_ISSUE_SUPPORTED", "civic_issue", issue.id)
    db.session.commit()
    return no_store(_summary(issue), 201)


@support_bp.delete("/api/civic/issues/<uuid:issue_id>/support")
@supporter
def remove_support(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue = _locked_issue(issue_id)
    failure = _visible_or_404(issue)
    if failure:
        return failure
    if issue.state != IssueState.VALIDATED:
        db.session.rollback()
        return error("INVALID_STATE", "Support can only be withdrawn before the issue is routed.", 409)
    row = db.session.scalar(select(IssueSupport).where(
        IssueSupport.issue_id == issue.id, IssueSupport.user_id == current_user.id))
    if row is None:
        db.session.rollback()
        return error("NOT_SUPPORTING", "You have not supported this issue directly.", 404)
    db.session.delete(row)
    audit("CIVIC_SUPPORT_WITHDRAWN", "civic_issue", issue.id)
    db.session.commit()
    return no_store(_summary(issue))
