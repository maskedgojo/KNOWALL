"""Shared Module 4 helpers: scope, validation, geography, serialisation and history.

Authorization reuses Module 1 `requires_permission`:
- `locality.read`             browse published locality content (residents, Society Admin, coordinator)
- `locality.listings.suggest` submit corrections, local events and content reports (eligible residents)
- `locality.manage`           directory stewardship and moderation (LOCALITY_COORDINATOR only)
The locality is always resolved from the configured society, never from the client.
"""
import math
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.schema import schema_required
from app.modules.governance.scope import configured_society
from app.modules.identity.access import requires_permission
from app.modules.identity.auth.routes import error
from app.modules.identity.models import AuditLog, User
from app.modules.identity.models.user import utc_now

from .models import LocalityHistory, LocalityProfile, Place, PlaceCategory, VerificationStatus, PublicationStatus

locality_bp = Blueprint("locality", __name__)

read_locality = requires_permission("locality.read")
suggest_locality = requires_permission("locality.listings.suggest")
manage_locality = requires_permission("locality.manage")

TABLES = ("locality_profiles", "place_categories", "places", "place_verifications", "listing_corrections",
          "local_events", "local_alerts", "locality_content_reports", "locality_history")
PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{6,24}$")


def store(payload, status=200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response, status


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    value = aware(value)
    return value.isoformat() if value else None


def locality_scope():
    """(locality, error_response). Checks migrations, society and the locality profile."""
    missing = schema_required(*TABLES)
    if missing:
        return None, missing
    society = configured_society()
    if society is None:
        return None, error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    locality = db.session.scalar(select(LocalityProfile).where(LocalityProfile.society_id == society.id))
    if locality is None:
        return None, error("LOCALITY_NOT_CONFIGURED",
                           "The locality has not been set up yet. Run python -m scripts.seed_locality.", 404)
    return locality, None


def pagination(default_limit=30):
    try:
        limit = int(request.args.get("limit", str(default_limit)))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def names(user_ids) -> dict:
    identifiers = {item for item in user_ids if item is not None}
    if not identifiers:
        return {}
    rows = db.session.execute(select(User.id, User.display_name).where(User.id.in_(identifiers))).all()
    return {row[0]: row[1] for row in rows}


# ------------------------------------------------------------------ validation

def text(value, field, minimum, maximum, problems, *, required=True):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        problems[field] = f"Must contain {minimum} to {maximum} characters."
        return None
    return value.strip()


def web_url(value, field, problems, *, required=False):
    """Only absolute http(s) URLs; rejects javascript:, data: and similar schemes."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            problems[field] = "A source link (https://…) is required."
        return None
    if not isinstance(value, str) or len(value.strip()) > 500:
        problems[field] = "Use a link of at most 500 characters."
        return None
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or any(ch.isspace() for ch in cleaned):
        problems[field] = "Use a full http:// or https:// link."
        return None
    return cleaned


def phone(value, field, problems, *, required=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            problems[field] = "Enter a phone number."
        return None
    if not isinstance(value, str) or not PHONE_RE.match(value.strip()) or sum(ch.isdigit() for ch in value) < 3:
        problems[field] = "Use digits, spaces, +, - or brackets (3 to 24 characters)."
        return None
    return " ".join(value.split())


def coordinate(value, field, low, high, problems):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        problems[field] = f"Must be a number between {low} and {high}."
        return None
    return float(value)


def parse_time(value, field, problems):
    if not isinstance(value, str):
        problems[field] = "Use an ISO 8601 date and time with a time zone."
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        problems[field] = "Use an ISO 8601 date and time with a time zone."
        return None
    if parsed.tzinfo is None:
        problems[field] = "Include a time zone offset."
        return None
    return parsed.astimezone(timezone.utc)


def enum_value(kind, value, field, problems):
    try:
        return kind(value)
    except ValueError:
        problems[field] = "Use one of: " + ", ".join(item.value for item in kind) + "."
        return None


# ------------------------------------------------------------------ geography

def distance_m(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance (haversine), metres."""
    radius = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def within_coverage(locality: LocalityProfile, lat: float, lng: float) -> bool:
    return distance_m(locality.center_latitude, locality.center_longitude, lat, lng) <= locality.coverage_radius_m


def coordinates(body, locality, problems, lat_key="latitude", lng_key="longitude"):
    """Both or neither; inside the configured coverage. Returns (lat, lng) or (None, None)."""
    lat, lng = body.get(lat_key), body.get(lng_key)
    if lat is None and lng is None:
        return None, None
    if lat is None or lng is None:
        problems[lat_key] = "Give both latitude and longitude, or neither."
        return None, None
    lat = coordinate(lat, lat_key, -90, 90, problems)
    lng = coordinate(lng, lng_key, -180, 180, problems)
    if lat is None or lng is None:
        return None, None
    if not within_coverage(locality, lat, lng):
        problems[lat_key] = f"This point is outside the {locality.name} coverage area ({locality.coverage_radius_m} m radius)."
        return None, None
    return lat, lng


# ------------------------------------------------------------------ serialisation

def verification_state(place: Place, locality: LocalityProfile, now: datetime | None = None) -> str:
    """ARCHIVED, NEEDS_RECHECK, UNVERIFIED, STALE or VERIFIED, from stored data only."""
    if place.publication_status == PublicationStatus.ARCHIVED:
        return "ARCHIVED"
    if place.verification_status == VerificationStatus.NEEDS_RECHECK:
        return "NEEDS_RECHECK"
    if place.verification_status == VerificationStatus.UNVERIFIED or place.last_verified_at is None:
        return "UNVERIFIED"
    now = now or utc_now()
    if aware(place.last_verified_at) < aware(now) - timedelta(days=locality.stale_after_days):
        return "STALE"
    return "VERIFIED"


def category_json(category: PlaceCategory) -> dict:
    return {"key": category.key, "label": category.label, "description": category.description,
            "is_emergency": category.is_emergency}


def place_json(place: Place, category: PlaceCategory, locality: LocalityProfile, *, people: dict | None = None,
               staff: bool = False) -> dict:
    state = verification_state(place, locality)
    payload = {
        "id": str(place.id),
        "name": place.name,
        "category": category_json(category),
        "description": place.description,
        "address": place.address,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "phone": place.phone,
        "website_url": place.website_url,
        "source_label": place.source_label,
        "source_url": place.source_url,
        "data_origin": place.data_origin.value,
        "publication_status": place.publication_status.value,
        "verification_state": state,
        "is_stale": state in ("STALE", "NEEDS_RECHECK"),
        "last_verified_at": iso(place.last_verified_at),
        "last_verification_method": place.last_verification_method.value if place.last_verification_method else None,
        "updated_at": iso(place.updated_at),
        "version": place.version,
    }
    if staff:
        people = people or {}
        payload.update({
            "archived_reason": place.archived_reason,
            "last_verified_by_display_name": people.get(place.last_verified_by_user_id),
            "created_at": iso(place.created_at),
        })
    return payload


def locality_json(locality: LocalityProfile, categories: list[PlaceCategory]) -> dict:
    return {
        "id": locality.id,
        "society_id": locality.society_id,
        "name": locality.name,
        "description": locality.description,
        "is_fictional": locality.is_fictional,
        "coverage": {
            "type": "RADIUS",
            "center": {"latitude": locality.center_latitude, "longitude": locality.center_longitude},
            "radius_m": locality.coverage_radius_m,
        },
        "stale_after_days": locality.stale_after_days,
        "categories": [category_json(item) for item in categories],
        "updated_at": iso(locality.updated_at),
    }


def active_categories() -> list[PlaceCategory]:
    return list(db.session.scalars(
        select(PlaceCategory).where(PlaceCategory.active.is_(True)).order_by(PlaceCategory.sort_order, PlaceCategory.label)
    ))


# ------------------------------------------------------------------ history

def record(locality: LocalityProfile, entity_type: str, entity_id, action: str, *, changes=None, reason=None,
           audit_details: dict | None = None) -> None:
    """Append to locality_history and the shared audit_logs. Caller commits."""
    db.session.add(LocalityHistory(
        locality_id=locality.id, entity_type=entity_type, entity_id=str(entity_id),
        actor_user_id=current_user.id if current_user.is_authenticated else None,
        action=action, changes=changes, reason=reason,
    ))
    db.session.add(AuditLog(
        actor_user_id=current_user.id if current_user.is_authenticated else None,
        action=f"LOCALITY_{action}", entity_type=f"LOCALITY_{entity_type}",
        entity_id=entity_id if isinstance(entity_id, uuid.UUID) else None,
        details={"locality_id": locality.id, **(audit_details or {})},
    ))


def history_json(rows, people: dict, *, include_actor: bool) -> list[dict]:
    items = []
    for row in rows:
        item = {"id": str(row.id), "action": row.action, "changes": row.changes, "reason": row.reason,
                "created_at": iso(row.created_at)}
        if include_actor:
            item["actor_display_name"] = people.get(row.actor_user_id)
        items.append(item)
    return items


def history_for(entity_type: str, entity_id) -> list[LocalityHistory]:
    return list(db.session.scalars(
        select(LocalityHistory)
        .where(LocalityHistory.entity_type == entity_type, LocalityHistory.entity_id == str(entity_id))
        .order_by(LocalityHistory.created_at.asc(), LocalityHistory.id.asc())
    ))
