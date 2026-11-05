"""Society events with capacity-limited RSVP and a first-come waitlist.

Events are society-private. `locality_publish_requested` only records an
opt-in for Module 4; it never publishes anything by itself.
"""
from uuid import UUID

from flask import Blueprint
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now

from .common import (
    aware, audit, integer, iso, manage_operations, names, no_store, pagination, resident_read, schema_missing,
    society_or_error, text, when,
)
from .models import EventRsvp, EventStatus, EventUpdate, EventVolunteer, RsvpStatus, SocietyEvent

events_bp = Blueprint("operations_events", __name__)
VISIBLE = (EventStatus.PUBLISHED, EventStatus.CLOSED, EventStatus.CANCELLED)


def _counts(event_ids) -> dict:
    if not event_ids:
        return {}
    rows = db.session.execute(
        select(EventRsvp.event_id, EventRsvp.status, func.count())
        .where(EventRsvp.event_id.in_(event_ids)).group_by(EventRsvp.event_id, EventRsvp.status)
    ).all()
    counts: dict = {}
    for event_id, status, total in rows:
        counts.setdefault(event_id, {})[status] = total
    return counts


def _mine(event_ids) -> dict:
    if not event_ids:
        return {}
    rows = db.session.execute(select(EventRsvp.event_id, EventRsvp.status).where(
        EventRsvp.event_id.in_(event_ids), EventRsvp.user_id == current_user.id,
    )).all()
    return {row[0]: row[1].value for row in rows}


def _volunteers(event_ids) -> tuple[dict, set]:
    """Per-event volunteer counts, and the events the caller volunteers for."""
    if not event_ids:
        return {}, set()
    rows = db.session.execute(select(EventVolunteer.event_id, EventVolunteer.user_id).where(
        EventVolunteer.event_id.in_(event_ids),
    )).all()
    counts: dict = {}
    for event_id, _ in rows:
        counts[event_id] = counts.get(event_id, 0) + 1
    return counts, {event_id for event_id, user_id in rows if user_id == current_user.id}


def _updates(event_ids) -> dict:
    if not event_ids:
        return {}
    rows = db.session.scalars(select(EventUpdate).where(EventUpdate.event_id.in_(event_ids))
                              .order_by(EventUpdate.created_at.asc(), EventUpdate.id.asc())).all()
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.event_id, []).append({"message": row.message, "created_at": iso(row.created_at)})
    return grouped


def _events_payload(rows, *, admin=False) -> list[dict]:
    ids = [row.id for row in rows]
    counts = _counts(ids)
    mine = _mine(ids)
    volunteer_counts, volunteering = _volunteers(ids)
    updates = _updates(ids)
    organizers = names(row.organizer_user_id for row in rows)
    payload = []
    for row in rows:
        tally = counts.get(row.id, {})
        body = {
            "id": str(row.id),
            "title": row.title,
            "description": row.description,
            "venue": row.venue,
            "starts_at": iso(row.starts_at),
            "ends_at": iso(row.ends_at),
            "capacity": row.capacity,
            "status": row.status.value,
            "organizer_display_name": organizers.get(row.organizer_user_id, ""),
            "going_count": tally.get(RsvpStatus.GOING, 0),
            "waitlist_count": tally.get(RsvpStatus.WAITLISTED, 0),
            "my_rsvp": mine.get(row.id),
            "volunteer_slots": row.volunteer_slots,
            "volunteer_count": volunteer_counts.get(row.id, 0),
            "i_volunteered": row.id in volunteering,
            "updates": updates.get(row.id, []),
        }
        if admin:
            body["locality_publish_requested"] = row.locality_publish_requested
        payload.append(body)
    return payload


def _event(event_id, society_id, *, lock=False, statuses=None):
    query = select(SocietyEvent).where(SocietyEvent.id == event_id, SocietyEvent.society_id == society_id)
    if statuses:
        query = query.where(SocietyEvent.status.in_(statuses))
    if lock:
        query = query.with_for_update()
    return db.session.scalar(query)


