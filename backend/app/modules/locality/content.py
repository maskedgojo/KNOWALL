"""Local events, moderated alerts, the curated locality feed and content reports.

Society events (Module 3) stay private unless the Society Admin ticked
`locality_publish_requested`, explicitly shares the event here, and a
coordinator publishes it. Only public fields are copied; RSVPs never are.
"""
from datetime import timedelta

from flask import request
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, select

from app.extensions import db
from app.modules.governance.scope import configured_society
from app.modules.identity.access import has_permission
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now
from app.modules.operations.models import EventStatus, SocietyEvent

from .common import (
    aware, enum_value, history_for, history_json, iso, locality_bp, locality_scope, manage_locality, names,
    parse_time, read_locality, record, store, suggest_locality, text, web_url,
)
from .models import (
    AlertSeverity, AlertSourceType, AlertStatus, LocalAlert, LocalEvent, LocalEventCategory, LocalEventStatus,
    LocalityContentReport, LocalityHistory, Place, PublicationStatus, ReportStatus, ReportTarget,
)

SEVERITY_RANK = {AlertSeverity.HIGH: 0, AlertSeverity.MEDIUM: 1, AlertSeverity.LOW: 2, AlertSeverity.INFO: 3}
MAX_EVENT_DAYS = 14
MAX_ALERT_DAYS = 30


# ------------------------------------------------------------------ events

def _visible_events(locality):
    """Published local events. A shared society event disappears if Module 3 cancels or un-shares it."""
    return (select(LocalEvent)
            .outerjoin(SocietyEvent, SocietyEvent.id == LocalEvent.source_event_id)
            .where(LocalEvent.locality_id == locality.id, LocalEvent.status == LocalEventStatus.PUBLISHED,
                   or_(LocalEvent.source_event_id.is_(None),
                       and_(SocietyEvent.status == EventStatus.PUBLISHED,
                            SocietyEvent.locality_publish_requested.is_(True)))))


def _timing(event, now):
    if aware(event.ends_at) <= now:
        return "COMPLETED"
    if aware(event.starts_at) <= now:
        return "ONGOING"
    return "UPCOMING"


def _event_json(event: LocalEvent, now, *, people=None, staff=False, mine=False) -> dict:
    payload = {
        "id": str(event.id), "title": event.title, "description": event.description,
        "organizer": event.organizer, "venue": event.venue, "category": event.category.value,
        "starts_at": iso(event.starts_at), "ends_at": iso(event.ends_at),
        "timing": _timing(event, now), "shared_by_society": event.source_event_id is not None,
        "published_at": iso(event.published_at),
    }
    if staff or mine:
        payload.update({"status": event.status.value, "decision_reason": event.decision_reason,
                        "created_at": iso(event.created_at)})
    if staff:
        people = people or {}
        payload.update({"submitted_by_display_name": people.get(event.submitted_by_user_id, ""),
                        "reviewer_display_name": people.get(event.reviewer_user_id)})
    return payload


@locality_bp.get("/api/locality/events")
@read_locality
def list_events():
    locality, failure = locality_scope()
    if failure:
        return failure
    now = utc_now()
    query = _visible_events(locality)
    when = request.args.get("when", "upcoming")
    if when == "upcoming":
        query = query.where(LocalEvent.ends_at > now).order_by(LocalEvent.starts_at.asc())
    elif when == "past":
        query = query.where(LocalEvent.ends_at <= now).order_by(LocalEvent.starts_at.desc())
    elif when == "all":
        query = query.order_by(LocalEvent.starts_at.desc())
    else:
        return error("VALIDATION_ERROR", "Use when=upcoming, past or all.", 400)
    category = request.args.get("category")
    if category:
        problems: dict = {}
        value = enum_value(LocalEventCategory, category, "category", problems)
        if value is None:
            return error("VALIDATION_ERROR", "Unknown event category.", 400, fields=problems)
        query = query.where(LocalEvent.category == value)
    keyword = (request.args.get("q") or "").strip().lower()
    if len(keyword) > 100:
        return error("VALIDATION_ERROR", "Search text must be at most 100 characters.", 400)
    rows = db.session.scalars(query.limit(100)).all()
    if keyword:
        rows = [row for row in rows if keyword in f"{row.title} {row.description} {row.venue} {row.organizer}".lower()]
    return store({"events": [_event_json(row, now) for row in rows]})


