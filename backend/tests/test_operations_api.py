"""Module 3 operations API tests. In-memory schema only; does not migrate the project database."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)
from app.modules.operations.common import SOCIETY_TZ

PASSWORD = "OperationsStrongPass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "operations-test-secret-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
        "MAIL_DELIVERY_MODE": "memory",
    })
    with instance.app_context():
        db.create_all()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def send(client, method, url, body=None):
    return client.open(url, method=method, json=body if body is not None else {}, headers={"X-CSRF-Token": csrf(client)})


def post(client, url, body=None):
    return send(client, "POST", url, body)


def login(client, email):
    result = post(client, "/api/auth/login", {"email": email, "password": PASSWORD})
    assert result.status_code == 200, result.json


def logout(client):
    assert post(client, "/api/auth/logout", {}).status_code == 200


@pytest.fixture()
def people(app):
    with app.app_context():
        db.session.add(SocietyProfile(
            id=1, name="Green Valley Residency", address="1 Main Road",
            locality="Green Valley", city="Bhubaneswar",
        ))
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        home = Household(flat=flat, label="Owner household")
        db.session.add(home)
        db.session.flush()
        for name, role, member in (
            ("admin", PermissionRole.SOCIETY_ADMIN, False),
            ("rahul", PermissionRole.RESIDENT, True),
            ("priya", PermissionRole.RESIDENT, True),
            ("applicant", PermissionRole.APPLICANT, False),
        ):
            user = User(
                email=f"{name}@example.test", display_name=name.title(),
                password_hash=generate_password_hash(PASSWORD),
                account_status=AccountStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user=user, role=role))
            if member:
                db.session.add(Membership(
                    user=user, household=home, category=ResidentCategory.OWNER,
                    status=MembershipStatus.ACTIVE,
                    valid_from=datetime.now(timezone.utc).date() - timedelta(days=2),
                ))
        db.session.commit()


def slot(hour, days=1, minutes=60):
    """Tomorrow at `hour` IST, as ISO strings."""
    local = datetime.now(SOCIETY_TZ).date() + timedelta(days=days)
    start = datetime(local.year, local.month, local.day, hour, tzinfo=SOCIETY_TZ)
    return start.isoformat(), (start + timedelta(minutes=minutes)).isoformat()


def make_facility(client, **overrides):
    body = {"name": "Clubhouse", "open_minute": 6 * 60, "close_minute": 22 * 60, "slot_minutes": 60,
            "max_minutes_per_booking": 180, "requires_approval": True}
    body.update(overrides)
    created = post(client, "/api/admin/facilities", body)
    assert created.status_code == 201, created.json
    return created.json["facility"]["id"]


def book(client, facility_id, hour, **overrides):
    starts_at, ends_at = slot(hour)
    body = {"facility_id": facility_id, "starts_at": starts_at, "ends_at": ends_at, "purpose": "Birthday party"}
    body.update(overrides)
    return post(client, "/api/bookings", body)


# ---------------------------------------------------------------- access

def test_access_requires_membership_and_admin_grant(client, people):
    assert client.get("/api/facilities").status_code == 401
    login(client, "applicant@example.test")
    assert client.get("/api/facilities").status_code == 403
    assert post(client, "/api/maintenance/requests", {}).status_code == 403
    logout(client)
    login(client, "rahul@example.test")
    assert client.get("/api/facilities").status_code == 200
    assert post(client, "/api/admin/facilities", {"name": "Gym"}).status_code == 403
    assert client.get("/api/admin/maintenance/requests").status_code == 403
    access = client.get("/api/me/access").json
    assert "society.operations.manage" not in str(access)
    logout(client)
    login(client, "admin@example.test")
    assert "society.operations.manage" in str(client.get("/api/me/access").json)


# ---------------------------------------------------------------- bookings

def test_booking_approval_overlap_cancel_and_history(client, app, people):
    login(client, "admin@example.test")
    clubhouse = make_facility(client)
    logout(client)

    login(client, "rahul@example.test")
    created = book(client, clubhouse, 10)
    assert created.status_code == 201, created.json
    booking = created.json["booking"]
    assert booking["status"] == "PENDING"
    # Pending requests hold the slot, including partial overlap.
    starts_at, _ = slot(10)
    _, ends_at = slot(11)
    assert book(client, clubhouse, 10).json["error"]["code"] == "SLOT_UNAVAILABLE"
    overlap = post(client, "/api/bookings", {
        "facility_id": clubhouse, "starts_at": starts_at, "ends_at": ends_at, "purpose": "Overlap",
    })
    assert overlap.status_code == 409
    availability = client.get(f"/api/facilities/{clubhouse}/availability?date={starts_at[:10]}").json
    by_start = {datetime.fromisoformat(item["starts_at"]): item for item in availability["slots"]}
    assert len(by_start) == 16  # 06:00–22:00 in one-hour slots
    ten = by_start[datetime.fromisoformat(starts_at)]
    assert ten["available"] is False and ten["reason"] == "BOOKED"
    assert by_start[datetime.fromisoformat(slot(12)[0])]["available"] is True
    logout(client)

    login(client, "admin@example.test")
    pending = client.get("/api/admin/bookings?status=PENDING").json["bookings"]
    assert [row["id"] for row in pending] == [booking["id"]]
    assert pending[0]["resident_display_name"] == "Rahul"
    assert post(client, f"/api/bookings/{booking['id']}/decision", {"decision": "REJECT"}).status_code == 400
    approved = post(client, f"/api/bookings/{booking['id']}/decision", {"decision": "APPROVE"})
    assert approved.status_code == 200 and approved.json["booking"]["status"] == "CONFIRMED"
    assert post(client, f"/api/bookings/{booking['id']}/decision", {"decision": "APPROVE"}).status_code == 409
    logout(client)

    login(client, "priya@example.test")
    assert post(client, f"/api/bookings/{booking['id']}/cancel", {}).status_code == 404
    logout(client)

    login(client, "rahul@example.test")
    cancelled = post(client, f"/api/bookings/{booking['id']}/cancel", {"reason": "Plans changed"})
    assert cancelled.status_code == 200
    history = cancelled.json["booking"]["history"]
    assert [item["to_status"] for item in history] == ["PENDING", "CONFIRMED", "CANCELLED"]
    # Once cancelled, the slot is free again.
    assert book(client, clubhouse, 10).status_code == 201
    mine = client.get("/api/bookings/me").json["bookings"]
    assert len(mine) == 2
    with app.app_context():
        actions = set(db.session.scalars(select(AuditLog.action)).all())
        assert {"BOOKING_REQUESTED", "BOOKING_DECIDED", "BOOKING_CANCELLED"} <= actions


def test_booking_rules_reject_bad_times(client, people):
    login(client, "admin@example.test")
    court = make_facility(client, name="Badminton Court", requires_approval=False, booking_window_days=3,
                          max_minutes_per_booking=60)
    logout(client)
    login(client, "rahul@example.test")
    auto = book(client, court, 7)
    assert auto.status_code == 201 and auto.json["booking"]["status"] == "CONFIRMED"
    assert book(client, court, 23).status_code == 400  # after closing
    assert book(client, court, 5).status_code == 400  # before opening
    starts_at, ends_at = slot(9, minutes=120)
    too_long = post(client, "/api/bookings", {"facility_id": court, "starts_at": starts_at, "ends_at": ends_at, "purpose": "Long"})
    assert too_long.status_code == 400 and "ends_at" in too_long.json["error"]["fields"]
    starts_at, ends_at = slot(9, days=10)
    far = post(client, "/api/bookings", {"facility_id": court, "starts_at": starts_at, "ends_at": ends_at, "purpose": "Far"})
    assert far.status_code == 400
    starts_at, ends_at = slot(9, days=-1)
    past = post(client, "/api/bookings", {"facility_id": court, "starts_at": starts_at, "ends_at": ends_at, "purpose": "Past"})
    assert past.status_code == 400
    misaligned = post(client, "/api/bookings", {
        "facility_id": court, "starts_at": slot(9)[0].replace(":00:00", ":30:00"),
        "ends_at": slot(10)[0].replace(":00:00", ":30:00"), "purpose": "Odd",
    })
    assert misaligned.status_code == 400
    assert book(client, court, 9, status="CONFIRMED").status_code == 400  # unknown field


def test_blackout_cancels_overlapping_bookings(client, people):
    login(client, "admin@example.test")
    court = make_facility(client, name="Court", requires_approval=False)
    logout(client)
    login(client, "rahul@example.test")
    booking = book(client, court, 10).json["booking"]
    logout(client)
    login(client, "admin@example.test")
    starts_at, _ = slot(8)
    _, ends_at = slot(12)
    blackout = post(client, f"/api/admin/facilities/{court}/blackouts", {
        "starts_at": starts_at, "ends_at": ends_at, "reason": "Floor repair",
    })
    assert blackout.status_code == 201
    assert blackout.json["cancelled_booking_ids"] == [booking["id"]]
    logout(client)
    login(client, "rahul@example.test")
    mine = client.get("/api/bookings/me").json["bookings"][0]
    assert mine["status"] == "CANCELLED" and "Floor repair" in mine["decision_reason"]
    assert book(client, court, 11).json["error"]["code"] == "FACILITY_UNAVAILABLE"


# ---------------------------------------------------------------- maintenance tickets

def test_ticket_lifecycle_privacy_and_reopen(client, people):
    login(client, "priya@example.test")
    created = post(client, "/api/maintenance/requests", {
        "issue_type": "PLUMBING", "title": "Leaking shared pipe", "description": "Water on the 4th floor landing.",
        "location_note": "Tower B, floor 4",
    })
    assert created.status_code == 201, created.json
    ticket = created.json["request"]
    assert ticket["status"] == "REPORTED" and ticket["flat"] == "B-402"
    assert post(client, f"/api/maintenance/requests/{ticket['id']}/feedback", {"action": "CONFIRM"}).status_code == 409
    logout(client)

    login(client, "rahul@example.test")
    assert client.get(f"/api/maintenance/requests/{ticket['id']}").status_code == 404
    assert client.get("/api/maintenance/requests/me").json["requests"] == []
    logout(client)

    login(client, "admin@example.test")
    url = f"/api/maintenance/requests/{ticket['id']}/status"
    assert send(client, "PATCH", url, {"status": "ASSIGNED", "message": "Assigning"}).status_code == 400
    assert send(client, "PATCH", url, {"status": "COMPLETED", "message": "Skip"}).status_code == 409
    for status, extra in (("ASSIGNED", {"assignee_label": "Plumber Ravi"}), ("IN_PROGRESS", {}), ("COMPLETED", {})):
        moved = send(client, "PATCH", url, {"status": status, "message": f"Now {status}", **extra})
        assert moved.status_code == 200, moved.json
    assert moved.json["request"]["reporter_display_name"] == "Priya"
    logout(client)

    login(client, "priya@example.test")
    feedback = f"/api/maintenance/requests/{ticket['id']}/feedback"
    assert post(client, feedback, {"action": "REOPEN"}).status_code == 400  # reason needed
    reopened = post(client, feedback, {"action": "REOPEN", "message": "Still dripping"})
    assert reopened.json["request"]["status"] == "REOPENED"
    logout(client)

    login(client, "admin@example.test")
    send(client, "PATCH", url, {"status": "IN_PROGRESS", "message": "Back on it"})
    send(client, "PATCH", url, {"status": "COMPLETED", "message": "Joint replaced"})
    logout(client)

    login(client, "priya@example.test")
    confirmed = post(client, feedback, {"action": "CONFIRM"})
    assert confirmed.json["request"]["status"] == "CONFIRMED"
    timeline = [item["to_status"] for item in confirmed.json["request"]["timeline"] if item["to_status"]]
    assert timeline == ["REPORTED", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "REOPENED", "IN_PROGRESS",
                        "COMPLETED", "CONFIRMED"]
    assert post(client, feedback, {"action": "CLARIFY", "message": "Thanks"}).status_code == 409


def test_maintenance_schedule_visible_to_residents(client, people):
    login(client, "admin@example.test")
    start, end = slot(9, minutes=240)
    created = post(client, "/api/maintenance", {
        "asset": "Lift B1", "title": "Lift servicing", "description": "Annual servicing.",
        "scheduled_start": start, "scheduled_end": end,
    })
    assert created.status_code == 201
    item = created.json["item"]["id"]
    assert post(client, f"/api/maintenance/{item}/updates", {"message": "Started", "status": "IN_PROGRESS"}).status_code == 200
    assert post(client, f"/api/maintenance/{item}/updates", {"message": "Done", "status": "RESOLVED"}).status_code == 200
    assert post(client, f"/api/maintenance/{item}/updates", {"message": "Again", "status": "PLANNED"}).status_code == 409
    logout(client)
    login(client, "rahul@example.test")
    items = client.get("/api/maintenance").json["items"]
    assert items[0]["status"] == "RESOLVED" and len(items[0]["updates"]) == 2
    assert post(client, "/api/maintenance", {"asset": "x"}).status_code == 403


# ---------------------------------------------------------------- events

def test_event_capacity_waitlist_and_promotion(client, people):
    login(client, "admin@example.test")
    start, end = slot(18, minutes=180)
    event = post(client, "/api/events", {
        "title": "Diwali evening", "description": "Lights and sweets.", "venue": "Central lawn",
        "starts_at": start, "ends_at": end, "capacity": 1,
    }).json["event"]
    assert event["status"] == "DRAFT"
    logout(client)
    login(client, "rahul@example.test")
    assert client.get(f"/api/events/{event['id']}").status_code == 404  # drafts hidden
    logout(client)
    login(client, "admin@example.test")
    assert post(client, f"/api/events/{event['id']}/publish").status_code == 200
    assert post(client, f"/api/events/{event['id']}/publish").status_code == 409
    logout(client)

    login(client, "rahul@example.test")
    going = post(client, f"/api/events/{event['id']}/rsvp")
    assert going.status_code == 201 and going.json["event"]["my_rsvp"] == "GOING"
    assert post(client, f"/api/events/{event['id']}/rsvp").status_code == 409
    logout(client)
    login(client, "priya@example.test")
    waiting = post(client, f"/api/events/{event['id']}/rsvp").json["event"]
    assert waiting["my_rsvp"] == "WAITLISTED" and waiting["going_count"] == 1
    logout(client)
    login(client, "rahul@example.test")
    after = send(client, "DELETE", f"/api/events/{event['id']}/rsvp").json["event"]
    assert after["my_rsvp"] == "CANCELLED" and after["going_count"] == 1 and after["waitlist_count"] == 0
    logout(client)
    login(client, "priya@example.test")
    assert client.get(f"/api/events/{event['id']}").json["event"]["my_rsvp"] == "GOING"
    logout(client)
    login(client, "admin@example.test")
    attendees = client.get(f"/api/admin/events/{event['id']}/attendees").json["attendees"]
    assert [row["display_name"] for row in attendees] == ["Priya"]
    marked = post(client, f"/api/events/{event['id']}/attendance", {"user_id": attendees[0]["user_id"], "attended": True})
    assert marked.status_code == 200
    assert post(client, f"/api/events/{event['id']}/close").status_code == 200


# ---------------------------------------------------------------- development + dashboard

def test_development_project_milestones_and_dashboard(client, people):
    login(client, "admin@example.test")
    project = post(client, "/api/development", {
        "title": "Lobby renovation", "description": "New flooring and lighting.", "expected_completion": "2027-01-31",
    }).json["project"]
    url = f"/api/development/{project['id']}"
    post(client, f"{url}/milestones", {"title": "Flooring", "due_date": "2026-12-15"})
    added = post(client, f"{url}/milestones", {"title": "Lighting", "due_date": "2027-01-15"}).json["project"]
    first, second = added["milestones"]
    assert send(client, "PATCH", url, {"status": "COMPLETED"}).status_code == 400
    halfway = send(client, "PATCH", f"{url}/milestones/{first['id']}", {"percent": 50, "status": "IN_PROGRESS"})
    assert halfway.json["project"]["status"] == "IN_PROGRESS" and halfway.json["project"]["progress_percent"] == 25
    for milestone in (first, second):
        send(client, "PATCH", f"{url}/milestones/{milestone['id']}", {"status": "COMPLETED"})
    done = send(client, "PATCH", url, {"status": "COMPLETED"})
    assert done.status_code == 200 and done.json["project"]["progress_percent"] == 100
    court = make_facility(client, name="Court", requires_approval=False)
    logout(client)

    login(client, "rahul@example.test")
    assert client.get(url).json["project"]["status"] == "COMPLETED"
    assert send(client, "PATCH", url, {"status": "PLANNED"}).status_code == 403
    book(client, court, 10)
    dashboard = client.get("/api/operations/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json["bookings"][0]["facility_name"] == "Court"
    assert dashboard.json["projects"] == []


# ---------------------------------------------------------------- booking caps, volunteers, photos

def test_booking_cap_per_resident(client, people):
    login(client, "admin@example.test")
    court = make_facility(client, name="Court", requires_approval=False, max_upcoming_per_resident=1)
    assert send(client, "PATCH", f"/api/admin/facilities/{court}", {"max_upcoming_per_resident": 0}).status_code == 400
    logout(client)
    login(client, "rahul@example.test")
    first = book(client, court, 9)
    assert first.status_code == 201
    capped = book(client, court, 11)
    assert capped.status_code == 409 and capped.json["error"]["code"] == "BOOKING_LIMIT_REACHED"
    post(client, f"/api/bookings/{first.json['booking']['id']}/cancel")
    assert book(client, court, 11).status_code == 201  # cancelled bookings free the cap
    logout(client)
    login(client, "priya@example.test")
    assert book(client, court, 13).status_code == 201  # cap is per resident
    logout(client)
    login(client, "admin@example.test")
    lifted = send(client, "PATCH", f"/api/admin/facilities/{court}", {"max_upcoming_per_resident": None})
    assert lifted.json["facility"]["max_upcoming_per_resident"] is None


def test_event_volunteers_and_updates(client, people):
    login(client, "admin@example.test")
    start, end = slot(18, minutes=120)
    event = post(client, "/api/events", {
        "title": "Clean-up drive", "description": "Park clean-up.", "venue": "Park",
        "starts_at": start, "ends_at": end, "capacity": 20, "volunteer_slots": 1,
    }).json["event"]
    assert event["volunteer_slots"] == 1
    post(client, f"/api/events/{event['id']}/publish")
    assert post(client, f"/api/events/{event['id']}/updates", {"message": "Bring gloves."}).status_code == 201
    logout(client)
    login(client, "rahul@example.test")
    assert post(client, f"/api/events/{event['id']}/updates", {"message": "x"}).status_code == 403
    joined = post(client, f"/api/events/{event['id']}/volunteer", {"note": "Can bring bags"})
    assert joined.status_code == 201
    body = joined.json["event"]
    assert body["i_volunteered"] is True and body["volunteer_count"] == 1
    assert [item["message"] for item in body["updates"]] == ["Bring gloves."]
    assert post(client, f"/api/events/{event['id']}/volunteer", {}).json["error"]["code"] == "ALREADY_VOLUNTEERED"
    logout(client)
    login(client, "priya@example.test")
    assert post(client, f"/api/events/{event['id']}/volunteer", {}).json["error"]["code"] == "VOLUNTEER_SLOTS_FULL"
    logout(client)
    login(client, "admin@example.test")
    roster = client.get(f"/api/admin/events/{event['id']}/attendees").json
    assert [(v["display_name"], v["note"]) for v in roster["volunteers"]] == [("Rahul", "Can bring bags")]
    logout(client)
    login(client, "rahul@example.test")
    left = send(client, "DELETE", f"/api/events/{event['id']}/volunteer")
    assert left.json["event"]["volunteer_count"] == 0
    logout(client)
    login(client, "priya@example.test")
    assert post(client, f"/api/events/{event['id']}/volunteer", {}).status_code == 201


def png_bytes():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload(client, url, data, name="leak.png", caption="Pipe joint"):
    import io
    return client.post(url, data={"file": (io.BytesIO(data), name), "caption": caption},
                       content_type="multipart/form-data", headers={"X-CSRF-Token": csrf(client)})


def test_ticket_and_milestone_photos_are_private(client, app, people, tmp_path):
    app.config["OCR_PRIVATE_DIR"] = str(tmp_path)
    login(client, "priya@example.test")
    ticket = post(client, "/api/maintenance/requests", {
        "issue_type": "PLUMBING", "title": "Leaking pipe", "description": "Dripping.",
    }).json["request"]
    url = f"/api/maintenance/requests/{ticket['id']}/photos"
    assert upload(client, url, b"%PDF-1.4 not an image", name="doc.pdf").status_code == 400
    assert upload(client, url, b"not really a png").status_code == 400
    added = upload(client, url, png_bytes())
    assert added.status_code == 201, added.json
    photo = added.json["photos"][0]
    assert photo["caption"] == "Pipe joint" and photo["uploaded_by_staff"] is False
    detail = client.get(f"/api/maintenance/requests/{ticket['id']}").json["request"]
    assert [p["id"] for p in detail["photos"]] == [photo["id"]]
    download = client.get(f"/api/operations/photos/{photo['id']}/file")
    assert download.status_code == 200 and download.data == png_bytes()
    assert download.headers["Content-Type"] == "application/octet-stream"
    logout(client)

    login(client, "rahul@example.test")  # another resident
    assert client.get(f"/api/operations/photos/{photo['id']}/file").status_code == 404
    assert upload(client, url, png_bytes()).status_code == 404
    logout(client)

    login(client, "admin@example.test")
    fix = upload(client, url, png_bytes(), name="fixed.jpg.png", caption="After repair")
    assert fix.status_code == 201 and fix.json["photos"][1]["uploaded_by_staff"] is True
    assert client.get(f"/api/operations/photos/{photo['id']}/file").status_code == 200
    project = post(client, "/api/development", {"title": "Lobby", "description": "Tiles."}).json["project"]
    project = post(client, f"/api/development/{project['id']}/milestones", {"title": "Flooring"}).json["project"]
    milestone = project["milestones"][0]
    shot = upload(client, f"/api/development/{project['id']}/milestones/{milestone['id']}/photos", png_bytes(),
                  caption="Half done")
    assert shot.status_code == 201
    milestone_photo = shot.json["photos"][0]["id"]
    logout(client)

    login(client, "rahul@example.test")
    seen = client.get(f"/api/development/{project['id']}").json["project"]["milestones"][0]["photos"]
    assert [p["caption"] for p in seen] == ["Half done"]
    assert client.get(f"/api/operations/photos/{milestone_photo}/file").status_code == 200
    assert upload(client, f"/api/development/{project['id']}/milestones/{milestone['id']}/photos",
                  png_bytes()).status_code == 403
    with app.app_context():
        assert db.session.scalar(select(AuditLog).where(AuditLog.action == "OPERATION_PHOTO_ADDED")) is not None
