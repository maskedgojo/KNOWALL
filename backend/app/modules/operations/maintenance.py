"""Planned maintenance notices and private resident maintenance tickets.

A ticket is visible only to its reporter and to a Society Admin. Anyone else
gets 404, as with private disputes. Public roads and streetlights belong to
Module 5, not here.
"""
from flask import Blueprint, request
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import Flat, Household, Tower
from app.modules.identity.models.user import utc_now

from .common import (
    audit, choice, current_membership, iso, manage_operations, names, no_store, pagination,
    report_maintenance, resident_read, schema_missing, society_or_error, text, when,
)
from .models import (
    MaintenanceItem, MaintenanceRequest, MaintenanceRequestUpdate, MaintenanceStatus, MaintenanceUpdate,
    PhotoSubject, TicketStatus, TicketType, TicketUpdateKind,
)
from .photos import photos_for

maintenance_bp = Blueprint("operations_maintenance", __name__)

# Admin-driven ticket transitions. Resident CONFIRM/REOPEN goes through feedback.
ADMIN_TRANSITIONS = {
    TicketStatus.REPORTED: {TicketStatus.ASSIGNED},
    TicketStatus.ASSIGNED: {TicketStatus.IN_PROGRESS},
    TicketStatus.IN_PROGRESS: {TicketStatus.COMPLETED},
    TicketStatus.REOPENED: {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS},
}
ITEM_TRANSITIONS = {
    MaintenanceStatus.PLANNED: {MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.RESOLVED},
    MaintenanceStatus.IN_PROGRESS: {MaintenanceStatus.RESOLVED},
}


# ---------------------------------------------------------------- schedules

def _item_updates(item_ids) -> dict:
    if not item_ids:
        return {}
    rows = db.session.scalars(
        select(MaintenanceUpdate).where(MaintenanceUpdate.item_id.in_(item_ids))
        .order_by(MaintenanceUpdate.created_at.asc(), MaintenanceUpdate.id.asc())
    ).all()
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.item_id, []).append({
            "message": row.message, "status": row.status, "created_at": iso(row.created_at),
        })
    return grouped


def _item_json(row: MaintenanceItem, updates: dict) -> dict:
    return {
        "id": str(row.id),
        "asset": row.asset,
        "title": row.title,
        "description": row.description,
        "scheduled_start": iso(row.scheduled_start),
        "scheduled_end": iso(row.scheduled_end),
        "status": row.status.value,
        "created_at": iso(row.created_at),
        "updates": updates.get(row.id, []),
    }


@maintenance_bp.get("/api/maintenance")
@resident_read
def list_maintenance():
    return _list_items()


@maintenance_bp.get("/api/admin/maintenance")
@manage_operations
def admin_list_maintenance():
    return _list_items()


def _list_items():
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
        select(MaintenanceItem).where(MaintenanceItem.society_id == society.id)
        .order_by(MaintenanceItem.scheduled_start.desc(), MaintenanceItem.id.desc()).limit(limit).offset(offset)
    ).all()
    updates = _item_updates([row.id for row in rows])
    return no_store({"items": [_item_json(row, updates) for row in rows], "pagination": {"limit": limit, "offset": offset}})


@maintenance_bp.post("/api/maintenance")
@manage_operations
def create_maintenance():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"asset", "title", "description", "scheduled_start", "scheduled_end"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    problems: dict = {}
    asset = text(body.get("asset"), "asset", 2, 120, problems)
    title = text(body.get("title"), "title", 3, 160, problems)
    description = text(body.get("description"), "description", 1, 8000, problems)
    start = when(body.get("scheduled_start"), "scheduled_start", problems)
    end = when(body.get("scheduled_end"), "scheduled_end", problems)
    if start and end and end <= start:
        problems["scheduled_end"] = "End must be after start."
    if problems:
        return error("VALIDATION_ERROR", "Check the maintenance notice and try again.", 400, fields=problems)
    now = utc_now()
    item = MaintenanceItem(
        society_id=society.id, asset=asset, title=title, description=description, scheduled_start=start,
        scheduled_end=end, status=MaintenanceStatus.PLANNED, created_by_user_id=current_user.id,
        created_at=now, updated_at=now,
    )
    db.session.add(item)
    db.session.flush()
    audit("MAINTENANCE_SCHEDULED", "MAINTENANCE_ITEM", item.id, {"asset": asset, "title": title})
    db.session.commit()
    return no_store({"item": _item_json(item, {})}, 201)


