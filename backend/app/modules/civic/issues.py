"""Issue creation, discovery, reporter lifecycle actions, timeline and abuse reports."""
from datetime import datetime, timedelta, timezone

from flask import Blueprint, request
from flask_login import current_user
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.auth.routes import error

from .common import (
    audit, bounding_box, choice, civic_reader, display_names, haversine_m, iso, is_moderator, json_body, no_store,
    number, pagination, resident_civic, safe_text, schema_missing, text, validation_error,
)
from .duplicates import find_similar, suggestions_payload
from .models import (
    ActorRole, CivicIssue, ConcernType, IssueCategory, IssueHandoff, IssueModerationReport, IssuePrivacy,
    IssueSeverity, IssueState, IssueTransition,
)
from .service import (
    COMMUNITY_STATES, EVIDENCE_EDITABLE, MAX_ISSUES_PER_DAY, REPORTER_EDITABLE, REPORTER_WITHDRAWABLE,
    InvalidTransition, MAX_EVIDENCE_PER_ISSUE, can_view, initial_transition, locality, min_supporters, serialize_issues,
    supporter_sets, transition, within_locality,
)
from . import priority

issues_bp = Blueprint("civic_issues", __name__)
S = IssueState
ISSUE_FIELDS = {"title", "description", "category", "severity", "latitude", "longitude", "address_hint", "privacy"}


def invalid_state(exc: InvalidTransition):
    return error(
        "INVALID_STATE", f"This issue cannot move from {exc.from_state.value} to {exc.to_state.value}.", 409
    )


def fetch_locked(issue_id):
    return db.session.scalar(select(CivicIssue).where(CivicIssue.id == issue_id).with_for_update())


def validated_fields(body: dict, loc, problems: dict, *, partial: bool) -> dict:
    """Clean issue fields. `partial` allows omitted fields (PATCH)."""
    cleaned: dict = {}

    def present(name):
        return name in body or not partial

    if present("title"):
        value = safe_text(body.get("title"), "title", 8, 160, problems)
        if value is not None:
            cleaned["title"] = value
    if present("description"):
        value = safe_text(body.get("description"), "description", 20, 2000, problems)
        if value is not None:
            cleaned["description"] = value
    if present("category"):
        value = choice(body.get("category"), "category", IssueCategory, problems)
        if value is not None:
            cleaned["category"] = value
    if "severity" in body:
        value = choice(body.get("severity"), "severity", IssueSeverity, problems)
        if value is not None:
            cleaned["severity"] = value
    elif not partial:
        cleaned["severity"] = IssueSeverity.MEDIUM
    if "privacy" in body:
        value = choice(body.get("privacy"), "privacy", IssuePrivacy, problems)
        if value is not None:
            cleaned["privacy"] = value
    elif not partial:
        cleaned["privacy"] = IssuePrivacy.ANONYMOUS
    if "address_hint" in body:
        value = safe_text(body.get("address_hint"), "address_hint", 0, 160, problems)
        if value is not None:
            cleaned["address_hint"] = value
    elif not partial:
        cleaned["address_hint"] = ""
    if present("latitude") or present("longitude"):
        latitude = number(body.get("latitude"), "latitude", -90, 90, problems)
        longitude = number(body.get("longitude"), "longitude", -180, 180, problems)
        if latitude is not None and longitude is not None:
            if not within_locality(loc, latitude, longitude):
                problems["latitude"] = "This location is outside the area covered by KNOWALL."
                problems["longitude"] = "This location is outside the area covered by KNOWALL."
            else:
                cleaned["latitude"], cleaned["longitude"] = latitude, longitude
    return cleaned


def _setup():
    missing = schema_missing()
    if missing:
        return None, missing
    loc = locality()
    if loc is None:
        return None, error("LOCALITY_NOT_CONFIGURED", "Civic reporting is not set up for this area yet.", 503)
    return loc, None


# ------------------------------------------------------------------ discovery