def _going(event_id) -> int:
    return db.session.scalar(select(func.count()).select_from(EventRsvp).where(
        EventRsvp.event_id == event_id, EventRsvp.status == RsvpStatus.GOING,
    )) or 0


# ---------------------------------------------------------------- resident

@events_bp.get("/api/events")
@resident_read
def list_events():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    page = pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    rows = db.session.scalars(
        select(SocietyEvent).where(SocietyEvent.society_id == society.id, SocietyEvent.status.in_(VISIBLE))
        .order_by(SocietyEvent.starts_at.desc(), SocietyEvent.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"events": _events_payload(rows), "pagination": {"limit": limit, "offset": offset}})


@events_bp.get("/api/events/<uuid:event_id>")
@resident_read
def get_event(event_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, statuses=VISIBLE)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    return no_store({"event": _events_payload([event])[0]})


@events_bp.post("/api/events/<uuid:event_id>/rsvp")
@resident_read
def rsvp(event_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, lock=True, statuses=VISIBLE)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    now = utc_now()
    if event.status != EventStatus.PUBLISHED or aware(event.starts_at) <= now:
        db.session.rollback()
        return error("EVENT_CLOSED", "RSVP is closed for this event.", 409)
    existing = db.session.scalar(select(EventRsvp).where(
        EventRsvp.event_id == event.id, EventRsvp.user_id == current_user.id,
    ).with_for_update())
    if existing is not None and existing.status != RsvpStatus.CANCELLED:
        db.session.rollback()
        return error("ALREADY_RESPONDED", "You have already responded to this event.", 409)
    status = RsvpStatus.GOING if _going(event.id) < event.capacity else RsvpStatus.WAITLISTED
    if existing is None:
        db.session.add(EventRsvp(event_id=event.id, user_id=current_user.id, status=status, created_at=now, updated_at=now))
    else:
        # Rejoining goes to the back of the queue.
        existing.status = status
        existing.created_at = now
        existing.updated_at = now
    audit("EVENT_RSVP", "SOCIETY_EVENT", event.id, {"status": status.value})
    db.session.commit()
    return no_store({"event": _events_payload([event])[0]}, 201)


@events_bp.delete("/api/events/<uuid:event_id>/rsvp")
@resident_read
def cancel_rsvp(event_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, lock=True, statuses=VISIBLE)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    mine = db.session.scalar(select(EventRsvp).where(
        EventRsvp.event_id == event.id, EventRsvp.user_id == current_user.id,
        EventRsvp.status != RsvpStatus.CANCELLED,
    ).with_for_update())
    if mine is None:
        db.session.rollback()
        return error("RSVP_NOT_FOUND", "You have not responded to this event.", 404)
    now = utc_now()
    was_going = mine.status == RsvpStatus.GOING
    mine.status = RsvpStatus.CANCELLED
    mine.updated_at = now
    promoted = None
    if was_going and event.status == EventStatus.PUBLISHED:
        promoted = db.session.scalar(select(EventRsvp).where(
            EventRsvp.event_id == event.id, EventRsvp.status == RsvpStatus.WAITLISTED,
        ).order_by(EventRsvp.created_at.asc(), EventRsvp.id.asc()).limit(1).with_for_update())
        if promoted is not None:
            promoted.status = RsvpStatus.GOING
            promoted.updated_at = now
    audit("EVENT_RSVP_CANCELLED", "SOCIETY_EVENT", event.id, {"promoted": promoted is not None})
    db.session.commit()
    return no_store({"event": _events_payload([event])[0]})