@maintenance_bp.post("/api/maintenance/<uuid:item_id>/updates")
@manage_operations
def update_maintenance(item_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"message", "status"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    item = db.session.scalar(
        select(MaintenanceItem).where(MaintenanceItem.id == item_id, MaintenanceItem.society_id == society.id)
        .with_for_update()
    )
    if item is None:
        return error("MAINTENANCE_NOT_FOUND", "Maintenance notice not found.", 404)
    problems: dict = {}
    message = text(body.get("message"), "message", 1, 4000, problems)
    status = item.status
    if "status" in body:
        status = choice(body.get("status"), "status", MaintenanceStatus, problems)
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the update and try again.", 400, fields=problems)
    if status != item.status and status not in ITEM_TRANSITIONS.get(item.status, set()):
        db.session.rollback()
        return error("INVALID_TRANSITION", f"Cannot move from {item.status.value} to {status.value}.", 409)
    now = utc_now()
    item.status = status
    item.updated_at = now
    db.session.add(MaintenanceUpdate(
        item_id=item.id, actor_user_id=current_user.id, message=message, status=status.value, created_at=now,
    ))
    audit("MAINTENANCE_UPDATED", "MAINTENANCE_ITEM", item.id, {"status": status.value})
    db.session.commit()
    return no_store({"item": _item_json(item, _item_updates([item.id]))})


# ---------------------------------------------------------------- tickets

def _flat_labels(flat_ids) -> dict:
    if not flat_ids:
        return {}
    rows = db.session.execute(
        select(Flat.id, Tower.name, Flat.flat_number).join(Tower, Tower.id == Flat.tower_id).where(Flat.id.in_(flat_ids))
    ).all()
    return {row[0]: f"{row[1]}-{row[2]}" for row in rows}


def _timeline(request_ids) -> dict:
    if not request_ids:
        return {}
    rows = db.session.scalars(
        select(MaintenanceRequestUpdate).where(MaintenanceRequestUpdate.request_id.in_(request_ids))
        .order_by(MaintenanceRequestUpdate.created_at.asc(), MaintenanceRequestUpdate.id.asc())
    ).all()
    people = names(row.actor_user_id for row in rows)
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row.request_id, []).append({
            "kind": row.kind.value, "message": row.message, "from_status": row.from_status,
            "to_status": row.to_status, "actor_display_name": people.get(row.actor_user_id, ""),
            "created_at": iso(row.created_at),
        })
    return grouped


def _tickets_payload(rows, *, admin=False) -> list[dict]:
    flats = _flat_labels({row.flat_id for row in rows})
    timeline = _timeline([row.id for row in rows])
    photos = photos_for(PhotoSubject.MAINTENANCE_REQUEST, [row.id for row in rows])
    people = names(row.reporter_user_id for row in rows) if admin else {}
    payload = []
    for row in rows:
        body = {
            "id": str(row.id),
            "flat": flats.get(row.flat_id, ""),
            "issue_type": row.issue_type.value,
            "title": row.title,
            "description": row.description,
            "location_note": row.location_note,
            "status": row.status.value,
            "assignee_label": row.assignee_label,
            "created_at": iso(row.created_at),
            "updated_at": iso(row.updated_at),
            "timeline": timeline.get(row.id, []),
            "photos": photos.get(row.id, []),
        }
        if admin:
            body["reporter_display_name"] = people.get(row.reporter_user_id, "")
        payload.append(body)
    return payload


def _add_update(ticket, kind, message, from_status=None, to_status=None):
    db.session.add(MaintenanceRequestUpdate(
        request_id=ticket.id, actor_user_id=current_user.id, kind=kind, message=message or "",
        from_status=from_status.value if from_status else None, to_status=to_status.value if to_status else None,
    ))


@maintenance_bp.post("/api/maintenance/requests")
@report_maintenance
def create_ticket():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"issue_type", "title", "description", "location_note"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    membership = current_membership()
    if membership is None:
        return error("FORBIDDEN", "An active society membership is required.", 403)
    problems: dict = {}
    issue_type = choice(body.get("issue_type"), "issue_type", TicketType, problems)
    title = text(body.get("title"), "title", 3, 160, problems)
    description = text(body.get("description"), "description", 1, 4000, problems)
    location_note = text(body.get("location_note"), "location_note", 0, 160, problems, required=False) or ""
    if problems:
        return error("VALIDATION_ERROR", "Check the request and try again.", 400, fields=problems)
    household = db.session.get(Household, membership.household_id)
    now = utc_now()
    ticket = MaintenanceRequest(
        society_id=society.id, flat_id=household.flat_id, membership_id=membership.id,
        reporter_user_id=current_user.id, issue_type=issue_type, title=title, description=description,
        location_note=location_note, status=TicketStatus.REPORTED, created_at=now, updated_at=now,
    )
    db.session.add(ticket)
    db.session.flush()
    _add_update(ticket, TicketUpdateKind.STATUS, "Request reported.", None, TicketStatus.REPORTED)
    audit("MAINTENANCE_REQUEST_REPORTED", "MAINTENANCE_REQUEST", ticket.id, {"issue_type": issue_type.value})
    db.session.commit()
    return no_store({"request": _tickets_payload([ticket])[0]}, 201)


@maintenance_bp.get("/api/maintenance/requests/me")
@report_maintenance
def my_tickets():
    missing = schema_missing()
    if missing:
        return missing
    page = pagination()
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    rows = db.session.scalars(
        select(MaintenanceRequest).where(MaintenanceRequest.reporter_user_id == current_user.id)
        .order_by(MaintenanceRequest.created_at.desc(), MaintenanceRequest.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"requests": _tickets_payload(rows), "pagination": {"limit": limit, "offset": offset}})