@issues_bp.get("/api/civic/locality")
@civic_reader
def civic_locality():
    """Coverage area and reporting rules, so the UI can draw the map and explain readiness."""
    loc, failure = _setup()
    if failure:
        return failure
    return no_store({"locality": {
        "id": loc.id, "name": loc.name, "center_lat": loc.center_lat, "center_lon": loc.center_lon,
        "radius_m": loc.radius_m, "required_supporters": min_supporters(),
        "max_evidence_per_issue": MAX_EVIDENCE_PER_ISSUE,
    }})


@issues_bp.get("/api/civic/issues")
@civic_reader
def list_issues():
    loc, failure = _setup()
    if failure:
        return failure
    page = pagination()
    if page is None:
        return validation_error({"limit": "Use limit 1-100 and offset 0 or more."})
    limit, offset = page
    problems: dict = {}
    conditions = [CivicIssue.locality_id == loc.id]
    mine = request.args.get("mine") == "true"
    if mine:
        conditions.append(CivicIssue.creator_id == current_user.id)
    else:
        conditions.append(CivicIssue.state.in_(COMMUNITY_STATES))
    if request.args.get("category"):
        category = choice(request.args["category"], "category", IssueCategory, problems)
        if category:
            conditions.append(CivicIssue.category == category)
    if request.args.get("severity"):
        severity = choice(request.args["severity"], "severity", IssueSeverity, problems)
        if severity:
            conditions.append(CivicIssue.severity == severity)
    if request.args.get("state"):
        state = choice(request.args["state"], "state", IssueState, problems)
        if state:
            conditions.append(CivicIssue.state == state)
    term = (request.args.get("q") or "").strip()[:80]
    if term:
        conditions.append(or_(CivicIssue.title.ilike(f"%{term}%"), CivicIssue.description.ilike(f"%{term}%")))
    near = None
    if request.args.get("near_lat") or request.args.get("near_lon") or request.args.get("radius_m"):
        try:
            near = (float(request.args["near_lat"]), float(request.args["near_lon"]),
                    float(request.args.get("radius_m", "500")))
        except (KeyError, ValueError):
            problems["near_lat"] = "Provide near_lat, near_lon and optional radius_m."
        else:
            if not (-90 <= near[0] <= 90 and -180 <= near[1] <= 180 and 10 <= near[2] <= 5000):
                problems["near_lat"] = "Coordinates or radius out of range."
            else:
                lo_lat, hi_lat, lo_lon, hi_lon = bounding_box(*near)
                conditions.append(and_(CivicIssue.latitude.between(lo_lat, hi_lat),
                                       CivicIssue.longitude.between(lo_lon, hi_lon)))
    sort = request.args.get("sort", "recent")
    if sort not in {"recent", "support", "priority"}:
        problems["sort"] = "Choose recent, support or priority."
    if problems:
        return validation_error(problems)
    rows = db.session.scalars(
        select(CivicIssue).where(and_(*conditions)).order_by(CivicIssue.created_at.desc()).limit(500)
    ).all()
    if near:
        rows = [row for row in rows if haversine_m(near[0], near[1], row.latitude, row.longitude) <= near[2]]
    total = len(rows)
    payload = serialize_issues(rows, viewer_id=current_user.id, moderator=is_moderator())
    if sort == "support":
        payload.sort(key=lambda item: (item["support_count"], item["created_at"]), reverse=True)
    elif sort == "priority":
        payload.sort(key=lambda item: (item["priority"]["score"], item["created_at"]), reverse=True)
    return no_store({"issues": payload[offset:offset + limit], "total": total, "limit": limit, "offset": offset})


@issues_bp.get("/api/civic/issues/<uuid:issue_id>")
@civic_reader
def get_issue(issue_id):
    loc, failure = _setup()
    if failure:
        return failure
    issue = db.session.get(CivicIssue, issue_id)
    moderator = is_moderator()
    # Same 404 for "missing" and "not visible" so ids cannot be probed.
    if issue is None or issue.locality_id != loc.id or not can_view(issue, current_user.id, moderator):
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    item = serialize_issues([issue], viewer_id=current_user.id, moderator=moderator, detail=True)[0]
    return no_store({"issue": item})


# ------------------------------------------------------------------ creation and reporter actions

