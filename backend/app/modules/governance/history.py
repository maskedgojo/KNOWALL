"""Resident view of society governance events already stored in audit_logs.

Only events tied to a record in the configured society are returned, and only
when that record is already visible to an eligible resident or was a published
notice. Raw audit details, actors, and identity events are not copied through.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy import and_, or_, select

from app.extensions import db
from app.modules.discussions.models import Discussion
from app.modules.governance.schema import tables_present
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.models import AuditLog
from app.modules.identity.models.user import utc_now
from app.modules.notices.models import Notice, NoticeStatus
from app.modules.polls.models import Poll
from app.modules.proposals.models import Proposal
from app.modules.suggestions.models import Suggestion


history_bp = Blueprint("governance_history", __name__)
read_history = requires_permission("society.notices.read")


def _pagination():
    try:
        limit = int(request.args.get("limit", "30"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _notice_readable(notice: Notice, now: datetime) -> bool:
    expires = _aware(notice.expires_at)
    return notice.status == NoticeStatus.PUBLISHED and (expires is None or expires > now)


def _summary(action: str, title: str, category: str | None = None) -> str:
    if action == "NOTICE_PUBLISHED":
        return f'Published notice "{title}".'
    if action == "NOTICE_ARCHIVED":
        return f'Archived notice "{title}".'
    if action == "DISCUSSION_CREATED":
        return f'Started discussion "{title}".'
    if action == "COMMENT_CREATED":
        return f'Comment added on "{title}".'
    if action == "POLL_CREATED":
        return f'Informal non-binding poll created: "{title}".'
    if action == "PROPOSAL_SUBMITTED":
        return f'Proposal submitted. Formal voting is not open: "{title}".'
    if action == "PROPOSAL_DECIDED":
        return f'Society Admin {(category or "decided").lower()} proposal "{title}".'
    label = category.replace("_", " ").title() if category else "General"
    return f'Suggestion submitted: "{title}" ({label}).'


@history_bp.get("/api/governance/history")
@read_history
def governance_history():
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    clauses = []
    if tables_present("notices"):
        notice_ids = select(Notice.id).where(Notice.society_id == society.id)
        published_notice_ids = select(Notice.id).where(
            Notice.society_id == society.id, Notice.published_at.is_not(None)
        )
        clauses.append(and_(AuditLog.action == "NOTICE_PUBLISHED", AuditLog.entity_type == "NOTICE", AuditLog.entity_id.in_(notice_ids)))
        clauses.append(and_(AuditLog.action == "NOTICE_ARCHIVED", AuditLog.entity_type == "NOTICE", AuditLog.entity_id.in_(published_notice_ids)))
    if tables_present("discussions"):
        discussion_ids = select(Discussion.id).where(
            Discussion.society_id == society.id, Discussion.hidden_at.is_(None)
        )
        clauses.append(and_(AuditLog.action == "DISCUSSION_CREATED", AuditLog.entity_type == "DISCUSSION", AuditLog.entity_id.in_(discussion_ids)))
        clauses.append(and_(AuditLog.action == "COMMENT_CREATED", AuditLog.entity_type == "DISCUSSION", AuditLog.entity_id.in_(discussion_ids)))
    if tables_present("suggestions"):
        suggestion_ids = select(Suggestion.id).where(Suggestion.society_id == society.id)
        clauses.append(and_(AuditLog.action == "SUGGESTION_CREATED", AuditLog.entity_type == "SUGGESTION", AuditLog.entity_id.in_(suggestion_ids)))
    if tables_present("polls"):
        poll_ids = select(Poll.id).where(Poll.society_id == society.id)
        clauses.append(and_(AuditLog.action == "POLL_CREATED", AuditLog.entity_type == "POLL", AuditLog.entity_id.in_(poll_ids)))
    if tables_present("proposals"):
        proposal_ids = select(Proposal.id).where(Proposal.society_id == society.id)
        clauses.append(and_(AuditLog.action.in_(("PROPOSAL_SUBMITTED", "PROPOSAL_DECIDED")), AuditLog.entity_type == "PROPOSAL", AuditLog.entity_id.in_(proposal_ids)))
    if not clauses:
        response = jsonify({"events": [], "pagination": {"limit": limit, "offset": offset}})
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    rows = db.session.scalars(
        select(AuditLog)
        .where(or_(*clauses))
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    now = utc_now()
    events = []
    for row in rows:
        resource_path = None
        if row.entity_type == "NOTICE":
            notice = db.session.get(Notice, row.entity_id)
            if notice is None or notice.society_id != society.id:
                continue
            title = notice.title
            category = None
            if row.action == "NOTICE_PUBLISHED" and _notice_readable(notice, now):
                resource_path = f"/notices/{notice.id}"
        elif row.entity_type == "DISCUSSION":
            discussion = db.session.get(Discussion, row.entity_id)
            if discussion is None or discussion.society_id != society.id:
                continue
            title = discussion.title
            category = None
            resource_path = f"/discussions/{discussion.id}"
        elif row.entity_type == "SUGGESTION":
            suggestion = db.session.get(Suggestion, row.entity_id)
            if suggestion is None or suggestion.society_id != society.id:
                continue
            title = suggestion.title
            category = suggestion.category.value
            resource_path = f"/suggestions/{suggestion.id}"
        elif row.entity_type == "POLL":
            poll = db.session.get(Poll, row.entity_id)
            if poll is None or poll.society_id != society.id:
                continue
            title = poll.question
            category = None
            resource_path = f"/polls/{poll.id}"
        elif row.entity_type == "PROPOSAL":
            proposal = db.session.get(Proposal, row.entity_id)
            if proposal is None or proposal.society_id != society.id:
                continue
            title = proposal.title
            category = proposal.status.value if row.action == "PROPOSAL_DECIDED" else None
            resource_path = f"/proposals/{proposal.id}"
        else:
            continue
        occurred = _aware(row.created_at)
        events.append({
            "id": str(row.id),
            "occurred_at": occurred.isoformat() if occurred else None,
            "event_type": row.action,
            "summary": _summary(row.action, title, category),
            "resource_path": resource_path,
        })
    response = jsonify({
        "events": events,
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200
