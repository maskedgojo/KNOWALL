"""Shared helpers for Module 5 routes: validation, permissions, geometry, audit.

Module 5 owns nothing outside `app/modules/civic`. Identity and permissions are
consumed from Module 1 (`requires_permission`, `has_permission`).
"""
import math
import re
from datetime import datetime, timezone
from functools import wraps

from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.identity.access import has_permission, requires_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.models import AuditLog, User

CIVIC_TABLES = (
    "civic_localities", "civic_issues", "civic_issue_evidence", "civic_issue_supports",
    "civic_duplicate_links", "civic_issue_transitions", "civic_priority_snapshots",
    "civic_issue_reports", "civic_issue_handoffs",
)

# Permissions registered by Module 1. Residents hold these through an ACTIVE membership.
CREATE_PERMISSION = "civic.issues.create"
SUPPORT_PERMISSION = "civic.issues.support"
# Moderation uses the existing shared admin grant until Module 1 registers a dedicated
# `civic.issues.moderate` permission. Change this single constant when it does.
MODERATE_PERMISSION = "identity.admin.manage"

resident_civic = requires_permission(CREATE_PERMISSION)
supporter = requires_permission(SUPPORT_PERMISSION)
moderator = requires_permission(MODERATE_PERMISSION)

EARTH_RADIUS_M = 6_371_000.0


def civic_reader(view):
    """Eligible residents and moderators may read civic issues."""
    @wraps(view)
    @login_required
    def protected(*args, **kwargs):
        if not (has_permission(CREATE_PERMISSION) or has_permission(MODERATE_PERMISSION)):
            return error("FORBIDDEN", "You do not have permission for this action.", 403)
        return view(*args, **kwargs)
    return protected


def is_moderator() -> bool:
    return has_permission(MODERATE_PERMISSION)


def schema_missing():
    return schema_required(*CIVIC_TABLES)


def aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso(value) -> str | None:
    if value is None:
        return None
    return aware(value).isoformat() if isinstance(value, datetime) else value.isoformat()


def json_body(allowed: set[str]):
    if not request.is_json:
        return None, error("UNSUPPORTED_MEDIA_TYPE", "Send a JSON object.", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, error("VALIDATION_ERROR", "A JSON object is required.", 400)
    unknown = sorted(set(body) - allowed)
    if unknown:
        return None, error(
            "VALIDATION_ERROR", "Unexpected fields are not accepted.", 400,
            fields={field: "Unknown field." for field in unknown},
        )
    return body, None


def validation_error(problems: dict):
    return error("VALIDATION_ERROR", "Please correct the highlighted fields.", 400, fields=problems)


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


def choice(value, field: str, kind, problems: dict):
    try:
        return kind(value)
    except (ValueError, TypeError):
        problems[field] = "Choose one of: " + ", ".join(item.value for item in kind) + "."
        return None


def number(value, field: str, minimum: float, maximum: float, problems: dict) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not minimum <= value <= maximum:
        problems[field] = f"Must be a number from {minimum} to {maximum}."
        return None
    return float(value)


# Safe, free-text rules. Descriptions are public to residents, so they must not
# carry markup or the reporter's own contact details.
_HTML = re.compile(r"<\s*/?\s*[a-zA-Z!][^>]*>")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d[\s().-]?){10,}")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def safe_text(value, field: str, minimum: int, maximum: int, problems: dict, *, required=True) -> str | None:
    cleaned = text(value, field, minimum, maximum, problems, required=required)
    if cleaned is None:
        return None
    if _CONTROL.search(cleaned):
        problems[field] = "Remove unsupported control characters."
        return None
    if _HTML.search(cleaned):
        problems[field] = "Markup is not allowed. Use plain text."
        return None
    if _EMAIL.search(cleaned) or _PHONE.search(cleaned):
        problems[field] = "Remove personal contact details such as phone numbers or email addresses."
        return None
    return cleaned


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bounding_box(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """Cheap SQL pre-filter (min_lat, max_lat, min_lon, max_lon); callers still apply haversine."""
    d_lat = math.degrees(radius_m / EARTH_RADIUS_M)
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    d_lon = math.degrees(radius_m / (EARTH_RADIUS_M * cos_lat))
    return lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon


def display_names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


def audit(action: str, entity_type: str, entity_id, details: dict | None = None):
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action, entity_type=entity_type,
        entity_id=entity_id, details=details,
    ))


def no_store(payload: dict, status: int = 200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status