@maintenance_bp.get("/api/maintenance/requests/<uuid:request_id>")
@report_maintenance
def my_ticket(request_id):
    missing = schema_missing()
    if missing:
        return missing
    ticket = db.session.scalar(select(MaintenanceRequest).where(
        MaintenanceRequest.id == request_id, MaintenanceRequest.reporter_user_id == current_user.id,
    ))
    if ticket is None:
        return error("REQUEST_NOT_FOUND", "Maintenance request not found.", 404)
    return no_store({"request": _tickets_payload([ticket])[0]})


@maintenance_bp.post("/api/maintenance/requests/<uuid:request_id>/feedback")
@report_maintenance
def ticket_feedback(request_id):
    """Reporter adds a clarification, or confirms/reopens completed work."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"action", "message"})
    if failure:
        return failure
    problems: dict = {}
    action = body.get("action")
    if action not in ("CLARIFY", "CONFIRM", "REOPEN"):
        problems["action"] = "Choose CLARIFY, CONFIRM or REOPEN."
    message = text(body.get("message"), "message", 1, 2000, problems, required=action != "CONFIRM")
    if problems:
        return error("VALIDATION_ERROR", "Check the feedback and try again.", 400, fields=problems)
    ticket = db.session.scalar(select(MaintenanceRequest).where(
        MaintenanceRequest.id == request_id, MaintenanceRequest.reporter_user_id == current_user.id,
    ).with_for_update())
    if ticket is None:
        return error("REQUEST_NOT_FOUND", "Maintenance request not found.", 404)
    previous = ticket.status
    if action == "CLARIFY":
        if previous == TicketStatus.CONFIRMED:
            db.session.rollback()
            return error("INVALID_STATE", "This request is closed.", 409)
        _add_update(ticket, TicketUpdateKind.CLARIFICATION, message)
    else:
        if previous != TicketStatus.COMPLETED:
            db.session.rollback()
            return error("INVALID_STATE", "Only completed work can be confirmed or reopened.", 409)
        ticket.status = TicketStatus.CONFIRMED if action == "CONFIRM" else TicketStatus.REOPENED
        _add_update(ticket, TicketUpdateKind.FEEDBACK, message or "Resident confirmed the fix.", previous, ticket.status)
    ticket.updated_at = utc_now()
    audit("MAINTENANCE_REQUEST_FEEDBACK", "MAINTENANCE_REQUEST", ticket.id, {"action": action})
    db.session.commit()
    return no_store({"request": _tickets_payload([ticket])[0]})


@maintenance_bp.get("/api/admin/maintenance/requests")
@manage_operations
def admin_tickets():
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
    query = select(MaintenanceRequest).where(MaintenanceRequest.society_id == society.id)
    status = request.args.get("status")
    if status:
        try:
            query = query.where(MaintenanceRequest.status == TicketStatus(status))
        except ValueError:
            return error("VALIDATION_ERROR", "Unknown status.", 400, fields={"status": "Unknown status."})
    rows = db.session.scalars(
        query.order_by(MaintenanceRequest.created_at.desc(), MaintenanceRequest.id.desc()).limit(limit).offset(offset)
    ).all()
    return no_store({"requests": _tickets_payload(rows, admin=True), "pagination": {"limit": limit, "offset": offset}})


@maintenance_bp.patch("/api/maintenance/requests/<uuid:request_id>/status")
@manage_operations
def admin_ticket_status(request_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_object({"status", "message", "assignee_label"})
    if failure:
        return failure
    society, failure = society_or_error()
    if failure:
        return failure
    ticket = db.session.scalar(select(MaintenanceRequest).where(
        MaintenanceRequest.id == request_id, MaintenanceRequest.society_id == society.id,
    ).with_for_update())
    if ticket is None:
        return error("REQUEST_NOT_FOUND", "Maintenance request not found.", 404)
    problems: dict = {}
    target = choice(body.get("status"), "status", TicketStatus, problems)
    message = text(body.get("message"), "message", 1, 2000, problems)
    assignee = text(body.get("assignee_label"), "assignee_label", 2, 120, problems, required=False)
    if target == TicketStatus.ASSIGNED and not assignee and not ticket.assignee_label:
        problems["assignee_label"] = "Name who is assigned."
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check the update and try again.", 400, fields=problems)
    previous = ticket.status
    if target not in ADMIN_TRANSITIONS.get(previous, set()):
        db.session.rollback()
        return error("INVALID_TRANSITION", f"Cannot move from {previous.value} to {target.value}.", 409)
    ticket.status = target
    if assignee:
        ticket.assignee_label = assignee
    ticket.updated_at = utc_now()
    _add_update(ticket, TicketUpdateKind.STATUS, message, previous, target)
    audit("MAINTENANCE_REQUEST_STATUS", "MAINTENANCE_REQUEST", ticket.id, {"from": previous.value, "to": target.value})
    db.session.commit()
    return no_store({"request": _tickets_payload([ticket], admin=True)[0]})