@issues_bp.post("/api/civic/issues")
@resident_civic
def create_issue():
    loc, failure = _setup()
    if failure:
        return failure
    body, failure = json_body(ISSUE_FIELDS | {"save_as_draft"})
    if failure:
        return failure
    problems: dict = {}
    cleaned = validated_fields(body, loc, problems, partial=False)
    draft = body.get("save_as_draft", False)
    if not isinstance(draft, bool):
        problems["save_as_draft"] = "Must be true or false."
    if problems:
        return validation_error(problems)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    recent = db.session.scalar(select(func.count()).select_from(CivicIssue).where(
        CivicIssue.creator_id == current_user.id, CivicIssue.created_at >= since)) or 0
    if recent >= MAX_ISSUES_PER_DAY:
        return error("RATE_LIMITED", f"You can create at most {MAX_ISSUES_PER_DAY} issues per day.", 429)
    issue = CivicIssue(locality_id=loc.id, creator_id=current_user.id, state=S.DRAFT, **cleaned)
    db.session.add(issue)
    db.session.flush()
    initial_transition(issue, actor_id=current_user.id)
    if not draft:
        transition(issue, S.SUBMITTED, actor_id=current_user.id, role=ActorRole.REPORTER, reason="Submitted by reporter.")
    audit("CIVIC_ISSUE_CREATED", "civic_issue", issue.id, {"category": issue.category.value, "draft": draft})
    similar = find_similar(
        issue.latitude, issue.longitude, issue.category, title=issue.title, exclude_id=issue.id,
    )
    db.session.commit()
    return no_store({
        "issue": serialize_issues([issue], viewer_id=current_user.id, moderator=False, detail=True)[0],
        "similar": suggestions_payload(similar, viewer_id=current_user.id, moderator=False),
    }, 201)


def _own_issue_locked(issue_id):
    issue = fetch_locked(issue_id)
    if issue is None or issue.creator_id != current_user.id:
        db.session.rollback()
        return None, error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    return issue, None


@issues_bp.patch("/api/civic/issues/<uuid:issue_id>")
@resident_civic
def edit_issue(issue_id):
    loc, failure = _setup()
    if failure:
        return failure
    body, failure = json_body(ISSUE_FIELDS)
    if failure:
        return failure
    issue, failure = _own_issue_locked(issue_id)
    if failure:
        return failure
    if issue.state not in REPORTER_EDITABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Only drafts and issues needing information can be edited.", 409)
    problems: dict = {}
    merged_body = {"latitude": issue.latitude, "longitude": issue.longitude, **body}
    cleaned = validated_fields(merged_body, loc, problems, partial=True)
    if problems:
        db.session.rollback()
        return validation_error(problems)
    for name, value in cleaned.items():
        setattr(issue, name, value)
    issue.updated_at = datetime.now(timezone.utc)
    audit("CIVIC_ISSUE_EDITED", "civic_issue", issue.id, {"fields": sorted(body)})
    db.session.commit()
    return no_store({"issue": serialize_issues([issue], viewer_id=current_user.id, moderator=False, detail=True)[0]})


@issues_bp.post("/api/civic/issues/<uuid:issue_id>/submit")
@resident_civic
def submit_issue(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"note"})
    if failure:
        return failure
    problems: dict = {}
    note = safe_text(body.get("note"), "note", 0, 500, problems, required=False) or ""
    if problems:
        return validation_error(problems)
    issue, failure = _own_issue_locked(issue_id)
    if failure:
        return failure
    try:
        transition(issue, S.SUBMITTED, actor_id=current_user.id, role=ActorRole.REPORTER,
                   reason=note or "Submitted by reporter.")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    audit("CIVIC_ISSUE_SUBMITTED", "civic_issue", issue.id)
    db.session.commit()
    return no_store({"issue": serialize_issues([issue], viewer_id=current_user.id, moderator=False, detail=True)[0]})


