"""Module 4: locality directory, corrections, local events, alerts, reports and access control."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Flat, Household, Membership, MembershipStatus, PermissionRole, ResidentCategory,
    RoleAssignment, SocietyProfile, Tower, User,
)
from app.modules.locality.models import (
    DataOrigin, LocalityProfile, Place, PlaceCategory, PlaceVerification, PublicationStatus, VerificationMethod,
    VerificationStatus,
)
from app.modules.operations.models import EventRsvp, EventStatus, RsvpStatus, SocietyEvent

PASSWORD = "LocalityTestPass!123"
CENTER = (20.3, 85.82)
REVIEWER_KEYS = {"reviewer_user_id", "reviewer_display_name", "reporter_user_id", "actor_display_name",
                 "actor_user_id"}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "locality-test-secret",
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


def post(client, url, body):
    return client.post(url, json=body, headers={"X-CSRF-Token": csrf(client)})


def patch(client, url, body):
    return client.patch(url, json=body, headers={"X-CSRF-Token": csrf(client)})


def login(client, name):
    assert post(client, "/api/auth/login", {"email": f"{name}@example.test", "password": PASSWORD}).status_code == 200


def logout(client):
    assert post(client, "/api/auth/logout", {}).status_code == 200


def walk_keys(value, found: set):
    if isinstance(value, dict):
        found.update(value)
        for item in value.values():
            walk_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            walk_keys(item, found)
    return found


def _society(app, *, with_locality=True):
    with app.app_context():
        db.session.add(SocietyProfile(id=1, name="Green Valley Residency", address="1 Main Road",
                                      locality="Meadow Park (fictional)", city="Demo City"))
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        home = Household(flat=flat, label="Owner household")
        db.session.add(home)
        db.session.flush()
        ids = {}
        for name, roles, member in (
            ("admin", [PermissionRole.SOCIETY_ADMIN], False),
            ("platform", [PermissionRole.PLATFORM_ADMIN], False),
            ("coord", [PermissionRole.LOCALITY_COORDINATOR], False),
            # A resident who is also a coordinator: may moderate, but never their own correction.
            ("coordres", [PermissionRole.LOCALITY_COORDINATOR, PermissionRole.RESIDENT], True),
            ("resident", [PermissionRole.RESIDENT], True),
            ("neighbour", [PermissionRole.RESIDENT], True),
            ("applicant", [PermissionRole.APPLICANT], False),
        ):
            user = User(email=f"{name}@example.test", display_name=name.title(),
                        password_hash=generate_password_hash(PASSWORD), account_status=AccountStatus.ACTIVE,
                        email_verified_at=datetime.now(timezone.utc))
            db.session.add(user)
            db.session.flush()
            for role in roles:
                db.session.add(RoleAssignment(user=user, role=role))
            if member:
                db.session.add(Membership(user=user, household=home, category=ResidentCategory.OWNER,
                                          status=MembershipStatus.ACTIVE,
                                          valid_from=datetime.now(timezone.utc).date() - timedelta(days=2)))
            ids[name] = user.id
        if with_locality:
            locality = LocalityProfile(society_id=1, name="Meadow Park (fictional)", description="Test locality.",
                                       center_latitude=CENTER[0], center_longitude=CENTER[1],
                                       coverage_radius_m=3000, stale_after_days=180, is_fictional=True)
            db.session.add(locality)
            db.session.flush()
            categories = {}
            for order, (key, label, emergency) in enumerate((("pharmacy", "Pharmacy", False),
                                                            ("police", "Police", True),
                                                            ("other_service", "Other", False))):
                categories[key] = PlaceCategory(key=key, label=label, description="", is_emergency=emergency,
                                                sort_order=order, active=True)
                db.session.add(categories[key])
            db.session.flush()
            now = datetime.now(timezone.utc)
            for name, key, phone, days, status in (
                ("Meadow Care Pharmacy (demo)", "pharmacy", "+91 00000 10001", 20, PublicationStatus.ACTIVE),
                ("Evergreen Medicals (demo)", "pharmacy", "+91 00000 10002", 400, PublicationStatus.ACTIVE),
                ("Station Police (demo)", "police", "+91 00000 30001", None, PublicationStatus.ACTIVE),
                ("Closed Store (demo)", "other_service", "+91 00000 60009", 5, PublicationStatus.ARCHIVED),
            ):
                place = Place(locality_id=locality.id, category_id=categories[key].id, name=name,
                              address="Market Road (fictional)", latitude=CENTER[0] + 0.004,
                              longitude=CENTER[1] + 0.003, phone=phone, source_label="Fictional test data",
                              data_origin=DataOrigin.FICTIONAL_DEMO, publication_status=status, version=1)
                if days is not None:
                    place.verification_status = VerificationStatus.VERIFIED
                    place.last_verified_at = now - timedelta(days=days)
                    place.last_verification_method = VerificationMethod.DEMO_SEED
                db.session.add(place)
                db.session.flush()
                ids[name] = place.id
        db.session.commit()
        return {name: str(value) for name, value in ids.items()}


@pytest.fixture()
def seeded(app):
    return _society(app)


PHARMACY = "Meadow Care Pharmacy (demo)"


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


# ------------------------------------------------------------------ directory and access

def test_resident_browses_and_searches_the_directory(client, seeded):
    login(client, "resident")
    profile = client.get("/api/locality/profile")
    assert profile.status_code == 200
    locality = profile.json["locality"]
    assert locality["is_fictional"] is True and locality["coverage"]["radius_m"] == 3000
    assert {item["key"]: item["place_count"] for item in locality["categories"]} == {
        "pharmacy": 2, "police": 1, "other_service": 0}

    listing = client.get("/api/locality/places")
    assert listing.json["total"] == 3  # archived listing hidden
    assert "Closed Store (demo)" not in listing.get_data(as_text=True)
    states = {item["name"]: item["verification_state"] for item in listing.json["places"]}
    assert states == {PHARMACY: "VERIFIED", "Evergreen Medicals (demo)": "STALE", "Station Police (demo)": "UNVERIFIED"}

    assert client.get("/api/locality/places?q=meadow").json["total"] == 1
    assert client.get("/api/locality/places?q=100%25").json["total"] == 0  # % is escaped, not a wildcard
    assert client.get("/api/locality/places?category=police").json["places"][0]["name"] == "Station Police (demo)"
    assert client.get("/api/locality/places?limit=0").status_code == 400

    detail = client.get(f"/api/locality/places/{seeded[PHARMACY]}")
    assert detail.status_code == 200
    place = detail.json["place"]
    assert place["data_origin"] == "FICTIONAL_DEMO" and place["source_label"] and place["last_verified_at"]
    assert client.get(f"/api/locality/places/{seeded['Closed Store (demo)']}").status_code == 404

    inside = client.get(f"/api/locality/coverage/check?latitude={CENTER[0] + 0.01}&longitude={CENTER[1]}")
    outside = client.get(f"/api/locality/coverage/check?latitude={CENTER[0] + 0.5}&longitude={CENTER[1]}")
    assert inside.json["inside"] is True and outside.json["inside"] is False
    assert client.get("/api/locality/coverage/check?latitude=abc&longitude=1").status_code == 400


def test_role_boundaries(client, seeded):
    assert client.get("/api/locality/places").status_code == 401

    login(client, "applicant")
    assert client.get("/api/locality/places").status_code == 403
    logout(client)

    login(client, "resident")
    for url in ("/api/locality/admin/summary", "/api/locality/admin/places", "/api/locality/admin/corrections",
                "/api/locality/admin/events", "/api/locality/admin/alerts", "/api/locality/admin/reports"):
        assert client.get(url).status_code == 403, url
    assert post(client, "/api/locality/admin/places", {"name": "X"}).status_code == 403
    logout(client)

    # A Society Admin can read and share society events, but does not steward the locality.
    login(client, "admin")
    assert client.get("/api/locality/places").status_code == 200
    assert client.get("/api/locality/admin/places").status_code == 403
    assert post(client, f"/api/locality/admin/places/{seeded[PHARMACY]}/verify",
                {"method": "PHONE_CALL", "note": "Called"}).status_code == 403
    logout(client)

    login(client, "platform")
    assert client.get("/api/locality/admin/corrections").status_code == 403
    logout(client)

    login(client, "coord")
    assert client.get("/api/locality/admin/summary").status_code == 200
    assert client.get("/api/locality/places").status_code == 200
    # The coordinator role alone is not a resident: it cannot submit corrections.
    assert post(client, f"/api/locality/places/{seeded[PHARMACY]}/corrections",
                {"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 99999",
                 "reason": "Number seems wrong."}).status_code == 403


def test_unconfigured_locality_reports_clearly(app, client):
    _society(app, with_locality=False)
    login(client, "resident")
    response = client.get("/api/locality/places")
    assert response.status_code == 404 and response.json["error"]["code"] == "LOCALITY_NOT_CONFIGURED"


# ------------------------------------------------------------------ coordinator stewardship

def test_coordinator_creates_edits_verifies_and_archives(client, app, seeded):
    login(client, "coord")
    base = {"name": "Ward Office (demo)", "category": "other_service", "address": "Ward Road (fictional)",
            "latitude": CENTER[0] + 0.002, "longitude": CENTER[1] - 0.002, "phone": "+91 00000 50002",
            "source_label": "Fictional test data", "data_origin": "FICTIONAL_DEMO"}
    for bad in ({"website_url": "javascript:alert(1)"}, {"latitude": CENTER[0] + 0.5},
                {"phone": "call me"}, {"category": "nope"}, {"data_origin": "REAL_WORLD"}):
        response = post(client, "/api/locality/admin/places", {**base, **bad})
        assert response.status_code == 400, bad
    assert post(client, "/api/locality/admin/places", {**base, "surprise": 1}).status_code == 400

    created = post(client, "/api/locality/admin/places", base)
    assert created.status_code == 201, created.json
    place = created.json["place"]
    assert place["verification_state"] == "UNVERIFIED" and place["version"] == 1
    duplicate = post(client, "/api/locality/admin/places", {**base, "name": "ward office (DEMO)"})
    assert duplicate.status_code == 409 and duplicate.json["error"]["code"] == "DUPLICATE_PLACE"

    url = f"/api/locality/admin/places/{place['id']}"
    assert patch(client, url, {"phone": "+91 00000 50003"}).status_code == 400  # expected_version required
    edited = patch(client, url, {"phone": "+91 00000 50003", "expected_version": 1, "note": "New line"})
    assert edited.status_code == 200 and edited.json["place"]["version"] == 2
    stale = patch(client, url, {"phone": "+91 00000 50004", "expected_version": 1})
    assert stale.status_code == 409 and stale.json["error"]["code"] == "PLACE_VERSION_CONFLICT"

    assert post(client, f"{url}/verify", {"method": "PHONE_CALL"}).status_code == 400  # note required
    assert post(client, f"{url}/verify", {"method": "DEMO_SEED", "note": "x" * 5}).status_code == 400
    assert post(client, f"{url}/verify", {"method": "OFFICIAL_SOURCE", "note": "Checked"}).status_code == 400
    verified = post(client, f"{url}/verify", {"method": "PHONE_CALL", "note": "Called the front desk."})
    assert verified.status_code == 200 and verified.json["place"]["verification_state"] == "VERIFIED"

    assert post(client, f"{url}/mark-stale", {}).status_code == 400
    marked = post(client, f"{url}/mark-stale", {"reason": "Resident says it moved"})
    assert marked.json["place"]["verification_state"] == "NEEDS_RECHECK"
    archived = post(client, f"{url}/archive", {"reason": "Office closed"})
    assert archived.status_code == 200 and archived.json["place"]["publication_status"] == "ARCHIVED"

    detail = client.get(url)
    actions = [item["action"] for item in detail.json["history"]]
    assert actions[:5] == ["CREATED", "UPDATED", "VERIFIED", "MARKED_FOR_RECHECK", "ARCHIVED"]
    assert all(item["actor_display_name"] == "Coord" for item in detail.json["history"])
    assert len(detail.json["verifications"]) == 1
    logout(client)

    login(client, "resident")
    assert client.get(f"/api/locality/places/{place['id']}").status_code == 404
    logout(client)

    login(client, "coord")
    assert post(client, f"{url}/restore", {"reason": "Reopened"}).status_code == 200
    with app.app_context():
        logged = set(db.session.scalars(select(AuditLog.action).where(AuditLog.action.like("LOCALITY_%"))))
    assert {"LOCALITY_CREATED", "LOCALITY_UPDATED", "LOCALITY_VERIFIED", "LOCALITY_ARCHIVED"} <= logged


def test_profile_coverage_cannot_strand_listings(client, seeded):
    login(client, "coord")
    shrink = patch(client, "/api/locality/admin/profile", {"coverage_radius_m": 300})
    assert shrink.status_code == 409 and shrink.json["error"]["code"] == "PLACES_OUTSIDE_COVERAGE"
    assert patch(client, "/api/locality/admin/profile", {"coverage_radius_m": 50}).status_code == 400
    assert patch(client, "/api/locality/admin/profile", {"stale_after_days": 30}).status_code == 200


# ------------------------------------------------------------------ corrections: the main demo flow

def _report_phone(client, place_id, number="+91 00000 77777"):
    return post(client, f"/api/locality/places/{place_id}/corrections", {
        "issue_type": "WRONG_PHONE", "proposed_value": number,
        "reason": "Called the old number; it is disconnected. New number is on the shop board.",
    })


def test_resident_reports_phone_and_coordinator_approves(client, app, seeded):
    place_id = seeded[PHARMACY]
    login(client, "resident")
    assert client.get(f"/api/locality/places/{place_id}").json["open_corrections"] == 0
    submitted = _report_phone(client, place_id)
    assert submitted.status_code == 201, submitted.json
    correction = submitted.json["correction"]
    assert correction["status"] == "PENDING" and correction["current_value"] == "+91 00000 10001"
    again = _report_phone(client, place_id, "+91 00000 66666")
    assert again.status_code == 409 and again.json["error"]["code"] == "DUPLICATE_OPEN_CORRECTION"
    mine = client.get("/api/locality/corrections/me").json["corrections"]
    assert [item["id"] for item in mine] == [correction["id"]]
    detail = client.get(f"/api/locality/places/{place_id}").json
    assert detail["open_corrections"] == 1 and detail["my_corrections"][0]["status"] == "PENDING"
    assert client.get("/api/locality/places/" + place_id).json["place"]["phone"] == "+91 00000 10001"
    logout(client)

    login(client, "coord")
    queue = client.get("/api/locality/admin/corrections?status=PENDING").json["corrections"]
    assert queue[0]["id"] == correction["id"] and queue[0]["reporter_display_name"] == "Resident"
    assert queue[0]["published_value"] == "+91 00000 10001"
    url = f"/api/locality/admin/corrections/{correction['id']}/decision"
    assert post(client, url, {"decision": "APPROVE"}).status_code == 400  # reason is mandatory
    assert post(client, url, {"decision": "MAYBE", "reason": "Not sure"}).status_code == 400
    approved = post(client, url, {"decision": "APPROVE", "reason": "Confirmed by calling the shop."})
    assert approved.status_code == 200 and approved.json["correction"]["status"] == "APPROVED"
    assert post(client, url, {"decision": "REJECT", "reason": "Changed my mind"}).status_code == 409
    logout(client)

    login(client, "resident")
    place = client.get(f"/api/locality/places/{place_id}").json
    assert place["place"]["phone"] == "+91 00000 77777" and place["place"]["version"] == 2
    assert "CORRECTION_APPLIED" in [item["action"] for item in place["history"]]
    mine = client.get("/api/locality/corrections/me")
    assert mine.json["corrections"][0]["status"] == "APPROVED"
    assert mine.json["corrections"][0]["decision_reason"] == "Confirmed by calling the shop."
    # The reporter learns the outcome, never who reviewed it.
    assert not walk_keys(mine.json, set()) & REVIEWER_KEYS
    assert "Coord" not in mine.get_data(as_text=True)

    with app.app_context():
        verification = db.session.scalar(select(PlaceVerification).where(
            PlaceVerification.method == VerificationMethod.CORRECTION_REVIEW))
        assert verification.scope == "phone"
        assert db.session.scalar(select(AuditLog.id).where(AuditLog.action == "LOCALITY_CORRECTION_APPLIED"))


def test_rejection_and_clarification_round_trip(client, seeded):
    place_id = seeded[PHARMACY]
    login(client, "resident")
    first = _report_phone(client, place_id).json["correction"]
    logout(client)
    login(client, "neighbour")
    second = post(client, f"/api/locality/places/{place_id}/corrections", {
        "issue_type": "WRONG_ADDRESS", "proposed_value": "Shop 5, Meadow Market Road (fictional)",
        "reason": "The shop moved two doors down last month.",
    }).json["correction"]
    logout(client)

    login(client, "coord")
    queue = client.get("/api/locality/admin/corrections").json["corrections"]
    assert {item["id"] for item in queue} == {first["id"], second["id"]}
    rejected = post(client, f"/api/locality/admin/corrections/{first['id']}/decision",
                    {"decision": "REJECT", "reason": "The listed number still answers."})
    assert rejected.json["correction"]["status"] == "REJECTED"
    asked = post(client, f"/api/locality/admin/corrections/{second['id']}/decision",
                 {"decision": "REQUEST_CLARIFICATION", "reason": "Which shop number exactly?"})
    assert asked.json["correction"]["status"] == "CLARIFICATION_REQUESTED"
    # Approval needs the reporter's reply first.
    early = post(client, f"/api/locality/admin/corrections/{second['id']}/decision",
                 {"decision": "APPROVE", "reason": "Looks right"})
    assert early.status_code == 409
    logout(client)

    login(client, "resident")
    mine = client.get("/api/locality/corrections/me").json["corrections"]
    assert mine[0]["status"] == "REJECTED" and mine[0]["decision_reason"] == "The listed number still answers."
    # Only the reporter can reply.
    assert post(client, f"/api/locality/corrections/{second['id']}/respond",
                {"message": "It is shop 5."}).status_code == 404
    logout(client)

    login(client, "neighbour")
    assert post(client, f"/api/locality/corrections/{second['id']}/respond", {"message": "x"}).status_code == 400
    replied = post(client, f"/api/locality/corrections/{second['id']}/respond",
                   {"message": "It is shop 5, next to the bank.",
                    "proposed_value": "Shop 5, near Co-op Bank, Meadow Market Road (fictional)"})
    assert replied.status_code == 200 and replied.json["correction"]["status"] == "PENDING"
    assert replied.json["correction"]["proposed_value"].startswith("Shop 5, near")
    logout(client)

    login(client, "coord")
    approved = post(client, f"/api/locality/admin/corrections/{second['id']}/decision",
                    {"decision": "APPROVE", "reason": "Clarified and plausible."})
    assert approved.status_code == 200
    assert client.get(f"/api/locality/admin/places/{place_id}").json["place"]["address"].startswith("Shop 5, near")


def test_correction_validation_and_conflicts(client, seeded):
    place_id = seeded[PHARMACY]
    login(client, "resident")
    url = f"/api/locality/places/{place_id}/corrections"
    for body in (
        {"issue_type": "WRONG_PHONE", "proposed_value": "not a number", "reason": "Number is wrong here."},
        {"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 10001", "reason": "Same as current one."},
        {"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 12345", "reason": "short"},
        {"issue_type": "WRONG_WEBSITE", "proposed_value": "javascript:alert(1)", "reason": "Website is wrong."},
        {"issue_type": "WRONG_COORDINATES", "proposed_latitude": CENTER[0] + 1, "proposed_longitude": CENTER[1],
         "reason": "Pin is in the wrong spot."},
        {"issue_type": "MISSING_SERVICE", "proposed_value": "New chemist", "reason": "There is a new chemist."},
        {"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 12345", "reason": "Number is wrong.",
         "status": "APPROVED"},
    ):
        assert post(client, url, body).status_code == 400, body
    assert post(client, "/api/locality/places/00000000-0000-0000-0000-000000000000/corrections",
                {"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 12345",
                 "reason": "Number is wrong."}).status_code == 404
    missing = post(client, "/api/locality/corrections", {
        "issue_type": "MISSING_SERVICE", "proposed_value": "Lakeview Dental (demo)", "proposed_category": "other_service",
        "reason": "A new dental clinic opened near the lake."})
    assert missing.status_code == 201 and missing.json["correction"]["place"] is None
    submitted = _report_phone(client, place_id).json["correction"]
    logout(client)

    # The coordinator edits the phone directly after the resident reported it.
    login(client, "coord")
    version = client.get(f"/api/locality/admin/places/{place_id}").json["place"]["version"]
    assert patch(client, f"/api/locality/admin/places/{place_id}",
                 {"phone": "+91 00000 88888", "expected_version": version}).status_code == 200
    queued = client.get(f"/api/locality/admin/corrections/{submitted['id']}").json["correction"]
    assert queued["published_changed_since_submission"] is True
    conflict = post(client, f"/api/locality/admin/corrections/{submitted['id']}/decision",
                    {"decision": "APPROVE", "reason": "Number confirmed"})
    assert conflict.status_code == 409 and conflict.json["error"]["code"] == "PLACE_CHANGED_SINCE_SUBMISSION"
    assert client.get(f"/api/locality/admin/places/{place_id}").json["place"]["phone"] == "+91 00000 88888"


def test_coordinator_cannot_review_own_correction(client, seeded):
    login(client, "coordres")
    own = _report_phone(client, seeded[PHARMACY]).json["correction"]
    response = post(client, f"/api/locality/admin/corrections/{own['id']}/decision",
                    {"decision": "APPROVE", "reason": "Looks right to me"})
    assert response.status_code == 403 and response.json["error"]["code"] == "SELF_REVIEW_FORBIDDEN"
    logout(client)
    login(client, "coord")
    assert post(client, f"/api/locality/admin/corrections/{own['id']}/decision",
                {"decision": "APPROVE", "reason": "Second reviewer confirmed"}).status_code == 200


def test_closed_place_correction_archives_listing(client, seeded):
    place_id = seeded["Station Police (demo)"]
    login(client, "resident")
    correction = post(client, f"/api/locality/places/{place_id}/corrections", {
        "issue_type": "MOVED_OR_CLOSED", "reason": "The outpost shut down; the building is empty now."}).json
    logout(client)
    login(client, "coord")
    assert post(client, f"/api/locality/admin/corrections/{correction['correction']['id']}/decision",
                {"decision": "APPROVE", "reason": "Confirmed on site visit"}).status_code == 200
    logout(client)
    login(client, "resident")
    assert client.get(f"/api/locality/places/{place_id}").status_code == 404


# ------------------------------------------------------------------ events

def test_resident_event_needs_coordinator_approval(client, seeded):
    login(client, "resident")
    event = {"title": "Park Yoga (demo)", "description": "Morning yoga for all ages.", "organizer": "Resident",
             "venue": "Central park", "category": "HEALTH",
             "starts_at": _iso(timedelta(days=2)), "ends_at": _iso(timedelta(days=2, hours=2))}
    assert post(client, "/api/locality/events/submit", {**event, "ends_at": _iso(timedelta(days=1))}).status_code == 400
    assert post(client, "/api/locality/events/submit",
                {**event, "starts_at": "2026-12-01T10:00:00"}).status_code == 400  # no time zone
    assert post(client, "/api/locality/events/submit",
                {**event, "ends_at": _iso(timedelta(days=30))}).status_code == 400
    created = post(client, "/api/locality/events/submit", event)
    assert created.status_code == 201 and created.json["event"]["status"] == "PENDING"
    assert client.get("/api/locality/events").json["events"] == []
    assert client.get("/api/locality/events/mine").json["events"][0]["status"] == "PENDING"
    logout(client)

    login(client, "coord")
    url = f"/api/locality/admin/events/{created.json['event']['id']}/decision"
    assert post(client, url, {"decision": "PUBLISH"}).status_code == 400
    assert post(client, url, {"decision": "PUBLISH", "reason": "Community event, fine."}).status_code == 200
    logout(client)

    login(client, "neighbour")
    listed = client.get("/api/locality/events").json["events"]
    assert [item["title"] for item in listed] == ["Park Yoga (demo)"] and listed[0]["timing"] == "UPCOMING"
    assert "status" not in listed[0]
    assert client.get("/api/locality/events?when=past").json["events"] == []
    assert client.get("/api/locality/events?when=soon").status_code == 400


def test_society_event_sharing_requires_opt_in_and_hides_rsvps(client, app, seeded):
    with app.app_context():
        start = datetime.now(timezone.utc) + timedelta(days=4)
        events = {}
        for title, opted in (("Diwali Evening (demo)", True), ("Private AGM (demo)", False)):
            row = SocietyEvent(society_id=1, organizer_user_id=uuid.UUID(seeded["admin"]), title=title,
                               description="Society event description.", venue="Central lawn",
                               starts_at=start, ends_at=start + timedelta(hours=3), capacity=30,
                               status=EventStatus.PUBLISHED, locality_publish_requested=opted)
            db.session.add(row)
            db.session.flush()
            events[title] = str(row.id)
        db.session.add(EventRsvp(event_id=row.id, user_id=uuid.UUID(seeded["resident"]), status=RsvpStatus.GOING))
        db.session.commit()

    login(client, "resident")
    assert post(client, "/api/locality/events/submit",
                {"source_event_id": events["Diwali Evening (demo)"]}).status_code == 403
    logout(client)

    login(client, "admin")
    shareable = client.get("/api/locality/events/shareable")
    assert [item["title"] for item in shareable.json["events"]] == ["Diwali Evening (demo)"]
    not_opted = post(client, "/api/locality/events/submit", {"source_event_id": events["Private AGM (demo)"]})
    assert not_opted.status_code == 409 and not_opted.json["error"]["code"] == "NOT_OPTED_IN"
    assert post(client, "/api/locality/events/submit",
                {"source_event_id": events["Diwali Evening (demo)"], "title": "Renamed"}).status_code == 400
    shared = post(client, "/api/locality/events/submit",
                  {"source_event_id": events["Diwali Evening (demo)"], "category": "CULTURAL"})
    assert shared.status_code == 201 and shared.json["event"]["organizer"] == "Green Valley Residency"
    again = post(client, "/api/locality/events/submit", {"source_event_id": events["Diwali Evening (demo)"]})
    assert again.status_code == 409 and again.json["error"]["code"] == "ALREADY_SHARED"
    logout(client)

    login(client, "coord")
    post(client, f"/api/locality/admin/events/{shared.json['event']['id']}/decision",
         {"decision": "PUBLISH", "reason": "Open to neighbours."})
    logout(client)

    login(client, "neighbour")
    response = client.get("/api/locality/events")
    assert response.json["events"][0]["shared_by_society"] is True
    keys = walk_keys(response.json, set())
    assert not keys & {"capacity", "rsvps", "rsvp_count", "going", "attendees", "volunteer_slots"}
    assert "GOING" not in response.get_data(as_text=True)

    # If Module 3 cancels the event, it disappears from the locality.
    with app.app_context():
        source = db.session.get(SocietyEvent, uuid.UUID(events["Diwali Evening (demo)"]))
        source.status = EventStatus.CANCELLED
        db.session.commit()
    assert client.get("/api/locality/events").json["events"] == []


# ------------------------------------------------------------------ alerts, feed and reports

def test_alert_lifecycle_and_feed(client, seeded):
    login(client, "coord")
    base = {"title": "Water cut (demo)", "description": "Supply reduced for pipeline repair.",
            "severity": "MEDIUM", "source_type": "OFFICIAL_NOTICE", "source_label": "Ward office notice",
            "source_url": "https://example.org/notice",
            "starts_at": _iso(timedelta(hours=-1)), "expires_at": _iso(timedelta(days=1))}
    assert post(client, "/api/locality/admin/alerts", {**base, "source_url": None}).status_code == 400
    assert post(client, "/api/locality/admin/alerts", {**base, "severity": "EXTREME"}).status_code == 400
    assert post(client, "/api/locality/admin/alerts", {**base, "expires_at": _iso(timedelta(days=40))}).status_code == 400
    draft = post(client, "/api/locality/admin/alerts", base)
    assert draft.status_code == 201 and draft.json["alert"]["state"] == "DRAFT"
    logout(client)

    login(client, "resident")
    assert client.get("/api/locality/alerts").json["active"] == []
    logout(client)

    login(client, "coord")
    alert_id = draft.json["alert"]["id"]
    assert post(client, f"/api/locality/admin/alerts/{alert_id}/publish", {}).status_code == 200
    assert post(client, f"/api/locality/admin/alerts/{alert_id}/publish", {}).status_code == 409
    logout(client)

    login(client, "resident")
    alerts = client.get("/api/locality/alerts").json
    assert [item["title"] for item in alerts["active"]] == ["Water cut (demo)"]
    assert alerts["active"][0]["source_url"] == "https://example.org/notice"
    feed = client.get("/api/locality/feed").json
    assert feed["pinned"][0]["id"] == alert_id
    logout(client)

    login(client, "coord")
    assert post(client, f"/api/locality/admin/alerts/{alert_id}/archive", {}).status_code == 400
    assert post(client, f"/api/locality/admin/alerts/{alert_id}/archive", {"reason": "Supply restored"}).status_code == 200
    logout(client)
    login(client, "resident")
    alerts = client.get("/api/locality/alerts").json
    assert alerts["active"] == [] and alerts["past"][0]["state"] == "ARCHIVED"


def test_content_report_can_archive_an_event(client, seeded):
    login(client, "coord")
    created = post(client, "/api/locality/admin/alerts", {
        "title": "Road closure (demo)", "description": "Station Road closed for repairs.", "severity": "LOW",
        "source_type": "COMMUNITY", "source_label": "Residents",
        "starts_at": _iso(timedelta(hours=-1)), "expires_at": _iso(timedelta(days=2))}).json["alert"]
    post(client, f"/api/locality/admin/alerts/{created['id']}/publish", {})
    logout(client)

    login(client, "resident")
    report = {"target_type": "ALERT", "target_id": created["id"], "reason": "This road is open again."}
    assert post(client, "/api/locality/reports", {**report, "reason": "no"}).status_code == 400
    assert post(client, "/api/locality/reports",
                {**report, "target_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404
    first = post(client, "/api/locality/reports", report)
    assert first.status_code == 201
    assert post(client, "/api/locality/reports", report).status_code == 409
    logout(client)

    login(client, "coord")
    reports = client.get("/api/locality/admin/reports").json["reports"]
    assert reports[0]["id"] == first.json["report"]["id"]
    decided = post(client, f"/api/locality/admin/reports/{first.json['report']['id']}/decision",
                   {"decision": "ARCHIVE_CONTENT", "reason": "Confirmed the road reopened."})
    assert decided.status_code == 200
    assert post(client, f"/api/locality/admin/reports/{first.json['report']['id']}/decision",
                {"decision": "DISMISS", "reason": "Again"}).status_code == 409
    logout(client)

    login(client, "resident")
    assert client.get("/api/locality/alerts").json["active"] == []


def test_mutations_require_csrf(client, seeded):
    login(client, "resident")
    response = client.post(f"/api/locality/places/{seeded[PHARMACY]}/corrections",
                           json={"issue_type": "WRONG_PHONE", "proposed_value": "+91 00000 12345",
                                 "reason": "Number is wrong."})
    assert response.status_code in (400, 403)
    with client.application.app_context():
        assert db.session.get(Place, uuid.UUID(seeded[PHARMACY])).phone == "+91 00000 10001"