def _society_event_problem(event: SocietyEvent | None, society_id: int):
    if event is None or event.society_id != society_id:
        return error("SOCIETY_EVENT_NOT_FOUND", "Society event not found.", 404)
    if not event.locality_publish_requested:
        return error("NOT_OPTED_IN", "Tick 'request locality publication' on the society event first.", 409)
    if event.status != EventStatus.PUBLISHED:
        return error("SOCIETY_EVENT_NOT_PUBLISHED", "Only a published society event can be shared.", 409)
    return None


@locality_bp.post("/api/locality/events/submit")
@login_required
def submit_event():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"source_event_id", "title", "description", "organizer", "venue", "category",
                                 "starts_at", "ends_at"})
    if failure:
        return failure
    now = utc_now()
    problems: dict = {}
    category = enum_value(LocalEventCategory, body.get("category", "OTHER"), "category", problems)
    if body.get("source_event_id") is not None:
        # Module 3 hand-off: the Society Admin shares an event they opted in. Public fields only.
        if not has_permission("society.operations.manage"):
            return error("FORBIDDEN", "Only the Society Admin can share a society event.", 403)
        if set(body) - {"source_event_id", "category"}:
            return error("VALIDATION_ERROR", "A shared society event uses its own details.", 400)
        if problems:
            return error("VALIDATION_ERROR", "Check the event.", 400, fields=problems)
        society = configured_society()
        try:
            from uuid import UUID
            source_id = UUID(str(body["source_event_id"]))
        except ValueError:
            return error("VALIDATION_ERROR", "Invalid society event id.", 400)
        source = db.session.get(SocietyEvent, source_id)
        problem = _society_event_problem(source, society.id)
        if problem:
            return problem
        if aware(source.ends_at) <= now:
            return error("EVENT_ENDED", "This event has already ended.", 409)
        if db.session.scalar(select(LocalEvent.id).where(LocalEvent.source_event_id == source.id)) is not None:
            return error("ALREADY_SHARED", "This society event was already shared with the locality.", 409)
        event = LocalEvent(
            locality_id=locality.id, title=source.title, description=source.description,
            organizer=society.name, venue=source.venue, category=category,
            starts_at=source.starts_at, ends_at=source.ends_at, source_event_id=source.id,
        )
    else:
        if not has_permission("locality.listings.suggest"):
            return error("FORBIDDEN", "Current resident access is required to submit a locality event.", 403)
        title = text(body.get("title"), "title", 3, 160, problems)
        description = text(body.get("description"), "description", 10, 4000, problems)
        organizer = text(body.get("organizer"), "organizer", 2, 160, problems)
        venue = text(body.get("venue"), "venue", 2, 160, problems)
        starts = parse_time(body.get("starts_at"), "starts_at", problems)
        ends = parse_time(body.get("ends_at"), "ends_at", problems)
        if starts and ends:
            if ends <= starts:
                problems["ends_at"] = "Must be after the start."
            elif ends - starts > timedelta(days=MAX_EVENT_DAYS):
                problems["ends_at"] = f"An event can last at most {MAX_EVENT_DAYS} days."
            elif ends <= now:
                problems["ends_at"] = "This event has already ended."
        if problems:
            return error("VALIDATION_ERROR", "Check the event and try again.", 400, fields=problems)
        event = LocalEvent(locality_id=locality.id, title=title, description=description, organizer=organizer,
                           venue=venue, category=category, starts_at=starts, ends_at=ends)
    event.status = LocalEventStatus.PENDING
    event.submitted_by_user_id = current_user.id
    event.created_at = event.updated_at = now
    db.session.add(event)
    db.session.flush()
    record(locality, "EVENT", event.id, "SUBMITTED", reason=None,
           changes={"shared_society_event": event.source_event_id is not None},
           audit_details={"title": event.title})
    db.session.commit()
    return store({"event": _event_json(event, now, mine=True)}, 201)


@locality_bp.get("/api/locality/events/mine")
@login_required
def my_events():
    locality, failure = locality_scope()
    if failure:
        return failure
    now = utc_now()
    rows = db.session.scalars(select(LocalEvent).where(
        LocalEvent.locality_id == locality.id, LocalEvent.submitted_by_user_id == current_user.id
    ).order_by(LocalEvent.created_at.desc())).all()
    return store({"events": [_event_json(row, now, mine=True) for row in rows]})


