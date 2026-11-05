"""Shared helpers for Module 3 routes."""
from datetime import date, datetime, timedelta, timezone

from flask import jsonify, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.models import AuditLog, User

# Green Valley Residency is a single Indian society; IST has no daylight saving.
SOCIETY_TZ = timezone(timedelta(hours=5, minutes=30), "IST")

resident_read = requires_permission("society.notices.read")
book_facilities = requires_permission("society.facilities.book")
report_maintenance = requires_permission("society.maintenance.create")
manage_operations = requires_permission("society.operations.manage")

OPERATIONS_TABLES = (
    "facilities", "facility_blackouts", "bookings", "booking_events", "society_events", "event_rsvps",
    "event_volunteers", "event_updates",
    "maintenance_items", "maintenance_updates", "maintenance_requests", "maintenance_request_updates",
    "development_projects", "project_milestones", "operation_photos",
)


def schema_missing():
    return schema_required(*OPERATIONS_TABLES)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return aware(value).isoformat()
    return value.isoformat()


def society_or_error():
    profile = configured_society()
    if profile is None:
        return None, error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    return profile, None


def pagination():
    try:
        limit = int(request.args.get("limit", "30"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def text(value, field: str, minimum: int, maximum: int, problems: dict, *, required=True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    return value.strip()


def when(value, field: str, problems: dict) -> datetime | None:
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


def day(value, field: str, problems: dict, *, required=False) -> date | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        problems[field] = "Use YYYY-MM-DD."
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        problems[field] = "Use YYYY-MM-DD."
        return None


def integer(value, field: str, minimum: int, maximum: int, problems: dict) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        problems[field] = f"Must be a whole number from {minimum} to {maximum}."
        return None
    return value


def choice(value, field: str, kind, problems: dict):
    try:
        return kind(value)
    except ValueError:
        problems[field] = "Choose one of: " + ", ".join(item.value for item in kind) + "."
        return None


def names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


def current_membership():
    """The signed-in resident's first effectively ACTIVE membership, or None."""
    from app.modules.identity.residential.routes import _eligible_memberships
    rows = _eligible_memberships()
    return rows[0] if rows else None


def audit(action: str, entity_type: str, entity_id, details: dict | None = None):
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    ))


def no_store(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status
