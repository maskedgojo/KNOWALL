"""Informal non-binding polls for eligible residents.

One signed-in eligible resident may respond once. Counts are hidden until
the poll closes. Voter identities are never returned. This is not formal voting.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog, User
from app.modules.identity.models.user import utc_now

from .models import Poll, PollOption, PollVote


polls_bp = Blueprint("polls", __name__)
participate = requires_permission("society.notices.read")
QUESTION_LIMIT = 200
OPTION_LIMIT = 80


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


def _status(poll: Poll, now: datetime) -> str:
    if now < _aware(poll.opens_at):
        return "SCHEDULED"
    if now >= _aware(poll.closes_at):
        return "CLOSED"
    return "OPEN"


def _when(value, field: str, problems: dict) -> datetime | None:
    if not isinstance(value, str):
        problems[field] = "Use a timezone-aware ISO timestamp."
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        problems[field] = "Use a timezone-aware ISO timestamp."
        return None
    if parsed.tzinfo is None:
        problems[field] = "Include a timezone."
        return None
    return parsed.astimezone(timezone.utc)


def _names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


def _options(poll_ids):
    if not poll_ids:
        return {}
    rows = db.session.scalars(
        select(PollOption).where(PollOption.poll_id.in_(poll_ids)).order_by(PollOption.position.asc(), PollOption.id.asc())
    ).all()
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.poll_id, []).append(row)
    return grouped


def _counts(poll_ids) -> dict:
    if not poll_ids:
        return {}
    rows = db.session.execute(
        select(PollVote.option_id, func.count()).where(PollVote.poll_id.in_(poll_ids)).group_by(PollVote.option_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _mine(poll_ids) -> dict:
    if not poll_ids:
        return {}
    rows = db.session.execute(
        select(PollVote.poll_id, PollVote.option_id).where(
            PollVote.poll_id.in_(poll_ids), PollVote.user_id == current_user.id
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def _json(poll: Poll, names: dict, options: list[PollOption], counts: dict, mine, now: datetime) -> dict:
    status = _status(poll, now)
    show_counts = status == "CLOSED"
    return {
        "id": str(poll.id),
        "society_id": poll.society_id,
        "question": poll.question,
        "binding": False,
        "status": status,
        "opens_at": _iso(poll.opens_at),
        "closes_at": _iso(poll.closes_at),
        "created_by_user_id": str(poll.created_by_user_id),
        "author_display_name": names.get(poll.created_by_user_id, ""),
        "created_at": _iso(poll.created_at),
        "my_option_id": str(mine) if mine else None,
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


def _find(poll_id, society_id: int) -> Poll | None:
    return db.session.scalar(select(Poll).where(Poll.id == poll_id, Poll.society_id == society_id))


@polls_bp.get("/api/polls")
@participate
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
        select(Poll).where(Poll.society_id == society.id).order_by(Poll.opens_at.desc(), Poll.id.desc()).limit(limit).offset(offset)
    ).all()
    now = utc_now()
    ids = [row.id for row in rows]
    closed_ids = [row.id for row in rows if _status(row, now) == "CLOSED"]
    options = _options(ids)
    names = _names(row.created_by_user_id for row in rows)
    counts = _counts(closed_ids)
    mine = _mine(ids)
    response = jsonify({
        "polls": [_json(row, names, options.get(row.id, []), counts, mine.get(row.id), now) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@polls_bp.post("/api/polls")
@participate
def create_poll():
    missing = schema_required("polls", "poll_options", "poll_votes")
    if missing:
        return missing
    body, failure = json_object({"question", "options", "opens_at", "closes_at"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    problems: dict = {}
    question = body.get("question")
    if not isinstance(question, str) or not 3 <= len(question.strip()) <= QUESTION_LIMIT:
        problems["question"] = f"Must contain 3 to {QUESTION_LIMIT} characters."
        question = None
    else:
        question = question.strip()
    raw_options = body.get("options")
    labels: list[str] = []
    if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 6:
        problems["options"] = "Provide 2 to 6 choices."
    else:
        for index, item in enumerate(raw_options):
            if not isinstance(item, str) or not 1 <= len(item.strip()) <= OPTION_LIMIT:
                problems["options"] = f"Each choice must contain 1 to {OPTION_LIMIT} characters."
                break
            labels.append(item.strip())
        if "options" not in problems and len(set(labels)) != len(labels):
            problems["options"] = "Choices must be different."
    opens_at = _when(body.get("opens_at"), "opens_at", problems)
    closes_at = _when(body.get("closes_at"), "closes_at", problems)
    now = utc_now()
    if opens_at and closes_at:
        if closes_at <= opens_at:
            problems["closes_at"] = "Closing time must be after opening time."
        elif opens_at < now - timedelta(minutes=2):
            problems["opens_at"] = "Opening time cannot be in the past."
        elif closes_at - opens_at > timedelta(days=14):
            problems["closes_at"] = "A poll can stay open for at most 14 days."
    if problems:
        return error("VALIDATION_ERROR", "Check the poll and try again.", 400, fields=problems)
    poll = Poll(
        society_id=society.id, question=question, opens_at=opens_at, closes_at=closes_at,
        created_by_user_id=current_user.id, created_at=now,
    )
    db.session.add(poll)
    db.session.flush()
    options = []
    for position, label in enumerate(labels, start=1):
        option = PollOption(poll_id=poll.id, label=label, position=position)
        db.session.add(option)
        options.append(option)
    db.session.flush()
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action="POLL_CREATED", entity_type="POLL", entity_id=poll.id,
        details={"question": poll.question, "binding": False},
    ))
    db.session.commit()
    names = _names([poll.created_by_user_id])
    return jsonify({"poll": _json(poll, names, options, {}, None, now)}), 201


@polls_bp.get("/api/polls/<uuid:poll_id>")
@participate
def get_poll(poll_id):
    missing = schema_required("polls", "poll_options", "poll_votes")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    poll = _find(poll_id, society.id)
    if poll is None:
        return error("POLL_NOT_FOUND", "Poll not found.", 404)
    now = utc_now()
    options = _options([poll.id]).get(poll.id, [])
    counts = _counts([poll.id]) if _status(poll, now) == "CLOSED" else {}
    mine = _mine([poll.id]).get(poll.id)
    names = _names([poll.created_by_user_id])
    response = jsonify({"poll": _json(poll, names, options, counts, mine, now)})
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@polls_bp.post("/api/polls/<uuid:poll_id>/votes")
@participate
def cast_poll_vote(poll_id):
    missing = schema_required("polls", "poll_options", "poll_votes")
    if missing:
        return missing
    body, failure = json_object({"option_id"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    poll = db.session.scalar(
        select(Poll).where(Poll.id == poll_id, Poll.society_id == society.id).with_for_update()
    )
    if poll is None:
        return error("POLL_NOT_FOUND", "Poll not found.", 404)
    raw_option = body.get("option_id")
    try:
        option_id = UUID(raw_option) if isinstance(raw_option, str) else None
    except ValueError:
        option_id = None
    if option_id is None:
        return error("VALIDATION_ERROR", "Choose one of the listed options.", 400, fields={"option_id": "Choose one of the listed options."})
    option = db.session.scalar(select(PollOption).where(PollOption.id == option_id, PollOption.poll_id == poll.id))
    if option is None:
        return error("OPTION_NOT_FOUND", "That choice is not part of this poll.", 404)
    now = utc_now()
    status = _status(poll, now)
    if status == "SCHEDULED":
        db.session.rollback()
        return error("POLL_NOT_OPEN", "This poll is not open yet.", 409)
    if status == "CLOSED":
        db.session.rollback()
        return error("POLL_CLOSED", "This poll is closed.", 409)
    already = db.session.scalar(
        select(PollVote.id).where(PollVote.poll_id == poll.id, PollVote.user_id == current_user.id)
    )
    if already is not None:
        db.session.rollback()
        return error("ALREADY_VOTED", "You have already responded to this poll.", 409)
    db.session.add(PollVote(poll_id=poll.id, option_id=option.id, user_id=current_user.id, created_at=now))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("ALREADY_VOTED", "You have already responded to this poll.", 409)
    return jsonify({"poll_id": str(poll.id), "my_option_id": str(option.id), "binding": False}), 201
