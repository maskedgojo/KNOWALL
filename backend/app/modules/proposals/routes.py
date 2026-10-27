"""Proposal submission without ballots or results.

Formal voting is not accepted. Status stays SUBMITTED.
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog, User
from app.modules.identity.models.user import utc_now

from .models import Proposal, ProposalStatus


proposals_bp = Blueprint("proposals", __name__)
participate = requires_permission("society.notices.read")


def _iso(value):
    if value is None:
        return None
    if value.tzinfo is None:
        from datetime import timezone
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _pagination():
    try:
        limit = int(request.args.get("limit", "30"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def _text(value, field, minimum, maximum, problems):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    return value.strip()


def _names(user_ids):
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


def _json(proposal: Proposal, names: dict) -> dict:
    return {
        "id": str(proposal.id),
        "society_id": proposal.society_id,
        "title": proposal.title,
        "summary": proposal.summary,
        "status": proposal.status.value,
        "voting_open": False,
        "created_by_user_id": str(proposal.created_by_user_id),
        "author_display_name": names.get(proposal.created_by_user_id, ""),
        "created_at": _iso(proposal.created_at),
        "updated_at": _iso(proposal.updated_at),
    }


@proposals_bp.get("/api/proposals")
@participate
def list_proposals():
    missing = schema_required("proposals")
    if missing:
        return missing
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(
        select(Proposal).where(Proposal.society_id == society.id).order_by(Proposal.created_at.desc(), Proposal.id.desc()).limit(limit).offset(offset)
    ).all()
    names = _names(row.created_by_user_id for row in rows)
    response = jsonify({
        "proposals": [_json(row, names) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@proposals_bp.post("/api/proposals")
@participate
def create_proposal():
    missing = schema_required("proposals")
    if missing:
        return missing
    body, failure = json_object({"title", "summary"})
    if failure:
        return failure
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    problems: dict = {}
    title = _text(body.get("title"), "title", 3, 160, problems)
    summary = _text(body.get("summary"), "summary", 1, 8000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the proposal and try again.", 400, fields=problems)
    now = utc_now()
    proposal = Proposal(
        society_id=society.id, title=title, summary=summary, status=ProposalStatus.SUBMITTED,
        created_by_user_id=current_user.id, created_at=now, updated_at=now,
    )
    db.session.add(proposal)
    db.session.flush()
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action="PROPOSAL_SUBMITTED", entity_type="PROPOSAL",
        entity_id=proposal.id, details={"title": proposal.title, "status": "SUBMITTED", "voting_open": False},
    ))
    db.session.commit()
    return jsonify({"proposal": _json(proposal, _names([proposal.created_by_user_id]))}), 201


@proposals_bp.get("/api/proposals/<uuid:proposal_id>")
@participate
def get_proposal(proposal_id):
    missing = schema_required("proposals")
    if missing:
        return missing
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    proposal = db.session.scalar(select(Proposal).where(Proposal.id == proposal_id, Proposal.society_id == society.id))
    if proposal is None:
        return error("PROPOSAL_NOT_FOUND", "Proposal not found.", 404)
    response = jsonify({"proposal": _json(proposal, _names([proposal.created_by_user_id]))})
    response.headers["Cache-Control"] = "no-store"
    return response, 200
