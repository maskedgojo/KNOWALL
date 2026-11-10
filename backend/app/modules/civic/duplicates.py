"""Duplicate suggestions: nearby, same-category open issues. Suggestions only, never automatic merges."""
import re

from flask import Blueprint, request
from flask_login import current_user
from sqlalchemy import and_, select

from app.extensions import db
from app.modules.identity.auth.routes import error

from .common import bounding_box, civic_reader, choice, haversine_m, is_moderator, no_store, number, schema_missing, \
    validation_error
from .models import CivicIssue, IssueCategory
from .service import OPEN_STATES, serialize_issues

duplicates_bp = Blueprint("civic_duplicates", __name__)

DEFAULT_RADIUS_M = 150.0
MAX_RADIUS_M = 500.0
MAX_SUGGESTIONS = 5
STOP_WORDS = frozenset({"the", "and", "for", "near", "from", "with", "this", "that", "road", "side", "area"})


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(word) > 2 and word not in STOP_WORDS}


def title_similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    return round(len(a & b) / len(a | b), 2) if a and b else 0.0


def find_similar(latitude: float, longitude: float, category: IssueCategory, *, title: str = "",
                 radius_m: float = DEFAULT_RADIUS_M, exclude_id=None) -> list[tuple[CivicIssue, dict]]:
    """Same category, open state, within `radius_m`. Text alone never produces a match."""
    min_lat, max_lat, min_lon, max_lon = bounding_box(latitude, longitude, radius_m)
    query = select(CivicIssue).where(
        CivicIssue.category == category, CivicIssue.state.in_(OPEN_STATES),
        and_(CivicIssue.latitude.between(min_lat, max_lat), CivicIssue.longitude.between(min_lon, max_lon)),
    )
    if exclude_id is not None:
        query = query.where(CivicIssue.id != exclude_id)
    matches = []
    for issue in db.session.scalars(query):
        distance = haversine_m(latitude, longitude, issue.latitude, issue.longitude)
        if distance > radius_m:
            continue
        text_score = title_similarity(title, issue.title)
        closeness = 1 - distance / radius_m
        matches.append((issue, {
            "distance_m": round(distance),
            "title_similarity": text_score,
            "match_score": round(0.7 * closeness + 0.3 * text_score, 2),
        }))
    matches.sort(key=lambda pair: pair[1]["match_score"], reverse=True)
    return matches[:MAX_SUGGESTIONS]


def suggestions_payload(matches, *, viewer_id, moderator: bool) -> list[dict]:
    rendered = serialize_issues([issue for issue, _ in matches], viewer_id=viewer_id, moderator=moderator)
    return [{**issue, "match": info} for issue, (_, info) in zip(rendered, matches)]


@duplicates_bp.get("/api/civic/issues/similar")
@civic_reader
def similar_issues():
    missing = schema_missing()
    if missing:
        return missing
    problems: dict = {}
    category = choice(request.args.get("category"), "category", IssueCategory, problems)
    latitude = number(_float(request.args.get("lat")), "lat", -90, 90, problems)
    longitude = number(_float(request.args.get("lon")), "lon", -180, 180, problems)
    radius = DEFAULT_RADIUS_M
    if request.args.get("radius_m") is not None:
        radius = number(_float(request.args.get("radius_m")), "radius_m", 10, MAX_RADIUS_M, problems) or radius
    title = (request.args.get("title") or "")[:160]
    exclude = request.args.get("exclude_id")
    exclude_id = None
    if exclude:
        import uuid
        try:
            exclude_id = uuid.UUID(exclude)
        except ValueError:
            problems["exclude_id"] = "Not a valid issue id."
    if problems:
        return validation_error(problems)
    matches = find_similar(latitude, longitude, category, title=title, radius_m=radius, exclude_id=exclude_id)
    return no_store({
        "similar": suggestions_payload(matches, viewer_id=current_user.id, moderator=is_moderator()),
        "radius_m": radius,
        "note": "These are suggestions only. A coordinator decides whether reports are the same issue.",
    })


def _float(value):
    try:
        return float(value) if value is not None else None
    except (ValueError, TypeError):
        return None
