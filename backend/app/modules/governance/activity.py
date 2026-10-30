"""Society Admin view and moderation of public community records.

Uses the existing society.notices.manage grant, which is limited to a verified
Society Admin. Responses omit resident ids, voter identities, individual poll
responses, raw audit payloads, and private disputes (see disputes/routes.py).

Admin actions: hide/restore a discussion (soft, reversible) and record one
APPROVED/REJECTED decision on a SUBMITTED proposal. Neither opens voting.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func, select

from app.extensions import db
from app.modules.discussions.models import Discussion, DiscussionComment
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog, User
from app.modules.identity.models.user import utc_now
from app.modules.polls.models import Poll, PollOption, PollVote
from app.modules.proposals.models import Proposal, ProposalStatus
from app.modules.suggestions.models import Suggestion


activity_bp = Blueprint("community_activity", __name__)
review_activity = requires_permission("society.notices.manage")


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware(value).isoformat()


def _pagination():
    try:
        limit = int(request.args.get("limit", "30"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def _society():
    profile = configured_society()
    if profile is None:
        return None, error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    return profile, None


def _names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


def _poll_status(poll: Poll, now: datetime) -> str:
    if now < _aware(poll.opens_at):
        return "SCHEDULED"
    if now >= _aware(poll.closes_at):
        return "CLOSED"
    return "OPEN"


def _store(payload, status=200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status


def _discussion_json(discussion: Discussion, names: dict, comment_count: int) -> dict:
    return {
        "id": str(discussion.id),
        "title": discussion.title,
        "body": discussion.body,
        "author_display_name": names.get(discussion.created_by_user_id, ""),
        "created_at": _iso(discussion.created_at),
        "updated_at": _iso(discussion.updated_at),
        "comment_count": comment_count,
        "hidden": discussion.hidden_at is not None,
        "hidden_at": _iso(discussion.hidden_at),
        "hidden_reason": discussion.hidden_reason,
        "hidden_by_display_name": names.get(discussion.hidden_by_user_id) if discussion.hidden_by_user_id else None,
    }


def _comment_json(comment: DiscussionComment, names: dict) -> dict:
    return {
        "id": str(comment.id),
        "discussion_id": str(comment.discussion_id),
        "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
        "body": comment.body,
        "author_display_name": names.get(comment.created_by_user_id, ""),
        "created_at": _iso(comment.created_at),
    }


def _suggestion_json(suggestion: Suggestion, names: dict) -> dict:
    return {
        "id": str(suggestion.id),
        "title": suggestion.title,
        "description": suggestion.description,
        "category": suggestion.category.value,
        "status": suggestion.status.value,
        "author_display_name": names.get(suggestion.created_by_user_id, ""),
        "created_at": _iso(suggestion.created_at),
        "updated_at": _iso(suggestion.updated_at),
    }


def _proposal_json(proposal: Proposal, names: dict) -> dict:
    return {
        "id": str(proposal.id),
        "title": proposal.title,
        "summary": proposal.summary,
        "status": proposal.status.value,
        "voting_open": False,
        "author_display_name": names.get(proposal.created_by_user_id, ""),
        "created_at": _iso(proposal.created_at),
        "updated_at": _iso(proposal.updated_at),
        "decided_at": _iso(proposal.decided_at),
        "decision_note": proposal.decision_note,
        "decided_by_display_name": names.get(proposal.decided_by_user_id) if proposal.decided_by_user_id else None,
    }


def _poll_json(poll: Poll, names: dict, options: list[PollOption], counts: dict, now: datetime) -> dict:
    status = _poll_status(poll, now)
    show_counts = status == "CLOSED"
    return {
        "id": str(poll.id),
        "question": poll.question,
        "binding": False,
        "status": status,
        "opens_at": _iso(poll.opens_at),
        "closes_at": _iso(poll.closes_at),
        "author_display_name": names.get(poll.created_by_user_id, ""),
        "options": [
            {
                "id": str(option.id),
                "label": option.label,
                "position": option.position,
                "vote_count": counts.get(option.id, 0) if show_counts else None,
            }
            for option in options
        ],
    }


def _comment_counts(discussion_ids) -> dict:
    if not discussion_ids:
        return {}
    rows = db.session.execute(
        select(DiscussionComment.discussion_id, func.count())
        .where(DiscussionComment.discussion_id.in_(discussion_ids))
        .group_by(DiscussionComment.discussion_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _poll_options(poll_ids) -> dict:
    if not poll_ids:
        return {}
    rows = db.session.scalars(
        select(PollOption).where(PollOption.poll_id.in_(poll_ids)).order_by(PollOption.position.asc(), PollOption.id.asc())
    ).all()
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.poll_id, []).append(row)
    return grouped


def _poll_counts(poll_ids) -> dict:
    if not poll_ids:
        return {}
    rows = db.session.execute(
        select(PollVote.option_id, func.count()).where(PollVote.poll_id.in_(poll_ids)).group_by(PollVote.option_id)
    ).all()
    return {row[0]: row[1] for row in rows}


@activity_bp.get("/api/admin/community/discussions")
@review_activity
def list_discussions():
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(
        select(Discussion)
        .where(Discussion.society_id == society.id)
        .order_by(Discussion.updated_at.desc(), Discussion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = _names([*(row.created_by_user_id for row in rows), *(row.hidden_by_user_id for row in rows)])
    counts = _comment_counts([row.id for row in rows])
    return _store({
        "discussions": [_discussion_json(row, names, counts.get(row.id, 0)) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })


@activity_bp.get("/api/admin/community/discussions/<uuid:discussion_id>")
@review_activity
def get_discussion(discussion_id):
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    discussion = db.session.scalar(
        select(Discussion).where(Discussion.id == discussion_id, Discussion.society_id == society.id)
    )
    if discussion is None:
        return error("DISCUSSION_NOT_FOUND", "Discussion not found.", 404)
    comments = db.session.scalars(
        select(DiscussionComment)
        .where(DiscussionComment.discussion_id == discussion.id)
        .order_by(DiscussionComment.created_at.asc(), DiscussionComment.id.asc())
    ).all()
    names = _names([discussion.created_by_user_id, discussion.hidden_by_user_id, *(comment.created_by_user_id for comment in comments)])
    return _store({
        "discussion": _discussion_json(discussion, names, len(comments)),
        "comments": [_comment_json(comment, names) for comment in comments],
    })


@activity_bp.get("/api/admin/community/suggestions")
@review_activity
def list_suggestions():
    missing = schema_required("suggestions")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(
        select(Suggestion)
        .where(Suggestion.society_id == society.id)
        .order_by(Suggestion.created_at.desc(), Suggestion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = _names(row.created_by_user_id for row in rows)
    return _store({
        "suggestions": [_suggestion_json(row, names) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })


@activity_bp.get("/api/admin/community/suggestions/<uuid:suggestion_id>")
@review_activity
def get_suggestion(suggestion_id):
    missing = schema_required("suggestions")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    suggestion = db.session.scalar(
        select(Suggestion).where(Suggestion.id == suggestion_id, Suggestion.society_id == society.id)
    )
    if suggestion is None:
        return error("SUGGESTION_NOT_FOUND", "Suggestion not found.", 404)
    names = _names([suggestion.created_by_user_id])
    return _store({"suggestion": _suggestion_json(suggestion, names)})


@activity_bp.get("/api/admin/community/polls")
@review_activity
def list_polls():
    missing = schema_required("polls", "poll_options", "poll_votes")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(
        select(Poll)
        .where(Poll.society_id == society.id)
        .order_by(Poll.opens_at.desc(), Poll.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    now = utc_now()
    closed_ids = [row.id for row in rows if _poll_status(row, now) == "CLOSED"]
    options = _poll_options([row.id for row in rows])
    counts = _poll_counts(closed_ids)
    names = _names(row.created_by_user_id for row in rows)
    return _store({
        "polls": [_poll_json(row, names, options.get(row.id, []), counts, now) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })


@activity_bp.get("/api/admin/community/polls/<uuid:poll_id>")
@review_activity
def get_poll(poll_id):
    missing = schema_required("polls", "poll_options", "poll_votes")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    poll = db.session.scalar(select(Poll).where(Poll.id == poll_id, Poll.society_id == society.id))
    if poll is None:
        return error("POLL_NOT_FOUND", "Poll not found.", 404)
    now = utc_now()
    options = _poll_options([poll.id]).get(poll.id, [])
    counts = _poll_counts([poll.id]) if _poll_status(poll, now) == "CLOSED" else {}
    names = _names([poll.created_by_user_id])
    return _store({"poll": _poll_json(poll, names, options, counts, now)})


@activity_bp.get("/api/admin/community/proposals")
@review_activity
def list_proposals():
    missing = schema_required("proposals")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(
        select(Proposal)
        .where(Proposal.society_id == society.id)
        .order_by(Proposal.created_at.desc(), Proposal.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = _names([*(row.created_by_user_id for row in rows), *(row.decided_by_user_id for row in rows)])
    return _store({
        "proposals": [_proposal_json(row, names) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })


@activity_bp.get("/api/admin/community/proposals/<uuid:proposal_id>")
@review_activity
def get_proposal(proposal_id):
    missing = schema_required("proposals")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    proposal = db.session.scalar(
        select(Proposal).where(Proposal.id == proposal_id, Proposal.society_id == society.id)
    )
    if proposal is None:
        return error("PROPOSAL_NOT_FOUND", "Proposal not found.", 404)
    names = _names([proposal.created_by_user_id, proposal.decided_by_user_id])
    return _store({"proposal": _proposal_json(proposal, names)})


def _audit(action: str, entity_type: str, entity_id, details: dict) -> None:
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    ))


def _optional_note(value, field: str, maximum: int, problems: dict) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str) or len(value.strip()) > maximum:
        problems[field] = f"Must contain at most {maximum} characters."
        return None
    return value.strip()


def _moderated_discussion(discussion_id, society_id: int) -> Discussion | None:
    return db.session.scalar(
        select(Discussion).where(Discussion.id == discussion_id, Discussion.society_id == society_id)
    )


@activity_bp.post("/api/admin/community/discussions/<uuid:discussion_id>/hide")
@review_activity
def hide_discussion(discussion_id):
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    body, failure = json_object({"reason"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    reason = body.get("reason")
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 500:
        return error("VALIDATION_ERROR", "Give a reason for hiding this discussion.", 400,
                     fields={"reason": "Must contain 3 to 500 characters."})
    discussion = _moderated_discussion(discussion_id, society.id)
    if discussion is None:
        return error("DISCUSSION_NOT_FOUND", "Discussion not found.", 404)
    if discussion.hidden_at is not None:
        return error("DISCUSSION_ALREADY_HIDDEN", "This discussion is already hidden.", 409)
    discussion.hidden_at = utc_now()
    discussion.hidden_by_user_id = current_user.id
    discussion.hidden_reason = reason.strip()
    _audit("DISCUSSION_HIDDEN", "DISCUSSION", discussion.id, {"reason": discussion.hidden_reason})
    db.session.commit()
    names = _names([discussion.created_by_user_id, discussion.hidden_by_user_id])
    count = _comment_counts([discussion.id]).get(discussion.id, 0)
    return _store({"discussion": _discussion_json(discussion, names, count)})


@activity_bp.post("/api/admin/community/discussions/<uuid:discussion_id>/restore")
@review_activity
def restore_discussion(discussion_id):
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    discussion = _moderated_discussion(discussion_id, society.id)
    if discussion is None:
        return error("DISCUSSION_NOT_FOUND", "Discussion not found.", 404)
    if discussion.hidden_at is None:
        return error("DISCUSSION_NOT_HIDDEN", "This discussion is not hidden.", 409)
    discussion.hidden_at = None
    discussion.hidden_by_user_id = None
    discussion.hidden_reason = None
    _audit("DISCUSSION_RESTORED", "DISCUSSION", discussion.id, {})
    db.session.commit()
    names = _names([discussion.created_by_user_id])
    count = _comment_counts([discussion.id]).get(discussion.id, 0)
    return _store({"discussion": _discussion_json(discussion, names, count)})


@activity_bp.post("/api/admin/community/proposals/<uuid:proposal_id>/decision")
@review_activity
def decide_proposal(proposal_id):
    missing = schema_required("proposals")
    if missing:
        return missing
    body, failure = json_object({"decision", "note"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    problems: dict = {}
    decision = body.get("decision")
    if decision not in (ProposalStatus.APPROVED.value, ProposalStatus.REJECTED.value):
        problems["decision"] = "Use APPROVED or REJECTED."
    note = _optional_note(body.get("note"), "note", 1000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the decision and try again.", 400, fields=problems)
    proposal = db.session.scalar(
        select(Proposal).where(Proposal.id == proposal_id, Proposal.society_id == society.id).with_for_update()
    )
    if proposal is None:
        return error("PROPOSAL_NOT_FOUND", "Proposal not found.", 404)
    if proposal.status != ProposalStatus.SUBMITTED:
        return error("PROPOSAL_ALREADY_DECIDED", "A decision is already recorded for this proposal.", 409)
    now = utc_now()
    proposal.status = ProposalStatus(decision)
    proposal.decided_at = now
    proposal.decided_by_user_id = current_user.id
    proposal.decision_note = note
    proposal.updated_at = now
    _audit("PROPOSAL_DECIDED", "PROPOSAL", proposal.id,
           {"title": proposal.title, "status": proposal.status.value, "voting_open": False})
    db.session.commit()
    names = _names([proposal.created_by_user_id, proposal.decided_by_user_id])
    return _store({"proposal": _proposal_json(proposal, names)})
