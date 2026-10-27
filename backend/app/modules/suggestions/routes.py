"""Resident suggestion list and submission.

Eligible residents use the existing `society.notices.read` permission.
The server sets status to SUBMITTED. Clients cannot choose a society,
author, timestamp, or status. No committee decision route is registered.
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

from .models import Suggestion, SuggestionCategory, SuggestionStatus


suggestions_bp = Blueprint("suggestions", __name__)
read_suggestions = requires_permission("society.notices.read")
TITLE_LIMIT = 160
DESCRIPTION_LIMIT = 8000
CATEGORIES = {item.value for item in SuggestionCategory}


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


def _names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(
        select(User.id, User.display_name).where(User.id.in_(identifiers))
    ).all()
    return {row[0]: row[1] for row in rows}


def _json(suggestion: Suggestion, names: dict) -> dict:
    return {
        "id": str(suggestion.id),
        "society_id": suggestion.society_id,
        "title": suggestion.title,
        "description": suggestion.description,
        "category": suggestion.category.value,
        "status": suggestion.status.value,
        "created_by_user_id": str(suggestion.created_by_user_id),
        "author_display_name": names.get(suggestion.created_by_user_id, ""),
        "created_at": _iso(suggestion.created_at),
        "updated_at": _iso(suggestion.updated_at),
    }


@suggestions_bp.get("/api/suggestions")
@read_suggestions
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
    response = jsonify({
        "suggestions": [_json(row, names) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@suggestions_bp.post("/api/suggestions")
@read_suggestions
def create_suggestion():
    missing = schema_required("suggestions")
    if missing:
        return missing
    body, failure = json_object({"title", "description", "category"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    problems: dict = {}
    title = _text(body.get("title"), "title", 3, TITLE_LIMIT, problems)
    description = _text(body.get("description"), "description", 1, DESCRIPTION_LIMIT, problems)
    category = body.get("category")
    if category not in CATEGORIES:
        problems["category"] = "Choose a listed category."
    if problems:
        return error("VALIDATION_ERROR", "Check the suggestion and try again.", 400, fields=problems)
    now = utc_now()
    suggestion = Suggestion(
        society_id=society.id,
        title=title,
        description=description,
        category=SuggestionCategory(category),
        status=SuggestionStatus.SUBMITTED,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(suggestion)
    db.session.flush()
    db.session.add(AuditLog(
        actor_user_id=current_user.id,
        action="SUGGESTION_CREATED",
        entity_type="SUGGESTION",
        entity_id=suggestion.id,
        details={"title": suggestion.title, "category": suggestion.category.value, "status": suggestion.status.value},
    ))
    db.session.commit()
    names = _names([suggestion.created_by_user_id])
    return jsonify({"suggestion": _json(suggestion, names)}), 201


@suggestions_bp.get("/api/suggestions/<uuid:suggestion_id>")
@read_suggestions
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
    response = jsonify({"suggestion": _json(suggestion, names)})
    response.headers["Cache-Control"] = "no-store"
    return response, 200