@events_bp.post("/api/events/<uuid:event_id>/volunteer")
@resident_read
def volunteer(event_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"note"})
    if failure:
        return failure
    problems: dict = {}
    note = text(body.get("note"), "note", 0, 200, problems, required=False) or ""
    if problems:
        return error("VALIDATION_ERROR", "Check the note and try again.", 400, fields=problems)
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, lock=True, statuses=VISIBLE)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    if event.status != EventStatus.PUBLISHED or aware(event.starts_at) <= utc_now():
        db.session.rollback()
        return error("EVENT_CLOSED", "Volunteering is closed for this event.", 409)
    if db.session.scalar(select(EventVolunteer.id).where(
        EventVolunteer.event_id == event.id, EventVolunteer.user_id == current_user.id,
    )) is not None:
        db.session.rollback()
        return error("ALREADY_VOLUNTEERED", "You have already volunteered for this event.", 409)
    taken = db.session.scalar(select(func.count()).select_from(EventVolunteer).where(
        EventVolunteer.event_id == event.id)) or 0
    if taken >= event.volunteer_slots:
        db.session.rollback()
        return error("VOLUNTEER_SLOTS_FULL", "No volunteer places are left for this event.", 409)
    db.session.add(EventVolunteer(event_id=event.id, user_id=current_user.id, note=note))
    audit("EVENT_VOLUNTEERED", "SOCIETY_EVENT", event.id, None)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("ALREADY_VOLUNTEERED", "You have already volunteered for this event.", 409)
    return no_store({"event": _events_payload([event])[0]}, 201)


@events_bp.delete("/api/events/<uuid:event_id>/volunteer")
@resident_read
def withdraw_volunteer(event_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, statuses=VISIBLE)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    row = db.session.scalar(select(EventVolunteer).where(
        EventVolunteer.event_id == event.id, EventVolunteer.user_id == current_user.id,
    ))
    if row is None:
        return error("VOLUNTEER_NOT_FOUND", "You are not volunteering for this event.", 404)
    db.session.delete(row)
    audit("EVENT_VOLUNTEER_WITHDRAWN", "SOCIETY_EVENT", event.id, None)
    db.session.commit()
    return no_store({"event": _events_payload([event])[0]})


# ---------------------------------------------------------------- admin

