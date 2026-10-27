"""Official notice management and society-wide resident reads.

The society id always comes from the singleton society profile. Published
title, body, and expiry cannot be edited. A correction is a new draft that
records the notice it replaces. Expiry is checked on read and does not archive.
"""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog
from app.modules.identity.models.user import utc_now

from .models import Notice, NoticeStatus


notices_bp = Blueprint("notices", __name__)
manage_notices = requires_permission("society.notices.manage")
read_notices = requires_permission("society.notices.read")
TITLE_LIMIT = 160
BODY_LIMIT = 8000


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware else None


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


def _visible(notice: Notice, now: datetime) -> bool:
    expires = _aware(notice.expires_at)
    return notice.status == NoticeStatus.PUBLISHED and (expires is None or expires > now)


def _serialize(notice: Notice, now: datetime | None = None) -> dict:
    moment = now or utc_now()
    return {
        "id": str(notice.id),
        "society_id": notice.society_id,
        "title": notice.title,
        "body": notice.body,
        "status": notice.status.value,
        "expires_at": _iso(notice.expires_at),
        "published_at": _iso(notice.published_at),
        "archived_at": _iso(notice.archived_at),
        "replaces_notice_id": str(notice.replaces_notice_id) if notice.replaces_notice_id else None,
        "created_by_user_id": str(notice.created_by_user_id),
        "published_by_user_id": str(notice.published_by_user_id) if notice.published_by_user_id else None,
        "archived_by_user_id": str(notice.archived_by_user_id) if notice.archived_by_user_id else None,
        "created_at": _iso(notice.created_at),
        "updated_at": _iso(notice.updated_at),
        "visible_to_residents": _visible(notice, moment),
    }


def _audit(action: str, notice: Notice, details: dict) -> None:
    db.session.add(AuditLog(
        actor_user_id=current_user.id,
        action=action,
        entity_type="NOTICE",
        entity_id=notice.id,
        details=details,
    ))


def _audit_details(notice: Notice, **extra) -> dict:
    details = {
        "title": notice.title,
        "status": notice.status.value,
        "expires_at": _iso(notice.expires_at),
        "replaces_notice_id": str(notice.replaces_notice_id) if notice.replaces_notice_id else None,
    }
    details.update(extra)
    return details


def _text(value, field: str, minimum: int, maximum: int, problems: dict) -> str | None:
    if not isinstance(value, str):
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    cleaned = value.strip()
    if not minimum <= len(cleaned) <= maximum:
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    return cleaned


def _expiry(value, problems: dict) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        problems["expires_at"] = "Use a timezone-aware ISO timestamp or null."
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        problems["expires_at"] = "Use a timezone-aware ISO timestamp or null."
        return None
    if parsed.tzinfo is None:
        problems["expires_at"] = "Expiry must include a timezone."
        return None
    return parsed.astimezone(timezone.utc)


def _content(body: dict, *, require_text: bool) -> tuple[dict, dict]:
    problems: dict = {}
    parsed: dict = {}
    if require_text or "title" in body:
        parsed["title"] = _text(body.get("title"), "title", 3, TITLE_LIMIT, problems)
    if require_text or "body" in body:
        parsed["body"] = _text(body.get("body"), "body", 1, BODY_LIMIT, problems)
    if require_text or "expires_at" in body:
        parsed["expires_at"] = _expiry(body.get("expires_at"), problems)
    return parsed, problems


def _lock(session: Session, notice_id, society_id: int) -> Notice | None:
    return session.scalar(
        select(Notice)
        .where(Notice.id == notice_id, Notice.society_id == society_id)
        .with_for_update()
    )