@locality_bp.get("/api/locality/events/shareable")
@login_required
def shareable_society_events():
    """Opted-in, published, not-yet-shared Module 3 events. No RSVP or capacity data."""
    if not has_permission("society.operations.manage"):
        return error("FORBIDDEN", "Only the Society Admin can share society events.", 403)
    locality, failure = locality_scope()
    if failure:
        return failure
    society = configured_society()
    shared = select(LocalEvent.source_event_id).where(LocalEvent.source_event_id.is_not(None))
    rows = db.session.scalars(select(SocietyEvent).where(
        SocietyEvent.society_id == society.id, SocietyEvent.status == EventStatus.PUBLISHED,
        SocietyEvent.locality_publish_requested.is_(True), SocietyEvent.ends_at > utc_now(),
        SocietyEvent.id.not_in(shared),
    ).order_by(SocietyEvent.starts_at.asc())).all()
    return store({"events": [{"id": str(row.id), "title": row.title, "venue": row.venue,
                              "starts_at": iso(row.starts_at), "ends_at": iso(row.ends_at)} for row in rows]})


@locality_bp.get("/api/locality/admin/events")
@manage_locality
def admin_list_events():
    locality, failure = locality_scope()
    if failure:
        return failure
    query = select(LocalEvent).where(LocalEvent.locality_id == locality.id)
    status = request.args.get("status")
    if status:
        problems: dict = {}
        value = enum_value(LocalEventStatus, status, "status", problems)
        if value is None:
            return error("VALIDATION_ERROR", "Unknown event status.", 400, fields=problems)
        query = query.where(LocalEvent.status == value)
    rows = db.session.scalars(query.order_by(LocalEvent.created_at.desc()).limit(100)).all()
    people = names([*(row.submitted_by_user_id for row in rows), *(row.reviewer_user_id for row in rows)])
    now = utc_now()
    events = []
    for row in rows:
        item = _event_json(row, now, people=people, staff=True)
        history = history_for("EVENT", row.id)
        item["history"] = history_json(history, names(entry.actor_user_id for entry in history), include_actor=True)
        events.append(item)
    return store({"events": events})