@issues_bp.delete("/api/civic/issues/<uuid:issue_id>")
@resident_civic
def withdraw_issue(issue_id):
    missing = schema_missing()
    if missing:
        return missing
    issue, failure = _own_issue_locked(issue_id)
    if failure:
        return failure
    if issue.state not in REPORTER_WITHDRAWABLE:
        db.session.rollback()
        return error("INVALID_STATE", "This issue can no longer be withdrawn.", 409)
    try:
        transition(issue, S.WITHDRAWN, actor_id=current_user.id, role=ActorRole.REPORTER, reason="Withdrawn by reporter.")
    except InvalidTransition as exc:
        db.session.rollback()
        return invalid_state(exc)
    audit("CIVIC_ISSUE_WITHDRAWN", "civic_issue", issue.id)
    db.session.commit()
    return no_store({"issue": serialize_issues([issue], viewer_id=current_user.id, moderator=False)[0]})


# ------------------------------------------------------------------ timeline

@issues_bp.get("/api/civic/issues/<uuid:issue_id>/timeline")
@civic_reader
def issue_timeline(issue_id):
    loc, failure = _setup()
    if failure:
        return failure
    issue = db.session.get(CivicIssue, issue_id)
    moderator = is_moderator()
    if issue is None or issue.locality_id != loc.id or not can_view(issue, current_user.id, moderator):
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    private = moderator or issue.creator_id == current_user.id
    rows = db.session.scalars(
        select(IssueTransition).where(IssueTransition.issue_id == issue.id)
        .order_by(IssueTransition.created_at, IssueTransition.id)
    ).all()
    events = []
    for row in rows:
        public_state = row.to_state in {s.value for s in COMMUNITY_STATES | {S.MERGED}}
        if not private and not public_state:
            continue
        if not private and events and events[-1]["to_state"] == row.to_state:
            continue  # a private round trip (e.g. needs-info) should not show as a repeat to others
        events.append({
            "type": "STATE_CHANGE", "from_state": row.from_state, "to_state": row.to_state,
            "actor_role": row.actor_role.value, "reason": row.reason if private else "",
            "at": iso(row.created_at),
        })
    handoff = db.session.scalar(select(IssueHandoff).where(IssueHandoff.canonical_issue_id == issue.id))
    if handoff:
        events.append({"type": "ROUTED", "routing_status": "PENDING_INTAKE", "at": iso(handoff.routed_at)})
        if handoff.acknowledged_at:
            events.append({
                "type": "AUTHORITY_ACKNOWLEDGED", "authority_case_id": handoff.authority_case_id,
                "at": iso(handoff.acknowledged_at),
            })
    events.sort(key=lambda item: item["at"])
    count = len(supporter_sets([issue.id]).get(issue.id, set()))
    from .service import authority_status
    return no_store({
        "issue_id": str(issue.id), "state": issue.state.value, "events": events,
        "support_count": count, "priority": priority.compute(issue, count),
        "authoritative_status": authority_status(issue.id),
    })


# ------------------------------------------------------------------ abuse reporting

@issues_bp.post("/api/civic/issues/<uuid:issue_id>/report")
@resident_civic
def report_issue(issue_id):
    loc, failure = _setup()
    if failure:
        return failure
    body, failure = json_body({"concern_type", "concern"})
    if failure:
        return failure
    problems: dict = {}
    concern_type = choice(body.get("concern_type"), "concern_type", ConcernType, problems)
    concern = text(body.get("concern"), "concern", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    issue = db.session.get(CivicIssue, issue_id)
    if issue is None or issue.locality_id != loc.id or not can_view(issue, current_user.id, False):
        return error("ISSUE_NOT_FOUND", "Issue not found.", 404)
    if issue.creator_id == current_user.id:
        return error("OWN_ISSUE", "You cannot report your own issue.", 409)
    exists = db.session.scalar(select(IssueModerationReport.id).where(
        IssueModerationReport.issue_id == issue.id, IssueModerationReport.reporter_id == current_user.id))
    if exists:
        return error("ALREADY_REPORTED", "You have already raised a concern about this issue.", 409)
    report = IssueModerationReport(
        issue_id=issue.id, reporter_id=current_user.id, concern_type=concern_type, concern=concern,
    )
    db.session.add(report)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return error("ALREADY_REPORTED", "You have already raised a concern about this issue.", 409)
    audit("CIVIC_ISSUE_REPORTED", "civic_issue", issue.id, {"concern_type": concern_type.value})
    db.session.commit()
    return no_store({"report": {"id": str(report.id), "status": report.status.value}}, 201)
