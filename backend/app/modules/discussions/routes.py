"""Resident discussions and threaded comments.

Participation uses the existing eligible-resident permission
`society.notices.read`. No discussion-specific permission is registered.
The society id comes from the singleton profile. Audit details omit post
and comment text. Discussions hidden by a Society Admin are treated as not
found here; moderation lives in governance/activity.py.
"""
from uuid import UUID

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import func, select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog, User
from app.modules.identity.models.user import utc_now

from .models import Discussion, DiscussionComment


discussions_bp = Blueprint("discussions", __name__)
participate = requires_permission("society.notices.read")
TITLE_LIMIT = 160
BODY_LIMIT = 8000
COMMENT_LIMIT = 4000


def _iso(value) -> str | None:
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


def _society():
    profile = configured_society()
    if profile is None:
        return None, error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    return profile, None


def _text(value, field: str, minimum: int, maximum: int, problems: dict) -> str | None:
    if not isinstance(value, str):
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    return cleaned


def _optional_uuid(value, field: str, problems: dict):
    if value is None:
        return None
    if not isinstance(value, str):
        problems[field] = "Use a comment id or null."
        return None
    try:
        return UUID(value)
    except ValueError:
        problems[field] = "Use a comment id or null."
        return None


def _names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(
        select(User.id, User.display_name).where(User.id.in_(identifiers))
    ).all()
    return {row[0]: row[1] for row in rows}


def _discussion_json(discussion: Discussion, names: dict, comment_count: int) -> dict:
    return {
        "id": str(discussion.id),
        "society_id": discussion.society_id,
        "title": discussion.title,
        "body": discussion.body,
        "created_by_user_id": str(discussion.created_by_user_id),
        "author_display_name": names.get(discussion.created_by_user_id, ""),
        "created_at": _iso(discussion.created_at),
        "updated_at": _iso(discussion.updated_at),
        "comment_count": comment_count,
    }


def _comment_json(comment: DiscussionComment, names: dict) -> dict:
    return {
        "id": str(comment.id),
        "discussion_id": str(comment.discussion_id),
        "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
        "body": comment.body,
        "created_by_user_id": str(comment.created_by_user_id),
        "author_display_name": names.get(comment.created_by_user_id, ""),
        "created_at": _iso(comment.created_at),
    }


def _counts(discussion_ids) -> dict:
    if not discussion_ids:
        return {}
    rows = db.session.execute(
        select(DiscussionComment.discussion_id, func.count())
        .where(DiscussionComment.discussion_id.in_(discussion_ids))
        .group_by(DiscussionComment.discussion_id)
    ).all()
    return {row[0]: row[1] for row in rows}


def _audit(action: str, entity_id, details: dict) -> None:
    db.session.add(AuditLog(
        actor_user_id=current_user.id,
        action=action,
        entity_type="DISCUSSION",
        entity_id=entity_id,
        details=details,
    ))


def _find(discussion_id, society_id: int) -> Discussion | None:
    return db.session.scalar(
        select(Discussion).where(
            Discussion.id == discussion_id,
            Discussion.society_id == society_id,
            Discussion.hidden_at.is_(None),
        )
    )


@discussions_bp.get("/api/discussions")
@participate
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
        .where(Discussion.society_id == society.id, Discussion.hidden_at.is_(None))
        .order_by(Discussion.updated_at.desc(), Discussion.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    names = _names(row.created_by_user_id for row in rows)
    counts = _counts([row.id for row in rows])
    response = jsonify({
        "discussions": [_discussion_json(row, names, counts.get(row.id, 0)) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@discussions_bp.post("/api/discussions")
@participate
def create_discussion():
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    body, failure = json_object({"title", "body"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    problems: dict = {}
    title = _text(body.get("title"), "title", 3, TITLE_LIMIT, problems)
    text = _text(body.get("body"), "body", 1, BODY_LIMIT, problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the discussion and try again.", 400, fields=problems)
    now = utc_now()
    discussion = Discussion(
        society_id=society.id,
        title=title,
        body=text,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(discussion)
    db.session.flush()
    _audit("DISCUSSION_CREATED", discussion.id, {"title": discussion.title})
    db.session.commit()
    names = _names([discussion.created_by_user_id])
    return jsonify({"discussion": _discussion_json(discussion, names, 0)}), 201


@discussions_bp.get("/api/discussions/<uuid:discussion_id>")
@participate
def get_discussion(discussion_id):
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    society, failure = _society()
    if failure:
        return failure
    discussion = _find(discussion_id, society.id)
    if discussion is None:
        return error("DISCUSSION_NOT_FOUND", "Discussion not found.", 404)
    comments = db.session.scalars(
        select(DiscussionComment)
        .where(DiscussionComment.discussion_id == discussion.id)
        .order_by(DiscussionComment.created_at.asc(), DiscussionComment.id.asc())
    ).all()
    names = _names([discussion.created_by_user_id, *(comment.created_by_user_id for comment in comments)])
    response = jsonify({
        "discussion": _discussion_json(discussion, names, len(comments)),
        "comments": [_comment_json(comment, names) for comment in comments],
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@discussions_bp.post("/api/discussions/<uuid:discussion_id>/comments")
@participate
def create_comment(discussion_id):
    missing = schema_required("discussions", "discussion_comments")
    if missing:
        return missing
    body, failure = json_object({"body", "parent_comment_id"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    discussion = _find(discussion_id, society.id)
    if discussion is None:
        return error("DISCUSSION_NOT_FOUND", "Discussion not found.", 404)
    problems: dict = {}
    text = _text(body.get("body"), "body", 1, COMMENT_LIMIT, problems)
    parent_id = _optional_uuid(body.get("parent_comment_id"), "parent_comment_id", problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the comment and try again.", 400, fields=problems)
    if parent_id is not None:
        parent = db.session.get(DiscussionComment, parent_id)
        if parent is None:
            return error("COMMENT_NOT_FOUND", "Comment not found.", 404)
        if parent.discussion_id != discussion.id:
            return error("COMMENT_PARENT_MISMATCH", "A reply must stay in the same discussion.", 409)
    now = utc_now()
    comment = DiscussionComment(
        discussion_id=discussion.id,
        parent_comment_id=parent_id,
        body=text,
        created_by_user_id=current_user.id,
        created_at=now,
    )
    discussion.updated_at = now
    db.session.add(comment)
    db.session.flush()
    _audit("COMMENT_CREATED", discussion.id, {
        "comment_id": str(comment.id),
        "parent_comment_id": str(parent_id) if parent_id else None,
    })
    db.session.commit()
    names = _names([comment.created_by_user_id])
    return jsonify({"comment": _comment_json(comment, names)}), 201