@locality_bp.post("/api/locality/admin/events/<uuid:event_id>/decision")
@manage_locality
def admin_decide_event(event_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"decision", "reason"})
    if failure:
        return failure
    problems: dict = {}
    decision = body.get("decision")
    if decision not in ("PUBLISH", "REJECT", "ARCHIVE"):
        problems["decision"] = "Use PUBLISH, REJECT or ARCHIVE."
    reason = text(body.get("reason"), "reason", 3, 1000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Give a decision and a reason.", 400, fields=problems)
    event = db.session.scalar(select(LocalEvent).where(
        LocalEvent.id == event_id, LocalEvent.locality_id == locality.id
    ).with_for_update())
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    allowed = {"PUBLISH": LocalEventStatus.PENDING, "REJECT": LocalEventStatus.PENDING,
               "ARCHIVE": LocalEventStatus.PUBLISHED}[decision]
    if event.status != allowed:
        return error("INVALID_STATUS_TRANSITION", f"A {event.status.value.lower()} event cannot be {decision.lower()}ed.", 409)
    now = utc_now()
    if decision == "PUBLISH":
        if aware(event.ends_at) <= now:
            return error("EVENT_ENDED", "This event has already ended; reject it instead.", 409)
        if event.source_event_id:
            problem = _society_event_problem(db.session.get(SocietyEvent, event.source_event_id), locality.society_id)
            if problem:
                return problem
    previous = event.status.value
    event.status = {"PUBLISH": LocalEventStatus.PUBLISHED, "REJECT": LocalEventStatus.REJECTED,
                    "ARCHIVE": LocalEventStatus.ARCHIVED}[decision]
    if decision == "PUBLISH":
        event.published_at = now
    event.reviewer_user_id = current_user.id
    event.decision_reason = reason
    event.updated_at = now
    record(locality, "EVENT", event.id, event.status.value, changes={"status": [previous, event.status.value]},
           reason=reason, audit_details={"decision": decision})
    db.session.commit()
    people = names([event.submitted_by_user_id, event.reviewer_user_id])
    return store({"event": _event_json(event, now, people=people, staff=True)})


# ------------------------------------------------------------------ alerts

def _alert_state(alert: LocalAlert, now) -> str:
    if alert.status == AlertStatus.ARCHIVED:
        return "ARCHIVED"
    if alert.status == AlertStatus.DRAFT:
        return "DRAFT"
    if aware(alert.expires_at) <= now:
        return "EXPIRED"
    if aware(alert.starts_at) > now:
        return "SCHEDULED"
    return "ACTIVE"


def _alert_json(alert: LocalAlert, now, *, people=None, staff=False) -> dict:
    payload = {
        "id": str(alert.id), "title": alert.title, "description": alert.description,
        "severity": alert.severity.value, "source_type": alert.source_type.value,
        "source_label": alert.source_label, "source_url": alert.source_url,
        "starts_at": iso(alert.starts_at), "expires_at": iso(alert.expires_at),
        "published_at": iso(alert.published_at), "archived_at": iso(alert.archived_at),
        "state": _alert_state(alert, now),
    }
    if staff:
        people = people or {}
        payload.update({"status": alert.status.value, "created_at": iso(alert.created_at),
                        "created_by_display_name": people.get(alert.created_by_user_id, ""),
                        "reviewer_display_name": people.get(alert.reviewer_user_id)})
    return payload


@locality_bp.get("/api/locality/alerts")
@read_locality
def list_alerts():
    locality, failure = locality_scope()
    if failure:
        return failure
    now = utc_now()
    rows = db.session.scalars(select(LocalAlert).where(
        LocalAlert.locality_id == locality.id,
        LocalAlert.status.in_((AlertStatus.PUBLISHED, AlertStatus.ARCHIVED)),
        LocalAlert.published_at.is_not(None),
    ).order_by(LocalAlert.starts_at.desc()).limit(100)).all()
    grouped = {"ACTIVE": [], "SCHEDULED": [], "PAST": []}
    for row in rows:
        state = _alert_state(row, now)
        grouped["PAST" if state in ("EXPIRED", "ARCHIVED") else state].append(_alert_json(row, now))
    grouped["ACTIVE"].sort(key=lambda item: (SEVERITY_RANK[AlertSeverity(item["severity"])], item["expires_at"]))
    grouped["SCHEDULED"].sort(key=lambda item: item["starts_at"])
    return store({"active": grouped["ACTIVE"], "scheduled": grouped["SCHEDULED"], "past": grouped["PAST"][:30]})


@locality_bp.get("/api/locality/admin/alerts")
@manage_locality
def admin_list_alerts():
    locality, failure = locality_scope()
    if failure:
        return failure
    rows = db.session.scalars(select(LocalAlert).where(LocalAlert.locality_id == locality.id)
                              .order_by(LocalAlert.created_at.desc()).limit(100)).all()
    people = names([*(row.created_by_user_id for row in rows), *(row.reviewer_user_id for row in rows)])
    now = utc_now()
    alerts = []
    for row in rows:
        item = _alert_json(row, now, people=people, staff=True)
        history = history_for("ALERT", row.id)
        item["history"] = history_json(history, names(entry.actor_user_id for entry in history), include_actor=True)
        alerts.append(item)
    return store({"alerts": alerts})


@locality_bp.post("/api/locality/admin/alerts")
@manage_locality
def admin_create_alert():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"title", "description", "severity", "source_type", "source_label", "source_url",
                                 "starts_at", "expires_at"})
    if failure:
        return failure
    problems: dict = {}
    title = text(body.get("title"), "title", 3, 160, problems)
    description = text(body.get("description"), "description", 10, 4000, problems)
    severity = enum_value(AlertSeverity, body.get("severity"), "severity", problems)
    source_type = enum_value(AlertSourceType, body.get("source_type"), "source_type", problems)
    source_label = text(body.get("source_label"), "source_label", 3, 200, problems)
    source_url = web_url(body.get("source_url"), "source_url", problems,
                         required=source_type == AlertSourceType.OFFICIAL_NOTICE)
    starts = parse_time(body.get("starts_at"), "starts_at", problems)
    expires = parse_time(body.get("expires_at"), "expires_at", problems)
    now = utc_now()
    if starts and expires:
        if expires <= starts:
            problems["expires_at"] = "Must be after the start."
        elif expires - starts > timedelta(days=MAX_ALERT_DAYS):
            problems["expires_at"] = f"An alert can run for at most {MAX_ALERT_DAYS} days."
        elif expires <= now:
            problems["expires_at"] = "Must be in the future."
    if problems:
        return error("VALIDATION_ERROR", "Check the alert and try again.", 400, fields=problems)
    alert = LocalAlert(locality_id=locality.id, title=title, description=description, severity=severity,
                       source_type=source_type, source_label=source_label, source_url=source_url,
                       starts_at=starts, expires_at=expires, status=AlertStatus.DRAFT,
                       created_by_user_id=current_user.id, created_at=now, updated_at=now)
    db.session.add(alert)
    db.session.flush()
    record(locality, "ALERT", alert.id, "DRAFTED", changes={"severity": [None, severity.value]},
           audit_details={"title": title, "severity": severity.value})
    db.session.commit()
    return store({"alert": _alert_json(alert, now, people=names([current_user.id]), staff=True)}, 201)