@notices_bp.post("/api/admin/notices")
@manage_notices
def create_notice():
    body, failure = json_object({"title", "body", "expires_at"})
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    parsed, problems = _content(body, require_text=True)
    if problems:
        return error("VALIDATION_ERROR", "Notice details are invalid.", 400, fields=problems)
    now = utc_now()
    notice = Notice(
        society_id=society.id,
        title=parsed["title"],
        body=parsed["body"],
        expires_at=parsed["expires_at"],
        status=NoticeStatus.DRAFT,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(notice)
    db.session.flush()
    _audit("NOTICE_CREATED", notice, _audit_details(notice))
    db.session.commit()
    return jsonify({"notice": _serialize(notice, now)}), 201


@notices_bp.get("/api/admin/notices")
@manage_notices
def list_managed_notices():
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    status_name = request.args.get("status")
    statement = select(Notice).where(Notice.society_id == society.id)
    if status_name is not None:
        try:
            status = NoticeStatus(status_name)
        except ValueError:
            return error("VALIDATION_ERROR", "Status must be DRAFT, PUBLISHED, or ARCHIVED.", 400)
        statement = statement.where(Notice.status == status)
    rows = db.session.scalars(
        statement.order_by(Notice.updated_at.desc(), Notice.id.desc()).limit(limit).offset(offset)
    ).all()
    now = utc_now()
    return jsonify({
        "notices": [_serialize(row, now) for row in rows],
        "pagination": {"limit": limit, "offset": offset},
    }), 200


@notices_bp.get("/api/admin/notices/<uuid:notice_id>")
@manage_notices
def get_managed_notice(notice_id):
    society, failure = _society()
    if failure:
        return failure
    notice = db.session.scalar(
        select(Notice).where(Notice.id == notice_id, Notice.society_id == society.id)
    )
    if notice is None:
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    return jsonify({"notice": _serialize(notice)}), 200


@notices_bp.patch("/api/admin/notices/<uuid:notice_id>")
@manage_notices
def update_draft(notice_id):
    body, failure = json_object({"title", "body", "expires_at"})
    if failure:
        return failure
    if not body:
        return error("VALIDATION_ERROR", "No notice changes were submitted.", 400)
    society, failure = _society()
    if failure:
        return failure
    notice = _lock(db.session, notice_id, society.id)
    if notice is None:
        db.session.rollback()
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    if notice.status != NoticeStatus.DRAFT:
        db.session.rollback()
        return error("NOTICE_IMMUTABLE", "Published notices cannot be edited. Create a replacement.", 409)
    parsed, problems = _content(body, require_text=False)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Notice details are invalid.", 400, fields=problems)
    if "title" in parsed:
        notice.title = parsed["title"]
    if "body" in parsed:
        notice.body = parsed["body"]
    if "expires_at" in parsed:
        notice.expires_at = parsed["expires_at"]
    notice.updated_at = utc_now()
    _audit("NOTICE_UPDATED", notice, _audit_details(notice))
    db.session.commit()
    return jsonify({"notice": _serialize(notice)}), 200


@notices_bp.post("/api/admin/notices/<uuid:notice_id>/publish")
@manage_notices
def publish_notice(notice_id):
    _body, failure = json_object(set())
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    notice = _lock(db.session, notice_id, society.id)
    if notice is None:
        db.session.rollback()
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    if notice.status != NoticeStatus.DRAFT:
        db.session.rollback()
        return error("INVALID_NOTICE_STATE", "Only a draft can be published.", 409)
    now = utc_now()
    expires = _aware(notice.expires_at)
    if expires is not None and expires <= now:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Expiry must be in the future before publication.", 400)
    notice.status = NoticeStatus.PUBLISHED
    notice.published_at = now
    notice.published_by_user_id = current_user.id
    notice.updated_at = now
    _audit("NOTICE_PUBLISHED", notice, _audit_details(notice, from_status="DRAFT"))
    db.session.commit()
    return jsonify({"notice": _serialize(notice, now)}), 200


@notices_bp.post("/api/admin/notices/<uuid:notice_id>/archive")
@manage_notices
def archive_notice(notice_id):
    _body, failure = json_object(set())
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    notice = _lock(db.session, notice_id, society.id)
    if notice is None:
        db.session.rollback()
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    if notice.status == NoticeStatus.ARCHIVED:
        db.session.rollback()
        return error("INVALID_NOTICE_STATE", "This notice is already archived.", 409)
    previous = notice.status.value
    now = utc_now()
    notice.status = NoticeStatus.ARCHIVED
    notice.archived_at = now
    notice.archived_by_user_id = current_user.id
    notice.updated_at = now
    _audit("NOTICE_ARCHIVED", notice, _audit_details(notice, from_status=previous))
    db.session.commit()
    return jsonify({"notice": _serialize(notice, now)}), 200


@notices_bp.post("/api/admin/notices/<uuid:notice_id>/replacements")
@manage_notices
def replace_notice(notice_id):
    _body, failure = json_object(set())
    if failure:
        return failure
    society, failure = _society()
    if failure:
        return failure
    source = _lock(db.session, notice_id, society.id)
    if source is None:
        db.session.rollback()
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    if source.published_at is None:
        db.session.rollback()
        return error("INVALID_NOTICE_STATE", "Only a published notice can be corrected by a replacement.", 409)
    now = utc_now()
    replacement = Notice(
        society_id=society.id,
        title=source.title,
        body=source.body,
        expires_at=source.expires_at,
        status=NoticeStatus.DRAFT,
        replaces_notice_id=source.id,
        created_by_user_id=current_user.id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(replacement)
    db.session.flush()
    _audit("NOTICE_REPLACEMENT_CREATED", replacement, _audit_details(replacement))
    db.session.commit()
    return jsonify({"notice": _serialize(replacement, now)}), 201


@notices_bp.get("/api/notices")
@read_notices
def list_visible_notices():
    society, failure = _society()
    if failure:
        return failure
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    now = utc_now()
    # Use the same expiry clock as the detail route. A SQL timestamp comparison
    # can disagree with that check and briefly list a notice the detail route hides.
    published = db.session.scalars(
        select(Notice)
        .where(Notice.society_id == society.id, Notice.status == NoticeStatus.PUBLISHED)
        .order_by(Notice.published_at.desc(), Notice.id.desc())
    ).all()
    visible = [row for row in published if _visible(row, now)]
    response = jsonify({
        "notices": [_serialize(row, now) for row in visible[offset:offset + limit]],
        "pagination": {"limit": limit, "offset": offset},
    })
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@notices_bp.get("/api/notices/<uuid:notice_id>")
@read_notices
def get_visible_notice(notice_id):
    society, failure = _society()
    if failure:
        return failure
    notice = db.session.scalar(
        select(Notice).where(Notice.id == notice_id, Notice.society_id == society.id)
    )
    now = utc_now()
    if notice is None or not _visible(notice, now):
        return error("NOTICE_NOT_FOUND", "Notice not found.", 404)
    response = jsonify({"notice": _serialize(notice, now)})
    response.headers["Cache-Control"] = "no-store"
    return response, 200
