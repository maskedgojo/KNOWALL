"""Private dispute submission. Only the author can read a dispute.

No handler, appeal, or status-change permission is registered.
"""
from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import AuditLog
from app.modules.identity.models.user import utc_now

from .models import Dispute, DisputeStatus


disputes_bp = Blueprint("disputes", __name__)
submit_dispute = requires_permission("society.notices.read")


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


def _json(dispute: Dispute) -> dict:
    return {
        "id": str(dispute.id),
        "society_id": dispute.society_id,
        "title": dispute.title,
        "description": dispute.description,
        "status": dispute.status.value,
        "created_at": _iso(dispute.created_at),
        "updated_at": _iso(dispute.updated_at),
    }


def _mine(dispute_id, society_id: int) -> Dispute | None:
    return db.session.scalar(select(Dispute).where(
        Dispute.id == dispute_id,
        Dispute.society_id == society_id,
        Dispute.created_by_user_id == current_user.id,
    ))


@disputes_bp.get("/api/disputes")
@submit_dispute
def list_disputes():
    missing = schema_required("disputes")
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
        select(Dispute)
        .where(Dispute.society_id == society.id, Dispute.created_by_user_id == current_user.id)
        .order_by(Dispute.created_at.desc(), Dispute.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    response = jsonify({"disputes": [_json(row) for row in rows], "pagination": {"limit": limit, "offset": offset}})
    response.headers["Cache-Control"] = "no-store"
    return response, 200


@disputes_bp.post("/api/disputes")
@submit_dispute
def create_dispute():
    missing = schema_required("disputes")
    if missing:
        return missing
    body, failure = json_object({"title", "description"})
    if failure:
        return failure
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    problems: dict = {}
    title = _text(body.get("title"), "title", 3, 160, problems)
    description = _text(body.get("description"), "description", 1, 8000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the dispute and try again.", 400, fields=problems)
    now = utc_now()
    dispute = Dispute(
        society_id=society.id, title=title, description=description,
        status=DisputeStatus.SUBMITTED, created_by_user_id=current_user.id,
        created_at=now, updated_at=now,
    )
    db.session.add(dispute)
    db.session.flush()
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action="DISPUTE_SUBMITTED", entity_type="DISPUTE",
        entity_id=dispute.id, details={"title": dispute.title, "status": "SUBMITTED"},
    ))
    db.session.commit()
    return jsonify({"dispute": _json(dispute)}), 201


@disputes_bp.get("/api/disputes/<uuid:dispute_id>")
@submit_dispute
def get_dispute(dispute_id):
    missing = schema_required("disputes")
    if missing:
        return missing
    society = configured_society()
    if society is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    dispute = _mine(dispute_id, society.id)
    if dispute is None:
        return error("DISPUTE_NOT_FOUND", "Dispute not found.", 404)
    response = jsonify({"dispute": _json(dispute)})
    response.headers["Cache-Control"] = "no-store"
    return response, 200