def _alert_action(alert_id, *, require_reason: bool):
    locality, failure = locality_scope()
    if failure:
        return None, None, None, failure
    body, failure = json_object({"reason"})
    if failure:
        return None, None, None, failure
    problems: dict = {}
    reason = text(body.get("reason"), "reason", 3, 500, problems, required=require_reason)
    if problems:
        return None, None, None, error("VALIDATION_ERROR", "Give a reason.", 400, fields=problems)
    alert = db.session.scalar(select(LocalAlert).where(
        LocalAlert.id == alert_id, LocalAlert.locality_id == locality.id
    ).with_for_update())
    if alert is None:
        return None, None, None, error("ALERT_NOT_FOUND", "Alert not found.", 404)
    return locality, alert, reason, None


@locality_bp.post("/api/locality/admin/alerts/<uuid:alert_id>/publish")
@manage_locality
def admin_publish_alert(alert_id):
    locality, alert, reason, failure = _alert_action(alert_id, require_reason=False)
    if failure:
        return failure
    if alert.status != AlertStatus.DRAFT:
        return error("INVALID_STATUS_TRANSITION", "Only a draft alert can be published.", 409)
    now = utc_now()
    if aware(alert.expires_at) <= now:
        return error("ALERT_EXPIRED", "This draft has already expired; archive it and create a new one.", 409)
    alert.status = AlertStatus.PUBLISHED
    alert.published_at = now
    alert.reviewer_user_id = current_user.id
    alert.updated_at = now
    record(locality, "ALERT", alert.id, "PUBLISHED", changes={"status": ["DRAFT", "PUBLISHED"]}, reason=reason,
           audit_details={"severity": alert.severity.value})
    db.session.commit()
    return store({"alert": _alert_json(alert, now, people=names([alert.created_by_user_id, alert.reviewer_user_id]),
                                       staff=True)})


@locality_bp.post("/api/locality/admin/alerts/<uuid:alert_id>/archive")
@manage_locality
def admin_archive_alert(alert_id):
    locality, alert, reason, failure = _alert_action(alert_id, require_reason=True)
    if failure:
        return failure
    if alert.status == AlertStatus.ARCHIVED:
        return error("INVALID_STATUS_TRANSITION", "This alert is already archived.", 409)
    now = utc_now()
    previous = alert.status.value
    alert.status = AlertStatus.ARCHIVED
    alert.archived_at = now
    alert.updated_at = now
    record(locality, "ALERT", alert.id, "ARCHIVED", changes={"status": [previous, "ARCHIVED"]}, reason=reason)
    db.session.commit()
    return store({"alert": _alert_json(alert, now, people=names([alert.created_by_user_id, alert.reviewer_user_id]),
                                       staff=True)})


# ------------------------------------------------------------------ feed

