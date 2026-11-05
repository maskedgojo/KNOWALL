"""Resident operations summary: upcoming bookings, events, disruptions, projects."""
from flask import Blueprint
from flask_login import current_user
from sqlalchemy import select

from app.extensions import db
from app.modules.identity.models.user import utc_now

from .common import iso, no_store, resident_read, schema_missing, society_or_error
from .models import (
    Booking, BookingStatus, DevelopmentProject, EventStatus, Facility, MaintenanceItem, MaintenanceRequest,
    MaintenanceStatus, ProjectStatus, SocietyEvent, TicketStatus,
)

dashboard_bp = Blueprint("operations_dashboard", __name__)


@dashboard_bp.get("/api/operations/dashboard")
@resident_read
def operations_dashboard():
    missing = schema_missing()
    if missing:
        return missing
    society, failure = society_or_error()
    if failure:
        return failure
    now = utc_now()
    bookings = db.session.execute(
        select(Booking, Facility.name).join(Facility, Facility.id == Booking.facility_id).where(
            Booking.user_id == current_user.id, Booking.ends_at > now,
            Booking.status.in_((BookingStatus.PENDING, BookingStatus.CONFIRMED)),
        ).order_by(Booking.starts_at.asc()).limit(5)
    ).all()
    events = db.session.scalars(select(SocietyEvent).where(
        SocietyEvent.society_id == society.id, SocietyEvent.status == EventStatus.PUBLISHED, SocietyEvent.ends_at > now,
    ).order_by(SocietyEvent.starts_at.asc()).limit(5)).all()
    disruptions = db.session.scalars(select(MaintenanceItem).where(
        MaintenanceItem.society_id == society.id, MaintenanceItem.status != MaintenanceStatus.RESOLVED,
    ).order_by(MaintenanceItem.scheduled_start.asc()).limit(5)).all()
    projects = db.session.scalars(select(DevelopmentProject).where(
        DevelopmentProject.society_id == society.id, DevelopmentProject.status != ProjectStatus.COMPLETED,
    ).order_by(DevelopmentProject.updated_at.desc()).limit(5)).all()
    open_tickets = db.session.scalars(select(MaintenanceRequest).where(
        MaintenanceRequest.reporter_user_id == current_user.id, MaintenanceRequest.status != TicketStatus.CONFIRMED,
    ).order_by(MaintenanceRequest.updated_at.desc()).limit(5)).all()
    return no_store({
        "bookings": [{
            "id": str(row.id), "facility_name": name, "starts_at": iso(row.starts_at),
            "ends_at": iso(row.ends_at), "status": row.status.value,
        } for row, name in bookings],
        "events": [{"id": str(row.id), "title": row.title, "venue": row.venue, "starts_at": iso(row.starts_at)} for row in events],
        "disruptions": [{
            "id": str(row.id), "asset": row.asset, "title": row.title, "status": row.status.value,
            "scheduled_start": iso(row.scheduled_start), "scheduled_end": iso(row.scheduled_end),
        } for row in disruptions],
        "projects": [{"id": str(row.id), "title": row.title, "status": row.status.value} for row in projects],
        "my_open_requests": [{"id": str(row.id), "title": row.title, "status": row.status.value} for row in open_tickets],
    })
