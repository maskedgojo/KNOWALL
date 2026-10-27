"""Amenity catalogue and conflict-free bookings.

Bookings that are PENDING or CONFIRMED hold their slot. Overlap is checked
while the facility row is locked, so two concurrent requests for one slot
cannot both succeed on PostgreSQL.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from flask import Blueprint, request
from flask_login import current_user
from sqlalchemy import func, select

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now

from .common import (
    SOCIETY_TZ, aware, audit, book_facilities, current_membership, integer, iso, manage_operations, names,
    no_store, pagination, schema_missing, society_or_error, text, when,
)
from .models import Booking, BookingEvent, BookingStatus, Facility, FacilityBlackout

facilities_bp = Blueprint("operations_facilities", __name__)
HOLDING = (BookingStatus.PENDING, BookingStatus.CONFIRMED)
FACILITY_FIELDS = {
    "name", "description", "location", "capacity", "open_minute", "close_minute", "slot_minutes",
    "max_minutes_per_booking", "booking_window_days", "requires_approval", "is_active", "max_upcoming_per_resident",
}


def _facility_json(row: Facility) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "location": row.location,
        "capacity": row.capacity,
        "open_minute": row.open_minute,
        "close_minute": row.close_minute,
        "slot_minutes": row.slot_minutes,
        "max_minutes_per_booking": row.max_minutes_per_booking,
        "booking_window_days": row.booking_window_days,
        "requires_approval": row.requires_approval,
        "is_active": row.is_active,
        "max_upcoming_per_resident": row.max_upcoming_per_resident,
    }


def _history(booking_ids) -> dict:
    if not booking_ids:
        return {}
    rows = db.session.scalars(
        select(BookingEvent).where(BookingEvent.booking_id.in_(booking_ids))
        .order_by(BookingEvent.created_at.asc(), BookingEvent.id.asc())
    ).all()
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.booking_id, []).append({
            "from_status": row.from_status, "to_status": row.to_status,
            "reason": row.reason, "created_at": iso(row.created_at),
        })
    return grouped


def _booking_json(row: Booking, facilities: dict, people: dict, history: dict, *, admin=False) -> dict:
    facility = facilities.get(row.facility_id)
    body = {
        "id": str(row.id),
        "facility_id": str(row.facility_id),
        "facility_name": facility.name if facility else "",
        "starts_at": iso(row.starts_at),
        "ends_at": iso(row.ends_at),
        "purpose": row.purpose,
        "status": row.status.value,
        "decision_reason": row.decision_reason,
        "created_at": iso(row.created_at),
        "history": history.get(row.id, []),
    }
    if admin:
        body["resident_display_name"] = people.get(row.user_id, "")
    return body


def _bookings_payload(rows, *, admin=False) -> list[dict]:
    facility_ids = {row.facility_id for row in rows}
    facilities = {
        item.id: item for item in db.session.scalars(select(Facility).where(Facility.id.in_(facility_ids))).all()
    } if facility_ids else {}
    people = names(row.user_id for row in rows) if admin else {}
    history = _history([row.id for row in rows])
    return [_booking_json(row, facilities, people, history, admin=admin) for row in rows]


def _record(booking: Booking, from_status, to_status: BookingStatus, reason=None, actor=True):
    db.session.add(BookingEvent(
        booking_id=booking.id, actor_user_id=current_user.id if actor else None,
        from_status=from_status.value if from_status else None, to_status=to_status.value, reason=reason,
    ))


def _overlap_query(facility_id, starts_at, ends_at):
    return select(Booking).where(
        Booking.facility_id == facility_id,
        Booking.status.in_(HOLDING),
        Booking.starts_at < ends_at,
        Booking.ends_at > starts_at,
    )


def _blackout_overlaps(facility_id, starts_at, ends_at) -> bool:
    return db.session.scalar(select(FacilityBlackout.id).where(
        FacilityBlackout.facility_id == facility_id,
        FacilityBlackout.starts_at < ends_at,
        FacilityBlackout.ends_at > starts_at,
    ).limit(1)) is not None


def _find_facility(facility_id, society_id, *, lock=False, active_only=True):
    query = select(Facility).where(Facility.id == facility_id, Facility.society_id == society_id)
    if active_only:
        query = query.where(Facility.is_active.is_(True))
    if lock:
        query = query.with_for_update()
    return db.session.scalar(query)


def _slot_problems(facility: Facility, starts_at: datetime, ends_at: datetime, now: datetime) -> dict:
    problems: dict = {}
    if ends_at <= starts_at:
        problems["ends_at"] = "End time must be after start time."
        return problems
    local_start = starts_at.astimezone(SOCIETY_TZ)
    start_minute = local_start.hour * 60 + local_start.minute
    duration = int((ends_at - starts_at).total_seconds() // 60)
    # close_minute <= 1440, so this also keeps a booking within one local day.
    end_minute = start_minute + duration
    if starts_at < now:
        problems["starts_at"] = "Bookings cannot start in the past."
    elif starts_at > now + timedelta(days=facility.booking_window_days):
        problems["starts_at"] = f"Book at most {facility.booking_window_days} days ahead."
    if start_minute < facility.open_minute or end_minute > facility.close_minute:
        problems["starts_at"] = "Choose a time within operating hours."
    elif local_start.second or (start_minute - facility.open_minute) % facility.slot_minutes \
            or duration % facility.slot_minutes:
        problems["starts_at"] = f"Use {facility.slot_minutes}-minute slots from opening time."
    if duration > facility.max_minutes_per_booking:
        problems["ends_at"] = f"A booking can last at most {facility.max_minutes_per_booking} minutes."
    return problems


# ---------------------------------------------------------------- resident

@facilities_bp.get("/api/facilities")
@book_facilities
def list_facilities():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    rows = db.session.scalars(
        select(Facility).where(Facility.society_id == society.id, Facility.is_active.is_(True)).order_by(Facility.name)
    ).all()
    return no_store({"facilities": [_facility_json(row) for row in rows]})


@facilities_bp.get("/api/facilities/<uuid:facility_id>/availability")
@book_facilities
def facility_availability(facility_id):
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    facility = _find_facility(facility_id, society.id)
    if facility is None:
        return error("FACILITY_NOT_FOUND", "Facility not found.", 404)
    try:
        local_day = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return error("VALIDATION_ERROR", "Use ?date=YYYY-MM-DD.", 400, fields={"date": "Use YYYY-MM-DD."})
    day_start = datetime(local_day.year, local_day.month, local_day.day, tzinfo=SOCIETY_TZ)
    opens = (day_start + timedelta(minutes=facility.open_minute)).astimezone(timezone.utc)
    closes = (day_start + timedelta(minutes=facility.close_minute)).astimezone(timezone.utc)
    taken = db.session.scalars(_overlap_query(facility.id, opens, closes)).all()
    blackouts = db.session.scalars(select(FacilityBlackout).where(
        FacilityBlackout.facility_id == facility.id,
        FacilityBlackout.starts_at < closes, FacilityBlackout.ends_at > opens,
    )).all()
    now = utc_now()
    window_end = now + timedelta(days=facility.booking_window_days)
    slots = []
    cursor = opens
    while cursor + timedelta(minutes=facility.slot_minutes) <= closes:
        slot_end = cursor + timedelta(minutes=facility.slot_minutes)
        reason = None
        if cursor < now:
            reason = "PAST"
        elif cursor > window_end:
            reason = "OUTSIDE_BOOKING_WINDOW"
        elif any(aware(b.starts_at) < slot_end and aware(b.ends_at) > cursor for b in blackouts):
            reason = "BLOCKED"
        elif any(aware(b.starts_at) < slot_end and aware(b.ends_at) > cursor for b in taken):
            reason = "BOOKED"
        slots.append({"starts_at": iso(cursor), "ends_at": iso(slot_end), "available": reason is None, "reason": reason})
        cursor = slot_end
    return no_store({"facility": _facility_json(facility), "date": local_day.isoformat(), "slots": slots})


@facilities_bp.post("/api/bookings")
@book_facilities
def create_booking():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"facility_id", "starts_at", "ends_at", "purpose"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    membership = current_membership()
    if membership is None:
        return error("FORBIDDEN", "An active society membership is required to book.", 403)
    problems: dict = {}
    purpose = text(body.get("purpose"), "purpose", 3, 300, problems)
    starts_at = when(body.get("starts_at"), "starts_at", problems)
    ends_at = when(body.get("ends_at"), "ends_at", problems)
    raw_id = body.get("facility_id")
    facility = None
    if not isinstance(raw_id, str):
        problems["facility_id"] = "Choose a facility."
    else:
        try:
            facility = _find_facility(UUID(raw_id), society.id, lock=True)
        except ValueError:
            problems["facility_id"] = "Choose a facility."
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the booking and try again.", 400, fields=problems)
    if facility is None:
        db.session.rollback()
        return error("FACILITY_NOT_FOUND", "Facility not found.", 404)
    now = utc_now()
    problems = _slot_problems(facility, starts_at, ends_at, now)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the booking and try again.", 400, fields=problems)
    if _blackout_overlaps(facility.id, starts_at, ends_at):
        db.session.rollback()
        return error("FACILITY_UNAVAILABLE", "The facility is closed for that time.", 409)
    if db.session.scalar(_overlap_query(facility.id, starts_at, ends_at).limit(1)) is not None:
        db.session.rollback()
        return error("SLOT_UNAVAILABLE", "That time is already booked.", 409)
    if facility.max_upcoming_per_resident is not None:
        # Checked under the facility lock, so parallel requests cannot exceed the cap.
        held = db.session.scalar(select(func.count()).select_from(Booking).where(
            Booking.facility_id == facility.id, Booking.user_id == current_user.id,
            Booking.status.in_(HOLDING), Booking.ends_at > now,
        )) or 0
        if held >= facility.max_upcoming_per_resident:
            db.session.rollback()
            return error(
                "BOOKING_LIMIT_REACHED",
                f"You can hold at most {facility.max_upcoming_per_resident} upcoming bookings for {facility.name}.",
                409,
            )
    status = BookingStatus.PENDING if facility.requires_approval else BookingStatus.CONFIRMED
    booking = Booking(
        facility_id=facility.id, user_id=current_user.id, membership_id=membership.id,
        starts_at=starts_at, ends_at=ends_at, purpose=purpose, status=status, created_at=now, updated_at=now,
    )
    db.session.add(booking)
    db.session.flush()
    _record(booking, None, status, None if facility.requires_approval else "Auto-confirmed by facility rule.")
    audit("BOOKING_REQUESTED", "BOOKING", booking.id, {"facility": facility.name, "status": status.value})
    db.session.commit()
    return no_store({"booking": _bookings_payload([booking])[0]}, 201)


@facilities_bp.get("/api/bookings/me")
@book_facilities
def my_bookings():
    missing = schema_missing()
    if missing:
        return missing
    page = pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    rows = db.session.scalars(
        select(Booking).where(Booking.user_id == current_user.id)
        .order_by(Booking.starts_at.desc(), Booking.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"bookings": _bookings_payload(rows), "pagination": {"limit": limit, "offset": offset}})


@facilities_bp.post("/api/bookings/<uuid:booking_id>/cancel")
@book_facilities
def cancel_booking(booking_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"reason"})
    if failure:
        return failure
    problems: dict = {}
    reason = text(body.get("reason"), "reason", 1, 300, problems, required=False)
    if problems:
        return error("VALIDATION_ERROR", "Check the reason and try again.", 400, fields=problems)
    booking = db.session.scalar(
        select(Booking).where(Booking.id == booking_id, Booking.user_id == current_user.id).with_for_update()
    )
    if booking is None:
        return error("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.status not in HOLDING:
        db.session.rollback()
        return error("INVALID_STATE", "Only pending or confirmed bookings can be cancelled.", 409)
    now = utc_now()
    if aware(booking.starts_at) <= now:
        db.session.rollback()
        return error("INVALID_STATE", "A booking that has started cannot be cancelled.", 409)
    previous = booking.status
    booking.status = BookingStatus.CANCELLED
    booking.decision_reason = reason or "Cancelled by resident."
    booking.updated_at = now
    _record(booking, previous, BookingStatus.CANCELLED, booking.decision_reason)
    audit("BOOKING_CANCELLED", "BOOKING", booking.id, {"from": previous.value})
    db.session.commit()
    return no_store({"booking": _bookings_payload([booking])[0]})


# ---------------------------------------------------------------- admin

def _facility_fields(body: dict, problems: dict, existing: Facility | None) -> dict:
    values: dict = {}
    creating = existing is None
    if creating or "name" in body:
        values["name"] = text(body.get("name"), "name", 2, 120, problems)
    for field, maximum in (("description", 4000), ("location", 160)):
        if field in body:
            values[field] = text(body.get(field), field, 0, maximum, problems)
    for field, low, high in (
        ("capacity", 1, 1000), ("open_minute", 0, 1439), ("close_minute", 1, 1440),
        ("slot_minutes", 15, 480), ("max_minutes_per_booking", 15, 1440), ("booking_window_days", 1, 180),
    ):
        if field in body or (creating and field in {"open_minute", "close_minute"}):
            values[field] = integer(body.get(field), field, low, high, problems)
    if "max_upcoming_per_resident" in body:
        cap = body.get("max_upcoming_per_resident")
        # null removes the cap.
        values["max_upcoming_per_resident"] = None if cap is None else integer(
            cap, "max_upcoming_per_resident", 1, 50, problems)
    for field in ("requires_approval", "is_active"):
        if field in body:
            if not isinstance(body.get(field), bool):
                problems[field] = "Must be true or false."
            else:
                values[field] = body[field]
    opening = values.get("open_minute", existing.open_minute if existing else None)
    closing = values.get("close_minute", existing.close_minute if existing else None)
    if opening is not None and closing is not None and closing <= opening:
        problems["close_minute"] = "Closing time must be after opening time."
    return values


@facilities_bp.get("/api/admin/facilities")
@manage_operations
def admin_list_facilities():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    rows = db.session.scalars(select(Facility).where(Facility.society_id == society.id).order_by(Facility.name)).all()
    return no_store({"facilities": [_facility_json(row) for row in rows]})


@facilities_bp.post("/api/admin/facilities")
@manage_operations
def admin_create_facility():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object(FACILITY_FIELDS)
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    problems: dict = {}
    values = _facility_fields(body, problems, None)
    if problems:
        return error("VALIDATION_ERROR", "Check the facility and try again.", 400, fields=problems)
    if db.session.scalar(select(Facility.id).where(Facility.society_id == society.id, Facility.name == values["name"])):
        return error("DUPLICATE_FACILITY", "A facility with that name exists.", 409, fields={"name": "Already used."})
    facility = Facility(society_id=society.id, **values)
    db.session.add(facility)
    db.session.flush()
    audit("FACILITY_CREATED", "FACILITY", facility.id, {"name": facility.name})
    db.session.commit()
    return no_store({"facility": _facility_json(facility)}, 201)


@facilities_bp.patch("/api/admin/facilities/<uuid:facility_id>")
@manage_operations
def admin_update_facility(facility_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object(FACILITY_FIELDS)
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    facility = _find_facility(facility_id, society.id, lock=True, active_only=False)
    if facility is None:
        return error("FACILITY_NOT_FOUND", "Facility not found.", 404)
    problems: dict = {}
    values = _facility_fields(body, problems, facility)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the facility and try again.", 400, fields=problems)
    for key, value in values.items():
        setattr(facility, key, value)
    audit("FACILITY_UPDATED", "FACILITY", facility.id, {"fields": sorted(values)})
    db.session.commit()
    return no_store({"facility": _facility_json(facility)})


@facilities_bp.post("/api/admin/facilities/<uuid:facility_id>/blackouts")
@manage_operations
def admin_add_blackout(facility_id):
    """Block a facility. Overlapping held bookings are cancelled with the reason."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"starts_at", "ends_at", "reason"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    problems: dict = {}
    starts_at = when(body.get("starts_at"), "starts_at", problems)
    ends_at = when(body.get("ends_at"), "ends_at", problems)
    reason = text(body.get("reason"), "reason", 3, 300, problems)
    if starts_at and ends_at and ends_at <= starts_at:
        problems["ends_at"] = "End time must be after start time."
    if problems:
        return error("VALIDATION_ERROR", "Check the blackout and try again.", 400, fields=problems)
    facility = _find_facility(facility_id, society.id, lock=True, active_only=False)
    if facility is None:
        return error("FACILITY_NOT_FOUND", "Facility not found.", 404)
    blackout = FacilityBlackout(
        facility_id=facility.id, starts_at=starts_at, ends_at=ends_at, reason=reason,
        created_by_user_id=current_user.id,
    )
    db.session.add(blackout)
    db.session.flush()
    affected = db.session.scalars(_overlap_query(facility.id, starts_at, ends_at).with_for_update()).all()
    now = utc_now()
    message = f"Facility unavailable: {reason}"
    for booking in affected:
        previous = booking.status
        booking.status = BookingStatus.CANCELLED
        booking.decision_reason = message[:300]
        booking.updated_at = now
        _record(booking, previous, BookingStatus.CANCELLED, booking.decision_reason)
    audit("FACILITY_BLACKOUT_ADDED", "FACILITY", facility.id, {
        "reason": reason, "cancelled_bookings": [str(item.id) for item in affected],
    })
    db.session.commit()
    return no_store({
        "blackout": {"id": str(blackout.id), "starts_at": iso(starts_at), "ends_at": iso(ends_at), "reason": reason},
        "cancelled_booking_ids": [str(item.id) for item in affected],
    }, 201)