@locality_bp.get("/api/locality/feed")
@read_locality
def locality_feed():
    """Read-through view of published sources; nothing is copied into a feed table."""
    locality, failure = locality_scope()
    if failure:
        return failure
    now = utc_now()
    pinned, items = [], []
    for alert in db.session.scalars(select(LocalAlert).where(
        LocalAlert.locality_id == locality.id, LocalAlert.status == AlertStatus.PUBLISHED,
        LocalAlert.starts_at <= now, LocalAlert.expires_at > now,
    )):
        pinned.append({"kind": "ALERT", "id": str(alert.id), "title": alert.title, "summary": alert.description,
                       "severity": alert.severity.value, "source_label": alert.source_label,
                       "occurred_at": iso(alert.published_at), "expires_at": iso(alert.expires_at),
                       "link": "/locality/alerts", "reportable": True})
    pinned.sort(key=lambda item: (SEVERITY_RANK[AlertSeverity(item["severity"])], item["occurred_at"] or ""))
    for event in db.session.scalars(_visible_events(locality).where(
        LocalEvent.ends_at > now - timedelta(days=7), LocalEvent.starts_at < now + timedelta(days=60)
    )):
        items.append({"kind": "EVENT", "id": str(event.id), "title": event.title,
                      "summary": f"{event.venue} · organised by {event.organizer}",
                      "starts_at": iso(event.starts_at), "timing": _timing(event, now),
                      "occurred_at": iso(event.published_at), "link": "/locality/events", "reportable": True})
    updates = _directory_updates(locality, now)
    labels = {"CREATED": "New listing", "CORRECTION_APPLIED": "Listing corrected", "VERIFIED": "Listing re-verified"}
    for entry, place in updates:
        fields = [key for key in (entry.changes or {}) if key not in ("correction_id", "verification_state")]
        detail = f" ({', '.join(field.replace('_', ' ') for field in fields)} updated)" if entry.action == "CORRECTION_APPLIED" and fields else ""
        items.append({"kind": "DIRECTORY_UPDATE", "id": str(entry.id), "title": f"{labels[entry.action]}: {place.name}",
                      "summary": f"Directory information changed{detail}.", "occurred_at": iso(entry.created_at),
                      "link": f"/locality/places/{place.id}", "reportable": False})
    items.sort(key=lambda item: item["occurred_at"] or "", reverse=True)
    return store({"pinned": pinned, "items": items[:40]})


def _directory_updates(locality, now):
    """Recent public directory changes on active places (history ids are text, so resolve in Python)."""
    from uuid import UUID
    entries = db.session.scalars(select(LocalityHistory).where(
        LocalityHistory.locality_id == locality.id, LocalityHistory.entity_type == "PLACE",
        LocalityHistory.action.in_(("CREATED", "CORRECTION_APPLIED", "VERIFIED")),
        LocalityHistory.created_at > now - timedelta(days=30),
    ).order_by(LocalityHistory.created_at.desc()).limit(20)).all()
    rows = []
    for entry in entries:
        place = db.session.get(Place, UUID(entry.entity_id))
        if place is not None and place.publication_status == PublicationStatus.ACTIVE:
            rows.append((entry, place))
    return rows


# ------------------------------------------------------------------ content reports

def _report_target(locality, target_type, target_id, *, published_only=True):
    if target_type == ReportTarget.EVENT:
        query = select(LocalEvent).where(LocalEvent.id == target_id, LocalEvent.locality_id == locality.id)
        if published_only:
            query = query.where(LocalEvent.status == LocalEventStatus.PUBLISHED)
    else:
        query = select(LocalAlert).where(LocalAlert.id == target_id, LocalAlert.locality_id == locality.id)
        if published_only:
            query = query.where(LocalAlert.status == AlertStatus.PUBLISHED)
    return db.session.scalar(query)


@locality_bp.post("/api/locality/reports")
@suggest_locality
def report_content():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"target_type", "target_id", "reason"})
    if failure:
        return failure
    problems: dict = {}
    target_type = enum_value(ReportTarget, body.get("target_type"), "target_type", problems)
    reason = text(body.get("reason"), "reason", 10, 500, problems)
    try:
        from uuid import UUID
        target_id = UUID(str(body.get("target_id")))
    except ValueError:
        problems["target_id"] = "Invalid id."
        target_id = None
    if problems:
        return error("VALIDATION_ERROR", "Check the report and try again.", 400, fields=problems)
    if _report_target(locality, target_type, target_id) is None:
        return error("CONTENT_NOT_FOUND", "Published content not found.", 404)
    if db.session.scalar(select(LocalityContentReport.id).where(
        LocalityContentReport.target_id == target_id, LocalityContentReport.reporter_user_id == current_user.id,
        LocalityContentReport.status == ReportStatus.OPEN,
    )) is not None:
        return error("ALREADY_REPORTED", "You already reported this; a coordinator will review it.", 409)
    report = LocalityContentReport(locality_id=locality.id, target_type=target_type, target_id=target_id,
                                   reporter_user_id=current_user.id, reason=reason, status=ReportStatus.OPEN)
    db.session.add(report)
    db.session.flush()
    record(locality, "REPORT", report.id, "REPORTED", changes={"target": [None, f"{target_type.value}:{target_id}"]},
           reason=reason)
    db.session.commit()
    return store({"report": {"id": str(report.id), "status": report.status.value}}, 201)