@events_bp.post("/api/events/<uuid:event_id>/updates")
@manage_operations
def post_event_update(event_id):
    """Organiser announcement shown on the event to residents."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"message"})
    if failure:
        return failure
    problems: dict = {}
    message = text(body.get("message"), "message", 1, 2000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the update and try again.", 400, fields=problems)
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, statuses=(EventStatus.DRAFT, EventStatus.PUBLISHED))
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found or no longer open.", 404)
    db.session.add(EventUpdate(event_id=event.id, actor_user_id=current_user.id, message=message))
    event.updated_at = utc_now()
    audit("EVENT_UPDATE_POSTED", "SOCIETY_EVENT", event.id, None)
    db.session.commit()
    return no_store({"event": _events_payload([event], admin=True)[0]}, 201)


@events_bp.get("/api/admin/events")
@manage_operations
def admin_list_events():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    page = pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    rows = db.session.scalars(
        select(SocietyEvent).where(SocietyEvent.society_id == society.id)
        .order_by(SocietyEvent.starts_at.desc(), SocietyEvent.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"events": _events_payload(rows, admin=True), "pagination": {"limit": limit, "offset": offset}})


@events_bp.post("/api/events")
@manage_operations
def create_event():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({
        "title", "description", "venue", "starts_at", "ends_at", "capacity", "locality_publish_requested",
        "volunteer_slots",
    })
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    problems: dict = {}
    title = text(body.get("title"), "title", 3, 160, problems)
    description = text(body.get("description"), "description", 1, 8000, problems)
    venue = text(body.get("venue"), "venue", 2, 160, problems)
    starts_at = when(body.get("starts_at"), "starts_at", problems)
    ends_at = when(body.get("ends_at"), "ends_at", problems)
    capacity = integer(body.get("capacity"), "capacity", 1, 5000, problems)
    volunteer_slots = integer(body.get("volunteer_slots", 0), "volunteer_slots", 0, 200, problems)
    locality = body.get("locality_publish_requested", False)
    if not isinstance(locality, bool):
        problems["locality_publish_requested"] = "Must be true or false."
    now = utc_now()
    if starts_at and ends_at:
        if ends_at <= starts_at:
            problems["ends_at"] = "End must be after start."
        elif starts_at < now:
            problems["starts_at"] = "Events cannot start in the past."
    if problems:
        return error("VALIDATION_ERROR", "Check the event and try again.", 400, fields=problems)
    event = SocietyEvent(
        society_id=society.id, organizer_user_id=current_user.id, title=title, description=description,
        venue=venue, starts_at=starts_at, ends_at=ends_at, capacity=capacity, volunteer_slots=volunteer_slots,
        status=EventStatus.DRAFT,
        locality_publish_requested=locality, created_at=now, updated_at=now,
    )
    db.session.add(event)
    db.session.flush()
    audit("EVENT_CREATED", "SOCIETY_EVENT", event.id, {"title": title, "capacity": capacity})
    db.session.commit()
    return no_store({"event": _events_payload([event], admin=True)[0]}, 201)


EVENT_ACTIONS = {
    "publish": ({EventStatus.DRAFT}, EventStatus.PUBLISHED, "EVENT_PUBLISHED"),
    "cancel": ({EventStatus.DRAFT, EventStatus.PUBLISHED}, EventStatus.CANCELLED, "EVENT_CANCELLED"),
    "close": ({EventStatus.PUBLISHED}, EventStatus.CLOSED, "EVENT_CLOSED"),
}


@events_bp.post("/api/events/<uuid:event_id>/<any(publish, cancel, close):action>")
@manage_operations
def change_event(event_id, action):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id, lock=True)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    allowed, target, code = EVENT_ACTIONS[action]
    if event.status not in allowed:
        db.session.rollback()
        return error("INVALID_TRANSITION", f"Cannot {action} an event that is {event.status.value}.", 409)
    event.status = target
    event.updated_at = utc_now()
    audit(code, "SOCIETY_EVENT", event.id, {"status": target.value})
    db.session.commit()
    return no_store({"event": _events_payload([event], admin=True)[0]})


@events_bp.get("/api/admin/events/<uuid:event_id>/attendees")
@manage_operations
def event_attendees(event_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    event = _event(event_id, society.id)
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    rows = db.session.scalars(
        select(EventRsvp).where(EventRsvp.event_id == event.id, EventRsvp.status != RsvpStatus.CANCELLED)
        .order_by(EventRsvp.status.asc(), EventRsvp.created_at.asc())
    ).all()
    helpers = db.session.scalars(select(EventVolunteer).where(EventVolunteer.event_id == event.id)
                                 .order_by(EventVolunteer.created_at.asc())).all()
    people = names([row.user_id for row in rows] + [row.user_id for row in helpers])
    return no_store({
        "attendees": [{
            "user_id": str(row.user_id), "display_name": people.get(row.user_id, ""),
            "status": row.status.value, "attended": row.attended,
        } for row in rows],
        "volunteers": [{
            "user_id": str(row.user_id), "display_name": people.get(row.user_id, ""), "note": row.note,
        } for row in helpers],
    })


@events_bp.post("/api/events/<uuid:event_id>/attendance")
@manage_operations
def mark_attendance(event_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"user_id", "attended"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    if not isinstance(body.get("attended"), bool) or not isinstance(body.get("user_id"), str):
        return error("VALIDATION_ERROR", "Provide user_id and attended.", 400)
    event = _event(event_id, society.id, statuses=(EventStatus.PUBLISHED, EventStatus.CLOSED))
    if event is None:
        return error("EVENT_NOT_FOUND", "Event not found.", 404)
    try:
        user_id = UUID(body["user_id"])
    except ValueError:
        return error("VALIDATION_ERROR", "Provide user_id and attended.", 400)
    row = db.session.scalar(select(EventRsvp).where(
        EventRsvp.event_id == event.id, EventRsvp.user_id == user_id, EventRsvp.status == RsvpStatus.GOING,
    ))
    if row is None:
        return error("RSVP_NOT_FOUND", "That resident is not on the going list.", 404)
    row.attended = body["attended"]
    row.updated_at = utc_now()
    audit("EVENT_ATTENDANCE", "SOCIETY_EVENT", event.id, {"user_id": str(user_id), "attended": row.attended})
    db.session.commit()
    return no_store({"user_id": str(user_id), "attended": row.attended})