@facilities_bp.get("/api/admin/bookings")
@manage_operations
def admin_list_bookings():
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
    query = select(Booking).join(Facility, Facility.id == Booking.facility_id).where(Facility.society_id == society.id)
    status = request.args.get("status")
    if status:
        try:
            query = query.where(Booking.status == BookingStatus(status))
        except ValueError:
            return error("VALIDATION_ERROR", "Unknown booking status.", 400, fields={"status": "Unknown status."})
    rows = db.session.scalars(
        query.order_by(Booking.starts_at.asc(), Booking.id.asc()).limit(limit).offset(offset)
    ).all()
    return no_store({"bookings": _bookings_payload(rows, admin=True), "pagination": {"limit": limit, "offset": offset}})


@facilities_bp.post("/api/bookings/<uuid:booking_id>/decision")
@manage_operations
def decide_booking(booking_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"decision", "reason"})
    if failure:
        return failure
    problems: dict = {}
    decision = body.get("decision")
    if decision not in ("APPROVE", "REJECT"):
        problems["decision"] = "Choose APPROVE or REJECT."
    reason = text(body.get("reason"), "reason", 1, 300, problems, required=decision != "APPROVE")
    if problems:
        return error("VALIDATION_ERROR", "Check the decision and try again.", 400, fields=problems)
    booking = db.session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
    if booking is None:
        return error("BOOKING_NOT_FOUND", "Booking not found.", 404)
    if booking.status != BookingStatus.PENDING:
        db.session.rollback()
        return error("INVALID_STATE", "Only pending bookings can be decided.", 409)
    target = BookingStatus.CONFIRMED if decision == "APPROVE" else BookingStatus.REJECTED
    booking.status = target
    booking.reviewer_user_id = current_user.id
    booking.decision_reason = reason
    booking.updated_at = utc_now()
    _record(booking, BookingStatus.PENDING, target, reason)
    audit("BOOKING_DECIDED", "BOOKING", booking.id, {"decision": decision})
    db.session.commit()
    return no_store({"booking": _bookings_payload([booking], admin=True)[0]})