@locality_bp.get("/api/locality/admin/reports")
@manage_locality
def admin_list_reports():
    locality, failure = locality_scope()
    if failure:
        return failure
    query = select(LocalityContentReport).where(LocalityContentReport.locality_id == locality.id)
    status = request.args.get("status")
    if status:
        problems: dict = {}
        value = enum_value(ReportStatus, status, "status", problems)
        if value is None:
            return error("VALIDATION_ERROR", "Unknown report status.", 400, fields=problems)
        query = query.where(LocalityContentReport.status == value)
    rows = db.session.scalars(query.order_by(LocalityContentReport.created_at.desc()).limit(100)).all()
    people = names([*(row.reporter_user_id for row in rows), *(row.reviewer_user_id for row in rows)])
    reports = []
    for row in rows:
        target = _report_target(locality, row.target_type, row.target_id, published_only=False)
        reports.append({
            "id": str(row.id), "target_type": row.target_type.value, "target_id": str(row.target_id),
            "target_title": target.title if target else None,
            "target_status": target.status.value if target else None,
            "reason": row.reason, "status": row.status.value, "review_note": row.review_note,
            "reporter_display_name": people.get(row.reporter_user_id, ""),
            "reviewer_display_name": people.get(row.reviewer_user_id),
            "created_at": iso(row.created_at), "reviewed_at": iso(row.reviewed_at),
        })
    return store({"reports": reports})


@locality_bp.post("/api/locality/admin/reports/<uuid:report_id>/decision")
@manage_locality
def admin_decide_report(report_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"decision", "reason"})
    if failure:
        return failure
    problems: dict = {}
    decision = body.get("decision")
    if decision not in ("DISMISS", "ARCHIVE_CONTENT"):
        problems["decision"] = "Use DISMISS or ARCHIVE_CONTENT."
    reason = text(body.get("reason"), "reason", 3, 500, problems)
    if problems:
        return error("VALIDATION_ERROR", "Give a decision and a reason.", 400, fields=problems)
    report = db.session.scalar(select(LocalityContentReport).where(
        LocalityContentReport.id == report_id, LocalityContentReport.locality_id == locality.id
    ).with_for_update())
    if report is None:
        return error("REPORT_NOT_FOUND", "Report not found.", 404)
    if report.status != ReportStatus.OPEN:
        return error("INVALID_STATUS_TRANSITION", "This report was already reviewed.", 409)
    now = utc_now()
    reports = [report]
    if decision == "ARCHIVE_CONTENT":
        target = _report_target(locality, report.target_type, report.target_id, published_only=False)
        if target is not None and target.status.value != "ARCHIVED":
            previous = target.status.value
            target.status = LocalEventStatus.ARCHIVED if report.target_type == ReportTarget.EVENT else AlertStatus.ARCHIVED
            target.updated_at = now
            if report.target_type == ReportTarget.ALERT:
                target.archived_at = now
            record(locality, report.target_type.value, target.id, "ARCHIVED",
                   changes={"status": [previous, "ARCHIVED"], "report_id": str(report.id)}, reason=reason)
        # Every open report on the same content is settled by this action.
        reports = db.session.scalars(select(LocalityContentReport).where(
            LocalityContentReport.target_id == report.target_id, LocalityContentReport.status == ReportStatus.OPEN
        )).all()
    for item in reports:
        item.status = ReportStatus.ACTIONED if decision == "ARCHIVE_CONTENT" else ReportStatus.DISMISSED
        item.reviewer_user_id = current_user.id
        item.review_note = reason
        item.reviewed_at = now
        record(locality, "REPORT", item.id, item.status.value, reason=reason)
    db.session.commit()
    return store({"report": {"id": str(report.id), "status": report.status.value}})
