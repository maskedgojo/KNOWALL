"""Module 6 authority case API tests. In-memory schema only; does not migrate the project database."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.authority.models import (
    AuthorityCase, AuthorityOfficer, CaseEvent, CaseMetricSnapshot, CaseNotification, Department, EscalationEvent,
    EscalationRule, JurisdictionRule, ResolutionVerification,
)
from app.modules.authority.service import AppendOnlyViolation
from app.modules.civic.models import CivicLocality, IssueHandoff
from app.modules.identity.models import (
    AccountStatus, Flat, Household, Membership, MembershipStatus, PermissionRole, ResidentCategory, RoleAssignment,
    SocietyProfile, Tower, User,
)

PASSWORD = "AuthorityStrongPass!123"
RESIDENTS = ("rahul", "priya", "amit", "sneha", "maya")
OFFICERS = {"roads_officer": "ROADS", "ward_officer": "WARD", "lights_officer": "LIGHTS"}
SUPPORTERS = ("priya", "amit", "sneha")


@pytest.fixture()
def app(tmp_path):
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "authority-test-secret-key",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
        "MAIL_DELIVERY_MODE": "memory",
        "OCR_PRIVATE_DIR": str(tmp_path / "private"),
    })
    with instance.app_context():
        db.create_all()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.drop_all()


def _account(name, role=None):
    user = User(email=f"{name}@example.test", display_name=name.replace("_", " ").title(),
                password_hash=generate_password_hash(PASSWORD), account_status=AccountStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc))
    db.session.add(user)
    db.session.flush()
    if role:
        db.session.add(RoleAssignment(user=user, role=role))
    return user


@pytest.fixture()
def world(app):
    with app.app_context():
        db.session.add(SocietyProfile(
            id=1, name="Green Valley Residency", address="1 Main Road", locality="Green Valley", city="Bhubaneswar"))
        loc = CivicLocality(society_id=1, name="Green Valley", center_lat=20.2961, center_lon=85.8245, radius_m=2500,
                            is_active=True)
        db.session.add(loc)
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        home = Household(flat=flat, label="Owner household")
        db.session.add(home)
        db.session.flush()
        _account("admin", PermissionRole.SOCIETY_ADMIN)
        _account("applicant", PermissionRole.APPLICANT)
        for name in RESIDENTS:
            user = _account(name, PermissionRole.RESIDENT)
            db.session.add(Membership(
                user=user, household=home, category=ResidentCategory.OWNER, status=MembershipStatus.ACTIVE,
                valid_from=datetime.now(timezone.utc).date() - timedelta(days=2)))
        departments = {}
        for code, name, categories, priority in (
            ("ROADS", "Roads Division (Demo)", ["ROAD_DAMAGE", "FOOTPATH"], 10),
            ("WARD", "Ward Office (Demo)", ["ROAD_DAMAGE", "PUBLIC_SPACE", "OTHER"], 200),
            ("LIGHTS", "Street Lighting Cell (Demo)", ["STREETLIGHT"], 10),
        ):
            row = Department(society_id=1, code=code, name=name, contact_label=f"{name} desk")
            db.session.add(row)
            db.session.flush()
            departments[code] = row
            for category in categories:
                db.session.add(JurisdictionRule(department_id=row.id, locality_id=loc.id, category=category,
                                                priority=priority))
        db.session.add(EscalationRule(department_id=departments["ROADS"].id, threshold_hours=48,
                                      target_label="Ward Office (Demo)"))
        for name, code in OFFICERS.items():
            user = _account(name)
            db.session.add(AuthorityOfficer(user_id=user.id, department_id=departments[code].id,
                                            title="Demo official"))
        db.session.commit()
        return {code: row.id for code, row in departments.items()}


# ------------------------------------------------------------------ client helpers

def csrf(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def send(client, method, url, body=None):
    return client.open(url, method=method, json=body if body is not None else {},
                       headers={"X-CSRF-Token": csrf(client)})


def post(client, url, body=None):
    return send(client, "POST", url, body)


def as_user(app, name):
    client = app.test_client()
    result = post(client, "/api/auth/login", {"email": f"{name}@example.test", "password": PASSWORD})
    assert result.status_code == 200, result.json
    return client


def png(color=(30, 160, 60)):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def multipart(client, url, form):
    return client.post(url, data=form, content_type="multipart/form-data", headers={"X-CSRF-Token": csrf(client)})


def routed_issue(app, *, category="ROAD_DAMAGE", reporter="rahul", title="Deep pothole outside the main gate"):
    """Module 5 flow up to a routed handoff: report, photo, validation, three supporters, route."""
    admin, author = as_user(app, "admin"), as_user(app, reporter)
    created = post(author, "/api/civic/issues", {
        "title": title, "category": category, "severity": "HIGH", "latitude": 20.2964, "longitude": 85.8248,
        "description": "A deep hole on the service road outside the main gate that is dangerous at night.",
        "address_hint": "Opposite the main gate",
    })
    assert created.status_code == 201, created.json
    issue_id = created.json["issue"]["id"]
    photo = multipart(author, f"/api/civic/issues/{issue_id}/evidence", {"file": (png(), "issue.png")})
    assert photo.status_code == 201, photo.json
    assert post(admin, f"/api/civic/admin/issues/{issue_id}/validate").status_code == 200
    for name in SUPPORTERS:
        assert post(as_user(app, name), f"/api/civic/issues/{issue_id}/support").status_code in (200, 201)
    routed = post(admin, f"/api/civic/issues/{issue_id}/route")
    assert routed.status_code == 201, routed.json
    return issue_id


def intake(app, issue_id, **body):
    result = post(as_user(app, "admin"), "/api/authority/cases/intake", {"canonical_issue_id": issue_id, **body})
    assert result.status_code == 201, result.json
    return result.json["case"]


def upload_proof(client, case_id, kind="RESOLUTION"):
    return multipart(client, f"/api/authority/cases/{case_id}/evidence",
                     {"file": (png(), "fixed.png"), "evidence_type": kind, "caption": "Road after repair"})


def work_to_resolved(app, case_id, officer="roads_officer"):
    client = as_user(app, officer)
    assert post(client, f"/api/authority/cases/{case_id}/acknowledge").status_code == 200
    assert post(client, f"/api/authority/cases/{case_id}/progress",
                {"message": "Crew scheduled for Tuesday morning."}).status_code == 200
    assert upload_proof(client, case_id).status_code == 201
    result = post(client, f"/api/authority/cases/{case_id}/resolve", {"summary": "Pothole filled and levelled."})
    assert result.status_code == 200, result.json
    return client


def case_status(app, issue_id, viewer="rahul"):
    result = as_user(app, viewer).get(f"/api/civic/issues/{issue_id}/case-status")
    assert result.status_code == 200, result.json
    return result.json["case"]


def verify(app, name, case_id, verdict, reason=""):
    return post(as_user(app, name), f"/api/authority/cases/{case_id}/verify", {"verdict": verdict, "reason": reason})


# ------------------------------------------------------------------ happy path

def test_end_to_end_case_closes_after_community_verification(app, world):
    issue_id = routed_issue(app)
    case = intake(app, issue_id)
    assert case["status"] == "ROUTED" and case["department"]["code"] == "ROADS"
    assert case["department"]["is_demo"] is True and case["simulated"] is True
    case_id = case["case_id"]

    with app.app_context():
        handoff = db.session.scalar(select(IssueHandoff))
        assert handoff.routing_status.value == "ACKNOWLEDGED" and handoff.authority_case_id == case["authority_case_id"]

    work_to_resolved(app, case_id)
    tracker = case_status(app, issue_id)
    assert tracker["status"] == "RESOLVED" and tracker["verification"]["viewer_can_verify"] is True
    assert tracker["authority_case_id"] == case["authority_case_id"]

    first = verify(app, "rahul", case_id, "CONFIRMED")
    assert first.status_code == 201 and first.json["outcome"] is None
    second = verify(app, "priya", case_id, "CONFIRMED")
    assert second.json["outcome"] == "CLOSED"

    official = as_user(app, "roads_officer").get(f"/api/authority/cases/{case_id}").json["case"]
    resident = case_status(app, issue_id)
    assert official["status"] == resident["status"] == "CLOSED"
    assert official["closure_basis"] == "COMMUNITY_VERIFIED"
    actions = [event["action"] for event in official["events"]]
    assert actions == ["INTAKE", "ACKNOWLEDGED", "PROGRESS", "EVIDENCE_ADDED", "RESOLVED",
                       "VERIFICATION_CONFIRMED", "VERIFICATION_CONFIRMED", "CLOSED"]
    assert [event["sequence"] for event in official["events"]] == list(range(1, 9))

    # Module 5 shows the same authoritative status on the civic issue.
    issue = as_user(app, "rahul").get(f"/api/civic/issues/{issue_id}").json["issue"]
    assert issue["authoritative_status"]["status"] == "CLOSED"
    assert issue["authoritative_status"]["authority_case_id"] == case["authority_case_id"]
    # Support was never touched by Module 6.
    assert issue["support_count"] == 3


def test_resident_timeline_hides_internal_reasons(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id, note="Internal note for staff only.")["case_id"]
    tracker = case_status(app, issue_id, viewer="maya")
    assert tracker["timeline"][0]["summary"].startswith("Case opened")
    assert "reason" not in tracker["timeline"][0]
    assert "Internal note" not in str(tracker)
    staff = as_user(app, "admin").get(f"/api/authority/cases/{case_id}").json["case"]
    assert staff["events"][0]["reason"] == "Internal note for staff only."


# ------------------------------------------------------------------ permissions and scope

def test_only_assigned_department_can_act(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    lights = as_user(app, "lights_officer")
    denied = post(lights, f"/api/authority/cases/{case_id}/acknowledge")
    assert denied.status_code == 403 and denied.json["error"]["code"] == "NOT_ASSIGNED"
    assert lights.get(f"/api/authority/cases/{case_id}").status_code == 403
    assert lights.get("/api/authority/cases").json["cases"] == []
    assert as_user(app, "roads_officer").get("/api/authority/cases").json["total"] == 1
    # Residents and applicants are not officials.
    for name in ("rahul", "applicant"):
        client = as_user(app, name)
        assert client.get("/api/authority/cases").status_code == 403
        assert post(client, f"/api/authority/cases/{case_id}/acknowledge").status_code == 403
    # Coordinators cannot impersonate a department.
    assert post(as_user(app, "admin"), f"/api/authority/cases/{case_id}/acknowledge").status_code == 403
    assert app.test_client().get("/api/authority/cases").status_code == 401


def test_revoked_official_loses_access(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    admin = as_user(app, "admin")
    officers = admin.get("/api/authority/departments").json["departments"]
    roads = next(item for item in officers if item["code"] == "ROADS")
    officer_id = roads["officers"][0]["id"]
    assert send(admin, "DELETE", f"/api/authority/admin/officers/{officer_id}").status_code == 200
    assert post(as_user(app, "roads_officer"), f"/api/authority/cases/{case_id}/acknowledge").status_code == 403


def test_assign_officer_requires_verified_account(app, world):
    admin = as_user(app, "admin")
    ok = post(admin, "/api/authority/admin/officers",
              {"email": "maya@example.test", "department_id": world["WARD"], "title": "Ward clerk (demo)"})
    assert ok.status_code == 201
    again = post(admin, "/api/authority/admin/officers", {"email": "maya@example.test", "department_id": world["ROADS"]})
    assert again.json["error"]["code"] == "ALREADY_OFFICER"
    assert post(admin, "/api/authority/admin/officers",
                {"email": "nobody@example.test", "department_id": world["ROADS"]}).status_code == 409
    assert post(as_user(app, "rahul"), "/api/authority/admin/officers",
                {"email": "amit@example.test", "department_id": world["ROADS"]}).status_code == 403
    me = as_user(app, "maya").get("/api/authority/me").json
    assert me["officer"]["department"]["code"] == "WARD" and me["is_coordinator"] is False


# ------------------------------------------------------------------ intake rules

def test_intake_rules(app, world):
    admin = as_user(app, "admin")
    missing = post(admin, "/api/authority/cases/intake", {"canonical_issue_id": "00000000-0000-0000-0000-000000000000"})
    assert missing.status_code == 404
    assert post(admin, "/api/authority/cases/intake", {"canonical_issue_id": "nope"}).status_code == 400

    issue_id = routed_issue(app)
    assert admin.get("/api/authority/intake-queue").json["handoffs"][0]["suggested_department"]["name"] \
        == "Roads Division (Demo)"
    wrong = post(admin, "/api/authority/cases/intake", {"canonical_issue_id": issue_id, "department_id": world["LIGHTS"]})
    assert wrong.status_code == 409 and wrong.json["error"]["code"] == "OUT_OF_JURISDICTION"
    manual = post(admin, "/api/authority/cases/intake", {"canonical_issue_id": issue_id, "department_id": world["WARD"]})
    assert manual.status_code == 201 and manual.json["case"]["department"]["code"] == "WARD"
    repeat = post(admin, "/api/authority/cases/intake", {"canonical_issue_id": issue_id})
    assert repeat.status_code == 200 and repeat.json["created"] is False
    assert repeat.json["case"]["case_id"] == manual.json["case"]["case_id"]
    assert admin.get("/api/authority/intake-queue").json["handoffs"] == []
    assert post(as_user(app, "roads_officer"), "/api/authority/cases/intake",
                {"canonical_issue_id": issue_id}).status_code == 403

    uncovered = routed_issue(app, category="GARBAGE", reporter="maya", title="Garbage dumped beside the bus stop")
    none = post(admin, "/api/authority/cases/intake", {"canonical_issue_id": uncovered})
    assert none.status_code == 409 and none.json["error"]["code"] == "NO_DEPARTMENT"
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(AuthorityCase)) == 1


# ------------------------------------------------------------------ transfer

def test_transfer_logged_and_loops_rejected(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    roads, ward = as_user(app, "roads_officer"), as_user(app, "ward_officer")
    same = post(roads, f"/api/authority/cases/{case_id}/transfer",
                {"to_department_id": world["ROADS"], "reason": "Testing a same-department move."})
    assert same.json["error"]["code"] == "SAME_DEPARTMENT"
    wrong = post(roads, f"/api/authority/cases/{case_id}/transfer",
                 {"to_department_id": world["LIGHTS"], "reason": "Not ours, try the lighting cell."})
    assert wrong.json["error"]["code"] == "OUT_OF_JURISDICTION"
    assert post(roads, f"/api/authority/cases/{case_id}/transfer",
                {"to_department_id": world["WARD"], "reason": "x"}).status_code == 400

    moved = post(roads, f"/api/authority/cases/{case_id}/transfer",
                 {"to_department_id": world["WARD"], "reason": "Service road belongs to the ward, not the division."})
    assert moved.status_code == 200
    case = moved.json["case"]
    assert case["department"]["code"] == "WARD" and case["status"] == "ROUTED"
    assert case["transfers"][0]["reason"].startswith("Service road")
    # The old department lost access; the new one accepts.
    assert post(roads, f"/api/authority/cases/{case_id}/acknowledge").status_code == 403
    loop = post(ward, f"/api/authority/cases/{case_id}/transfer",
                {"to_department_id": world["ROADS"], "reason": "Sending it straight back to roads."})
    assert loop.status_code == 409 and loop.json["error"]["code"] == "TRANSFER_LOOP"
    assert post(ward, f"/api/authority/cases/{case_id}/acknowledge").status_code == 200
    assert post(ward, f"/api/authority/cases/{case_id}/progress", {"message": "Survey team assigned."}).status_code == 200
    late = post(ward, f"/api/authority/cases/{case_id}/transfer",
                {"to_department_id": world["ROADS"], "reason": "Too late to move it now."})
    assert late.status_code == 409 and late.json["error"]["code"] == "INVALID_STATE"


# ------------------------------------------------------------------ lifecycle guards

def test_invalid_transitions_rejected(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    roads = as_user(app, "roads_officer")
    assert post(roads, f"/api/authority/cases/{case_id}/progress", {"message": "Too early."}).status_code == 409
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Claiming fixed early."}).status_code == 409
    assert post(roads, f"/api/authority/cases/{case_id}/acknowledge").status_code == 200
    assert post(roads, f"/api/authority/cases/{case_id}/acknowledge").status_code == 409
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Skipping the work."}).status_code == 409
    assert verify(app, "rahul", case_id, "CONFIRMED").json["error"]["code"] == "VERIFICATION_CLOSED"
    admin = as_user(app, "admin")
    assert post(admin, f"/api/authority/cases/{case_id}/reopen", {"reason": "Nothing to reopen yet."}).status_code == 409


def test_resolution_without_proof_is_blocked(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    roads = as_user(app, "roads_officer")
    post(roads, f"/api/authority/cases/{case_id}/acknowledge")
    post(roads, f"/api/authority/cases/{case_id}/progress", {"message": "Crew on site."})
    blocked = post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Pothole filled and levelled."})
    assert blocked.status_code == 409 and blocked.json["error"]["code"] == "PROOF_REQUIRED"
    assert upload_proof(roads, case_id, kind="PROGRESS").status_code == 201
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Pothole filled."}).json["error"]["code"] \
        == "PROOF_REQUIRED"
    bad = multipart(roads, f"/api/authority/cases/{case_id}/evidence", {"file": (io.BytesIO(b"%PDF-1.4"), "x.pdf")})
    assert bad.status_code == 400
    assert upload_proof(roads, case_id).status_code == 201
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Pothole filled."}).status_code == 200


# ------------------------------------------------------------------ verification

def test_verification_scope_and_single_vote(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    work_to_resolved(app, case_id)
    outsider = verify(app, "maya", case_id, "CONFIRMED")
    assert outsider.status_code == 403 and outsider.json["error"]["code"] == "NOT_AFFECTED"
    assert case_status(app, issue_id, viewer="maya")["verification"]["viewer_can_verify"] is False
    assert verify(app, "roads_officer", case_id, "CONFIRMED").status_code == 403
    assert verify(app, "rahul", case_id, "DISPUTED").status_code == 400  # a dispute needs a reason
    assert verify(app, "rahul", case_id, "MAYBE").status_code == 400
    assert verify(app, "rahul", case_id, "CONFIRMED").status_code == 201
    # A second session for the same account cannot vote again.
    repeat = verify(app, "rahul", case_id, "DISPUTED", "Changed my mind about the repair.")
    assert repeat.status_code == 409 and repeat.json["error"]["code"] == "ALREADY_VERIFIED"
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(ResolutionVerification)) == 1


def test_rejected_fix_reopens_same_case_then_closes(app, world):
    issue_id = routed_issue(app)
    case = intake(app, issue_id)
    case_id = case["case_id"]
    roads = work_to_resolved(app, case_id)
    assert verify(app, "rahul", case_id, "DISPUTED", "The hole is still there on the left side.").json["outcome"] is None
    photo = multipart(as_user(app, "priya"), f"/api/authority/cases/{case_id}/verify",
                      {"verdict": "DISPUTED", "reason": "Water still pools in the same spot.",
                       "photo": (png((90, 90, 90)), "still-broken.png")})
    assert photo.status_code == 201 and photo.json["outcome"] == "REOPENED"

    tracker = case_status(app, issue_id)
    assert tracker["status"] == "REOPENED" and tracker["round"] == 2 and tracker["reopen_count"] == 1
    assert tracker["case_id"] == case_id and tracker["authority_case_id"] == case["authority_case_id"]
    detail = roads.get(f"/api/authority/cases/{case_id}").json["case"]
    dispute = next(item for item in detail["verifications"] if item["has_photo"])
    assert roads.get(f"/api/authority/verifications/{dispute['id']}/photo").status_code == 200
    assert as_user(app, "maya").get(f"/api/authority/verifications/{dispute['id']}/photo").status_code == 404

    # Round 2: the previous proof does not count; new proof and new votes are required.
    assert post(roads, f"/api/authority/cases/{case_id}/progress", {"message": "Relaying the full patch."}).status_code == 200
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Patched again."}).json["error"]["code"] \
        == "PROOF_REQUIRED"
    assert upload_proof(roads, case_id).status_code == 201
    assert post(roads, f"/api/authority/cases/{case_id}/resolve", {"summary": "Whole stretch resurfaced."}).status_code == 200
    assert verify(app, "rahul", case_id, "CONFIRMED").status_code == 201
    assert verify(app, "amit", case_id, "CONFIRMED").json["outcome"] == "CLOSED"
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(AuthorityCase)) == 1


def test_coordinator_controlled_reopen(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    work_to_resolved(app, case_id)
    verify(app, "sneha", case_id, "DISPUTED", "Photo shows a different stretch of road.")
    admin = as_user(app, "admin")
    assert post(admin, f"/api/authority/cases/{case_id}/reopen", {"reason": "short"}).status_code == 400
    result = post(admin, f"/api/authority/cases/{case_id}/reopen",
                  {"reason": "The dispute photo is convincing; department must recheck."})
    assert result.status_code == 200 and result.json["case"]["status"] == "REOPENED"
    assert post(as_user(app, "rahul"), f"/api/authority/cases/{case_id}/reopen",
                {"reason": "Residents cannot reopen directly."}).status_code == 403


def test_verification_window_expiry_is_settled_once(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    work_to_resolved(app, case_id)
    admin = as_user(app, "admin")
    early = post(admin, f"/api/authority/cases/{case_id}/close", {"reason": "Closing while the window is open."})
    assert early.json["error"]["code"] == "CLOSE_NOT_ALLOWED"
    with app.app_context():
        row = db.session.get(AuthorityCase, __import__("uuid").UUID(case_id))
        row.verification_closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    assert post(admin, "/api/authority/admin/sweep").json["report"]["awaiting_coordinator"] == 1
    assert post(admin, "/api/authority/admin/sweep").json["report"]["awaiting_coordinator"] == 0
    assert verify(app, "rahul", case_id, "CONFIRMED").json["error"]["code"] == "VERIFICATION_CLOSED"
    closed = post(admin, f"/api/authority/cases/{case_id}/close", {"reason": "No resident responded in 72 hours."})
    assert closed.status_code == 200 and closed.json["case"]["closure_basis"] == "COORDINATOR_AFTER_WINDOW"


def test_window_majority_closes_on_sweep(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    work_to_resolved(app, case_id)
    verify(app, "rahul", case_id, "CONFIRMED")
    with app.app_context():
        row = db.session.get(AuthorityCase, __import__("uuid").UUID(case_id))
        row.verification_closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    report = post(as_user(app, "admin"), "/api/authority/admin/sweep").json["report"]
    assert report["closed"] == 1
    assert case_status(app, issue_id)["closure_basis"] == "WINDOW_MAJORITY"


# ------------------------------------------------------------------ escalation

def _make_overdue(app, case_id):
    with app.app_context():
        row = db.session.get(AuthorityCase, __import__("uuid").UUID(case_id))
        row.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()


def test_overdue_sweep_escalates_once_per_deadline(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    roads = as_user(app, "roads_officer")
    post(roads, f"/api/authority/cases/{case_id}/acknowledge")
    _make_overdue(app, case_id)
    admin = as_user(app, "admin")
    assert admin.get("/api/authority/cases?overdue=true").json["total"] == 1
    assert case_status(app, issue_id)["is_overdue"] is True
    assert post(admin, "/api/authority/admin/sweep").json["report"]["escalated"] == 1
    # Re-running after downtime does not escalate the same deadline again.
    assert post(admin, "/api/authority/admin/sweep").json["report"]["escalated"] == 0
    runner = app.test_cli_runner()
    assert "escalated=0" in runner.invoke(args=["authority-sweep"]).output
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(EscalationEvent)) == 1
        assert db.session.scalar(select(func.count()).select_from(CaseMetricSnapshot)) == 3
        assert db.session.scalar(select(func.count()).select_from(CaseNotification).where(
            CaseNotification.event_type == "CASE_ESCALATED")) >= 2
    escalation = admin.get(f"/api/authority/cases/{case_id}").json["case"]["escalations"][0]
    assert escalation["kind"] == "AUTO_OVERDUE" and escalation["target_label"] == "Ward Office (Demo)"

    revised = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    update = post(roads, f"/api/authority/cases/{case_id}/progress",
                  {"message": "Material delayed; crew booked for Friday.", "revised_due_at": revised})
    assert update.status_code == 200
    case = update.json["case"]
    assert case["is_overdue"] is False and case["escalations"][0]["outcome"] == "RESPONDED"
    assert post(roads, f"/api/authority/cases/{case_id}/progress",
                {"message": "Bad date.", "revised_due_at": "2001-01-01T00:00:00Z"}).status_code == 400
    # The revised deadline is a new cycle; missing it escalates again.
    _make_overdue(app, case_id)
    assert post(admin, "/api/authority/admin/sweep").json["report"]["escalated"] == 1


def test_manual_escalation_requires_simulation_acknowledgement(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    admin = as_user(app, "admin")
    missing = post(admin, f"/api/authority/cases/{case_id}/escalate", {"reason": "No response from department."})
    assert missing.status_code == 400 and "acknowledge_simulated" in missing.json["error"]["fields"]
    body = {"reason": "No response from department.", "acknowledge_simulated": True}
    assert post(admin, f"/api/authority/cases/{case_id}/escalate", body).status_code == 200
    assert post(admin, f"/api/authority/cases/{case_id}/escalate", body).json["error"]["code"] == "ALREADY_ESCALATED"
    assert post(as_user(app, "roads_officer"), f"/api/authority/cases/{case_id}/escalate", body).status_code == 403


# ------------------------------------------------------------------ clarification

def test_clarification_roundtrip(app, world):
    issue_id = routed_issue(app)
    case_id = intake(app, issue_id)["case_id"]
    roads = as_user(app, "roads_officer")
    post(roads, f"/api/authority/cases/{case_id}/acknowledge")
    asked = post(roads, f"/api/authority/cases/{case_id}/request-clarification",
                 {"question": "Is the pothole on the left or right lane when leaving the gate?"})
    assert asked.json["case"]["status"] == "CLARIFICATION_REQUESTED"
    assert post(roads, f"/api/authority/cases/{case_id}/progress", {"message": "Waiting."}).status_code == 409
    rahul = as_user(app, "rahul")
    assert case_status(app, issue_id)["open_clarification"]["question"].startswith("Is the pothole")
    assert case_status(app, issue_id, viewer="priya")["open_clarification"] is None
    notes = rahul.get("/api/authority/notifications").json
    assert any(item["event_type"] == "CLARIFICATION_REQUESTED" for item in notes["notifications"])
    assert post(as_user(app, "priya"), f"/api/authority/cases/{case_id}/respond-clarification",
                {"response": "Left lane I think."}).status_code == 404
    answered = post(rahul, f"/api/authority/cases/{case_id}/respond-clarification",
                    {"response": "Left lane, about two metres from the gate pillar."})
    assert answered.status_code == 200 and answered.json["case"]["status"] == "ACKNOWLEDGED"
    assert post(rahul, f"/api/authority/cases/{case_id}/respond-clarification",
                {"response": "Answering twice."}).json["error"]["code"] == "NO_OPEN_CLARIFICATION"
    read = post(rahul, f"/api/authority/notifications/{notes['notifications'][0]['id']}/read")
    assert read.status_code == 200 and read.json["read_at"]


# ------------------------------------------------------------------ history and analytics

def test_history_is_append_only(app, world):
    case_id = intake(app, routed_issue(app))["case_id"]
    with app.app_context():
        row = db.session.scalar(select(CaseEvent))
        row.reason = "Rewritten history"
        with pytest.raises(AppendOnlyViolation):
            db.session.flush()
        db.session.rollback()
        with pytest.raises(AppendOnlyViolation):
            db.session.delete(db.session.scalar(select(CaseEvent)))
            db.session.flush()
        db.session.rollback()
        assert db.session.scalar(select(CaseEvent.reason)) != "Rewritten history"
    assert case_id


def test_evidence_file_access(app, world):
    issue_id = routed_issue(app)
    case = intake(app, issue_id)
    case_id = case["case_id"]
    roads = work_to_resolved(app, case_id)
    detail = roads.get(f"/api/authority/cases/{case_id}").json["case"]
    reporter_photo = detail["issue"]["evidence"][0]["evidence_id"]
    assert roads.get(f"/api/authority/cases/{case_id}/issue-evidence/{reporter_photo}/file").status_code == 200
    assert as_user(app, "lights_officer").get(
        f"/api/authority/cases/{case_id}/issue-evidence/{reporter_photo}/file").status_code == 403
    proof = detail["evidence"][0]["id"]
    assert as_user(app, "maya").get(f"/api/authority/evidence/{proof}/file").status_code == 200
    assert as_user(app, "lights_officer").get(f"/api/authority/evidence/{proof}/file").status_code == 404
    assert as_user(app, "applicant").get(f"/api/authority/evidence/{proof}/file").status_code == 404


def test_analytics_reconcile_states_and_timestamps(app, world):
    closed_issue = routed_issue(app)
    closed = intake(app, closed_issue)["case_id"]
    work_to_resolved(app, closed)
    verify(app, "rahul", closed, "CONFIRMED")
    verify(app, "priya", closed, "CONFIRMED")
    open_issue = routed_issue(app, reporter="maya", category="STREETLIGHT", title="Streetlight dead on park lane")
    open_case = intake(app, open_issue)["case_id"]
    admin = as_user(app, "admin")
    post(admin, f"/api/authority/cases/{open_case}/escalate",
         {"reason": "Lighting cell has not responded.", "acknowledge_simulated": True})

    report = admin.get("/api/admin/analytics/civic").json
    assert report["totals"]["cases"] == 2 and report["totals"]["open"] == 1
    assert report["by_status"]["CLOSED"] == 1 and report["by_status"]["ROUTED"] == 1
    assert report["reconciliation"]["consistent"] is True
    assert report["reconciliation"]["status_sum_matches_total"] is True
    assert report["durations"]["intake_to_close"]["count"] == 1
    assert report["escalations"]["manual"] == 1
    assert report["outcomes"]["closed_by_basis"]["COMMUNITY_VERIFIED"] == 1
    assert report["outcomes"]["verifications"]["confirmed"] == 2
    assert {item["name"] for item in report["by_department"]} == {"Roads Division (Demo)", "Street Lighting Cell (Demo)"}
    assert report["audit"] and "Simulated" in report["simulation_notice"]
    assert as_user(app, "roads_officer").get("/api/admin/analytics/civic").status_code == 403

    # A status changed outside the workflow is caught by reconciliation.
    with app.app_context():
        row = db.session.get(AuthorityCase, __import__("uuid").UUID(open_case))
        row.status = row.status.__class__.IN_PROGRESS
        db.session.commit()
    broken = admin.get("/api/admin/analytics/civic").json["reconciliation"]
    assert broken["consistent"] is False and broken["mismatches"][0]["case_id"] == open_case


def test_department_admin_endpoints(app, world):
    admin = as_user(app, "admin")
    created = post(admin, "/api/authority/admin/departments",
                   {"code": "drain", "name": "Drainage Unit (Demo)", "contact_label": "Drainage desk"})
    assert created.status_code == 201 and created.json["department"]["code"] == "DRAIN"
    dept_id = created.json["department"]["id"]
    assert post(admin, "/api/authority/admin/departments", {"code": "DRAIN", "name": "Again"}).status_code == 409
    rules = send(admin, "PUT", f"/api/authority/admin/departments/{dept_id}/jurisdiction",
                 {"categories": ["DRAINAGE", "GARBAGE"]})
    assert rules.status_code == 200 and {item["category"] for item in rules.json["jurisdiction"]} == {"DRAINAGE", "GARBAGE"}
    assert send(admin, "PUT", f"/api/authority/admin/departments/{dept_id}/jurisdiction",
                {"categories": ["PARTY"]}).status_code == 400
    rule = send(admin, "PUT", f"/api/authority/admin/departments/{dept_id}/escalation-rule",
                {"threshold_hours": 24, "target_label": "Ward Office (Demo)"})
    assert rule.json["escalation_rule"]["threshold_hours"] == 24
    assert send(admin, "PATCH", f"/api/authority/admin/departments/{dept_id}",
                {"escalation_department_id": dept_id}).status_code == 400
    assert send(admin, "PATCH", f"/api/authority/admin/departments/{dept_id}", {"is_active": False}).status_code == 200
    listed = as_user(app, "roads_officer").get("/api/authority/departments").json["departments"]
    assert all("officers" not in item for item in listed) and all(item["is_demo"] for item in listed)
    assert post(as_user(app, "rahul"), "/api/authority/admin/departments",
                {"code": "X1", "name": "Resident made"}).status_code == 403
