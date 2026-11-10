"""Module 5 civic issue API tests. In-memory schema only; does not migrate the project database."""
import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image
from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.civic.models import (
    CivicIssue, CivicLocality, DuplicateLink, IssueHandoff, IssueModerationReport, IssueSupport, IssueTransition,
    PrioritySnapshot,
)
from app.modules.civic import priority
from app.modules.identity.models import (
    AccountStatus, AuditLog, Flat, Household, Membership, MembershipStatus, PermissionRole, ResidentCategory,
    RoleAssignment, SocietyProfile, Tower, User,
)

PASSWORD = "CivicStrongPass!123"
RESIDENTS = ("rahul", "priya", "amit", "sneha", "maya")


@pytest.fixture()
def app(tmp_path):
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "civic-test-secret-key",
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


@pytest.fixture()
def people(app):
    with app.app_context():
        db.session.add(SocietyProfile(
            id=1, name="Green Valley Residency", address="1 Main Road", locality="Green Valley", city="Bhubaneswar"))
        db.session.add(CivicLocality(
            society_id=1, name="Green Valley", center_lat=20.2961, center_lon=85.8245, radius_m=2500, is_active=True))
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        home = Household(flat=flat, label="Owner household")
        db.session.add(home)
        db.session.flush()
        specs = [("admin", PermissionRole.SOCIETY_ADMIN, False), ("applicant", PermissionRole.APPLICANT, False)]
        specs += [(name, PermissionRole.RESIDENT, True) for name in RESIDENTS]
        for name, role, member in specs:
            user = User(
                email=f"{name}@example.test", display_name=name.title(),
                password_hash=generate_password_hash(PASSWORD), account_status=AccountStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc), phone="9876543210",
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user=user, role=role))
            if member:
                db.session.add(Membership(
                    user=user, household=home, category=ResidentCategory.OWNER, status=MembershipStatus.ACTIVE,
                    valid_from=datetime.now(timezone.utc).date() - timedelta(days=2)))
        db.session.commit()


def csrf(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def send(client, method, url, body=None):
    return client.open(url, method=method, json=body if body is not None else {}, headers={"X-CSRF-Token": csrf(client)})


def post(client, url, body=None):
    return send(client, "POST", url, body)


def as_user(app, name):
    client = app.test_client()
    result = post(client, "/api/auth/login", {"email": f"{name}@example.test", "password": PASSWORD})
    assert result.status_code == 200, result.json
    return client


def png(size=(8, 8), color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def upload(client, issue_id, *, name="pothole.png", visibility=None, data=None):
    form = {"file": (data or png(), name), "caption": "Photo of the pothole"}
    if visibility:
        form["visibility"] = visibility
    return client.post(f"/api/civic/issues/{issue_id}/evidence", data=form, content_type="multipart/form-data",
                       headers={"X-CSRF-Token": csrf(client)})


def issue_body(**overrides):
    body = {
        "title": "Deep pothole outside the main gate",
        "description": "A deep pothole on the service road outside the main gate that is dangerous at night.",
        "category": "ROAD_DAMAGE", "severity": "HIGH", "latitude": 20.2964, "longitude": 85.8248,
        "address_hint": "Opposite the main gate",
    }
    body.update(overrides)
    return body


def create(client, **overrides):
    result = post(client, "/api/civic/issues", issue_body(**overrides))
    assert result.status_code == 201, result.json
    return result.json["issue"]["id"]


def validate(admin, issue_id, **body):
    result = post(admin, f"/api/civic/admin/issues/{issue_id}/validate", body)
    assert result.status_code == 200, result.json
    return result.json["issue"]


def validated_issue(app, reporter="rahul", **overrides):
    admin = as_user(app, "admin")
    issue_id = create(as_user(app, reporter), **overrides)
    validate(admin, issue_id)
    return issue_id


def support(client, issue_id):
    return post(client, f"/api/civic/issues/{issue_id}/support")


# ------------------------------------------------------------------ access and creation

def test_access_requires_verified_resident(app, people):
    anonymous = app.test_client()
    assert anonymous.get("/api/civic/issues").status_code == 401
    applicant = as_user(app, "applicant")
    assert applicant.get("/api/civic/issues").status_code == 403
    assert post(applicant, "/api/civic/issues", issue_body()).status_code == 403
    rahul = as_user(app, "rahul")
    assert rahul.get("/api/civic/issues").status_code == 200
    assert post(rahul, "/api/civic/admin/issues/00000000-0000-0000-0000-000000000000/validate").status_code == 403
    assert rahul.get("/api/civic/admin/issues").status_code == 403


def test_locality_endpoint_describes_coverage(app, people):
    shown = as_user(app, "rahul").get("/api/civic/locality").json["locality"]
    assert shown["radius_m"] == 2500 and shown["required_supporters"] == 3 and shown["max_evidence_per_issue"] == 5
    assert app.test_client().get("/api/civic/locality").status_code == 401


def test_create_submits_and_records_history(app, people):
    rahul = as_user(app, "rahul")
    result = post(rahul, "/api/civic/issues", issue_body())
    assert result.status_code == 201
    issue = result.json["issue"]
    assert issue["state"] == "SUBMITTED"
    assert issue["viewer_is_reporter"] is True
    assert result.json["similar"] == []
    with app.app_context():
        steps = db.session.scalars(select(IssueTransition.to_state).order_by(IssueTransition.created_at)).all()
        assert steps == ["DRAFT", "SUBMITTED"]
        assert db.session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "CIVIC_ISSUE_CREATED")) == 1


def test_validation_and_scope_rejections(app, people):
    rahul = as_user(app, "rahul")
    assert post(rahul, "/api/civic/issues", {}).status_code == 400
    far = post(rahul, "/api/civic/issues", issue_body(latitude=28.6139, longitude=77.2090))
    assert far.status_code == 400 and "outside the area" in far.json["error"]["fields"]["latitude"]
    assert post(rahul, "/api/civic/issues", issue_body(latitude=91, longitude=85.8)).status_code == 400
    assert post(rahul, "/api/civic/issues", issue_body(latitude=True)).status_code == 400
    assert post(rahul, "/api/civic/issues", issue_body(category="PARTY")).status_code == 400
    assert post(rahul, "/api/civic/issues", issue_body(unknown="x")).status_code == 400
    markup = post(rahul, "/api/civic/issues", issue_body(description="<script>alert(1)</script> on the road outside"))
    assert markup.status_code == 400 and "description" in markup.json["error"]["fields"]
    contact = post(rahul, "/api/civic/issues", issue_body(description="Call me on 98765 43210 about the pothole here"))
    assert "description" in contact.json["error"]["fields"]
    email = post(rahul, "/api/civic/issues", issue_body(description="Mail me at someone@example.com about this pothole"))
    assert "description" in email.json["error"]["fields"]
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(CivicIssue)) == 0


def test_draft_edit_and_submit(app, people):
    rahul = as_user(app, "rahul")
    draft = post(rahul, "/api/civic/issues", issue_body(save_as_draft=True)).json["issue"]
    assert draft["state"] == "DRAFT"
    priya = as_user(app, "priya")
    assert priya.get(f"/api/civic/issues/{draft['id']}").status_code == 404
    listed = [item["id"] for item in priya.get("/api/civic/issues").json["issues"]]
    assert draft["id"] not in listed
    edited = send(rahul, "PATCH", f"/api/civic/issues/{draft['id']}", {"title": "Pothole by the main gate road"})
    assert edited.status_code == 200 and edited.json["issue"]["title"] == "Pothole by the main gate road"
    moved = send(rahul, "PATCH", f"/api/civic/issues/{draft['id']}", {"latitude": 28.6, "longitude": 77.2})
    assert moved.status_code == 400
    assert send(priya, "PATCH", f"/api/civic/issues/{draft['id']}", {"title": "Hijacked title here"}).status_code == 404
    submitted = post(rahul, f"/api/civic/issues/{draft['id']}/submit")
    assert submitted.status_code == 200 and submitted.json["issue"]["state"] == "SUBMITTED"
    assert post(rahul, f"/api/civic/issues/{draft['id']}/submit").status_code == 409
    assert send(rahul, "PATCH", f"/api/civic/issues/{draft['id']}", {"title": "Edited after submission"}).status_code == 409


def test_withdraw_keeps_history(app, people):
    rahul = as_user(app, "rahul")
    issue_id = create(rahul)
    assert send(rahul, "DELETE", f"/api/civic/issues/{issue_id}").json["issue"]["state"] == "WITHDRAWN"
    assert as_user(app, "priya").get(f"/api/civic/issues/{issue_id}").status_code == 404
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(CivicIssue)) == 1
        assert db.session.scalar(select(func.count()).select_from(IssueTransition)) == 3
    assert post(rahul, f"/api/civic/issues/{issue_id}/submit").status_code == 409


# ------------------------------------------------------------------ discovery and duplicates

def test_list_filters_and_privacy(app, people):
    rahul, priya = as_user(app, "rahul"), as_user(app, "priya")
    create(rahul)
    create(rahul, title="Streetlight is dead on park lane", category="STREETLIGHT",
           latitude=20.2980, longitude=85.8220, severity="LOW")
    everything = priya.get("/api/civic/issues").json
    assert everything["total"] == 2
    only_lights = priya.get("/api/civic/issues?category=STREETLIGHT").json["issues"]
    assert [item["category"] for item in only_lights] == ["STREETLIGHT"]
    near_gate = priya.get("/api/civic/issues?near_lat=20.2964&near_lon=85.8248&radius_m=100").json["issues"]
    assert [item["category"] for item in near_gate] == ["ROAD_DAMAGE"]
    assert priya.get("/api/civic/issues?category=BOGUS").status_code == 400
    assert priya.get("/api/civic/issues?limit=0").status_code == 400
    # Reporter is anonymous to others by default and no contact details are ever exposed.
    shown = priya.get("/api/civic/issues").json["issues"][0]
    assert shown["reporter_display_name"] == "A resident" and shown["viewer_is_reporter"] is False
    raw = priya.get("/api/civic/issues").get_data(as_text=True)
    assert "rahul@example.test" not in raw and "9876543210" not in raw
    mine = rahul.get("/api/civic/issues?mine=true").json["issues"]
    assert len(mine) == 2 and mine[0]["reporter_display_name"] == "Rahul"


def test_public_name_privacy_option(app, people):
    issue_id = create(as_user(app, "rahul"), privacy="PUBLIC_NAME")
    assert as_user(app, "priya").get(f"/api/civic/issues/{issue_id}").json["issue"]["reporter_display_name"] == "Rahul"


def test_similar_requires_nearby_same_category(app, people):
    rahul, priya = as_user(app, "rahul"), as_user(app, "priya")
    first = create(rahul)
    near = priya.get("/api/civic/issues/similar?category=ROAD_DAMAGE&lat=20.29645&lon=85.82485"
                     "&title=Deep pothole outside main gate")
    assert near.status_code == 200
    found = near.json["similar"]
    assert [item["id"] for item in found] == [first]
    assert found[0]["match"]["distance_m"] < 20 and found[0]["match"]["title_similarity"] > 0.3
    # Near-identical text far away must not match; neither must another category nearby.
    far = priya.get("/api/civic/issues/similar?category=ROAD_DAMAGE&lat=20.3100&lon=85.8400&title=Deep pothole outside the main gate")
    assert far.json["similar"] == []
    other = priya.get("/api/civic/issues/similar?category=STREETLIGHT&lat=20.2964&lon=85.8248")
    assert other.json["similar"] == []
    assert priya.get("/api/civic/issues/similar?category=ROAD_DAMAGE").status_code == 400
    # Creating a second report returns the first as a suggestion but does not merge anything.
    second = post(priya, "/api/civic/issues", issue_body(latitude=20.29646, longitude=85.82486))
    assert [item["id"] for item in second.json["similar"]] == [first]
    assert second.json["issue"]["canonical_issue_id"] is None


def test_similar_ignores_closed_issues(app, people):
    rahul = as_user(app, "rahul")
    issue_id = create(rahul)
    send(rahul, "DELETE", f"/api/civic/issues/{issue_id}")
    result = as_user(app, "priya").get("/api/civic/issues/similar?category=ROAD_DAMAGE&lat=20.2964&lon=85.8248")
    assert result.json["similar"] == []


# ------------------------------------------------------------------ support

def test_support_requires_validation_and_is_unique(app, people):
    rahul, priya, amit = as_user(app, "rahul"), as_user(app, "priya"), as_user(app, "amit")
    issue_id = create(rahul)
    early = support(priya, issue_id)
    assert early.status_code == 409 and early.json["error"]["code"] == "NOT_OPEN_FOR_SUPPORT"
    validate(as_user(app, "admin"), issue_id)
    first = support(priya, issue_id)
    assert first.status_code == 201 and first.json["support_count"] == 1 and first.json["viewer_has_supported"]
    # The same account from a second session is rejected; the count does not move.
    second_session = as_user(app, "priya")
    again = support(second_session, issue_id)
    assert again.status_code == 409 and again.json["error"]["code"] == "ALREADY_SUPPORTED"
    assert support(rahul, issue_id).json["error"]["code"] == "OWN_ISSUE"
    assert support(amit, issue_id).json["support_count"] == 2
    assert priya.get(f"/api/civic/issues/{issue_id}").json["issue"]["support_count"] == 2
    withdrawn = send(priya, "DELETE", f"/api/civic/issues/{issue_id}/support")
    assert withdrawn.status_code == 200 and withdrawn.json["support_count"] == 1
    assert send(priya, "DELETE", f"/api/civic/issues/{issue_id}/support").status_code == 404
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(IssueSupport)) == 1


def test_database_blocks_duplicate_support_rows(app, people):
    issue_id = validated_issue(app)
    support(as_user(app, "priya"), issue_id)
    from sqlalchemy.exc import IntegrityError
    with app.app_context():
        existing = db.session.scalar(select(IssueSupport))
        db.session.add(IssueSupport(issue_id=existing.issue_id, user_id=existing.user_id))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ------------------------------------------------------------------ moderation lifecycle

def test_lifecycle_guards(app, people):
    admin, rahul = as_user(app, "admin"), as_user(app, "rahul")
    issue_id = create(rahul)
    assert post(admin, f"/api/civic/admin/issues/{issue_id}/review").json["issue"]["state"] == "UNDER_REVIEW"
    assert post(admin, f"/api/civic/admin/issues/{issue_id}/review").status_code == 409
    short = post(admin, f"/api/civic/admin/issues/{issue_id}/reject", {"reason": "no"})
    assert short.status_code == 400
    rejected = post(admin, f"/api/civic/admin/issues/{issue_id}/reject", {"reason": "This is not a public issue."})
    assert rejected.json["issue"]["state"] == "REJECTED"
    # Terminal: cannot be validated, edited, withdrawn or supported afterwards.
    assert post(admin, f"/api/civic/admin/issues/{issue_id}/validate", {}).status_code == 409
    assert send(rahul, "DELETE", f"/api/civic/issues/{issue_id}").status_code == 409
    assert support(as_user(app, "priya"), issue_id).status_code == 404
    assert post(admin, "/api/civic/admin/issues/00000000-0000-0000-0000-000000000000/validate", {}).status_code == 404


def test_needs_info_roundtrip_and_reporter_timeline(app, people):
    admin, rahul, priya = as_user(app, "admin"), as_user(app, "rahul"), as_user(app, "priya")
    issue_id = create(rahul)
    asked = post(admin, f"/api/civic/admin/issues/{issue_id}/needs-info", {"reason": "Please add a clearer landmark."})
    assert asked.json["issue"]["state"] == "NEEDS_INFO"
    assert priya.get(f"/api/civic/issues/{issue_id}").status_code == 404
    assert send(rahul, "PATCH", f"/api/civic/issues/{issue_id}", {"address_hint": "Next to the bus stop"}).status_code == 200
    assert post(rahul, f"/api/civic/issues/{issue_id}/submit", {"note": "Added the landmark."}).json["issue"]["state"] == "SUBMITTED"
    validate(admin, issue_id, note="Looks genuine.")
    timeline = rahul.get(f"/api/civic/issues/{issue_id}/timeline").json
    states = [event["to_state"] for event in timeline["events"]]
    assert states == ["DRAFT", "SUBMITTED", "NEEDS_INFO", "SUBMITTED", "VALIDATED"]
    assert any("clearer landmark" in event["reason"] for event in timeline["events"])
    # Other residents only see community-visible steps and never the reasons.
    other = priya.get(f"/api/civic/issues/{issue_id}/timeline").json
    assert [event["to_state"] for event in other["events"]] == ["SUBMITTED", "VALIDATED"]
    assert all(event["reason"] == "" for event in other["events"])


def test_validate_can_adjust_severity_and_snapshots_priority(app, people):
    admin = as_user(app, "admin")
    issue_id = create(as_user(app, "rahul"), severity="LOW")
    result = validate(admin, issue_id, severity="CRITICAL")
    assert result["severity"] == "CRITICAL"
    with app.app_context():
        snapshot = db.session.scalar(select(PrioritySnapshot))
        assert snapshot.trigger == "VALIDATED" and snapshot.inputs["severity_points"] == 20


def test_moderation_queue(app, people):
    admin = as_user(app, "admin")
    first = create(as_user(app, "rahul"))
    queue = admin.get("/api/civic/admin/issues").json
    assert [item["id"] for item in queue["issues"]] == [first]
    assert queue["issues"][0]["reporter_user_id"]
    assert admin.get("/api/civic/admin/issues?state=BOGUS").status_code == 400


# ------------------------------------------------------------------ duplicates and merge

def make_pair(app):
    rahul, maya, admin = as_user(app, "rahul"), as_user(app, "maya"), as_user(app, "admin")
    canonical = create(rahul)
    duplicate = create(maya, title="Pothole near the main gate road", latitude=20.29646, longitude=85.82486)
    validate(admin, canonical)
    return admin, canonical, duplicate


def test_merge_combines_support_without_double_counting(app, people):
    admin, canonical, duplicate = make_pair(app)
    priya, amit = as_user(app, "priya"), as_user(app, "amit")
    support(priya, canonical)
    validate(admin, duplicate)
    support(priya, duplicate)  # same resident supported both reports
    support(amit, duplicate)
    merged = post(admin, f"/api/civic/admin/issues/{duplicate}/merge",
                  {"canonical_issue_id": canonical, "reason": "Same pothole outside the gate."})
    assert merged.status_code == 200
    assert merged.json["duplicate"]["state"] == "MERGED"
    # priya (once), amit, and maya (reporter of the duplicate) = 3 distinct identities.
    assert merged.json["canonical"]["support_count"] == 3
    # Reporter of the duplicate is pointed to the canonical issue and keeps the submitted history.
    maya = as_user(app, "maya")
    own = maya.get(f"/api/civic/issues/{duplicate}").json["issue"]
    assert own["state"] == "MERGED" and own["canonical_issue_id"] == canonical
    assert maya.get(f"/api/civic/issues/{canonical}").json["issue"]["viewer_has_supported"] is True
    reasons = [e["reason"] for e in maya.get(f"/api/civic/issues/{duplicate}/timeline").json["events"]]
    assert any(canonical in reason for reason in reasons)
    blocked = support(as_user(app, "sneha"), duplicate)
    assert blocked.status_code == 409 and blocked.json["error"]["code"] == "ISSUE_MERGED"
    assert support(maya, canonical).json["error"]["code"] == "ALREADY_SUPPORTED"
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(DuplicateLink)) == 1
        assert db.session.scalar(select(func.count()).select_from(IssueSupport)) == 3  # nothing deleted


def test_merge_rules(app, people):
    rahul, admin = as_user(app, "rahul"), as_user(app, "admin")
    canonical = create(rahul)
    far = create(as_user(app, "priya"), title="Deep pothole outside the main gate", latitude=20.2990, longitude=85.8290)
    other_category = create(as_user(app, "amit"), category="STREETLIGHT")
    url = f"/api/civic/admin/issues/{far}/merge"
    body = {"canonical_issue_id": canonical, "reason": "Looks like the same pothole."}
    blocked = post(admin, url, body)
    assert blocked.status_code == 422 and blocked.json["error"]["code"] == "LOCATIONS_TOO_FAR"
    assert post(admin, f"/api/civic/admin/issues/{other_category}/merge", body).json["error"]["code"] == "CATEGORY_MISMATCH"
    assert post(admin, url, {**body, "canonical_issue_id": far}).status_code == 400
    assert post(rahul, url, body).status_code == 403
    allowed = post(admin, url, {**body, "acknowledge_distance": True})
    assert allowed.status_code == 200 and allowed.json["duplicate"]["state"] == "MERGED"
    assert post(admin, url, {**body, "acknowledge_distance": True}).status_code == 409  # already merged
    # A merged issue is not a valid target.
    third = create(as_user(app, "sneha"), latitude=20.29641, longitude=85.82481)
    assert post(admin, f"/api/civic/admin/issues/{third}/merge", {**body, "canonical_issue_id": far}).json["error"]["code"] == "INVALID_CANONICAL"


def test_merging_a_canonical_repoints_its_duplicates(app, people):
    admin = as_user(app, "admin")
    first = create(as_user(app, "rahul"))
    second = create(as_user(app, "priya"), latitude=20.29641, longitude=85.82481)
    third = create(as_user(app, "amit"), latitude=20.29642, longitude=85.82482)
    reason = {"reason": "Same pothole at the gate."}
    assert post(admin, f"/api/civic/admin/issues/{third}/merge", {"canonical_issue_id": second, **reason}).status_code == 200
    assert post(admin, f"/api/civic/admin/issues/{second}/merge", {"canonical_issue_id": first, **reason}).status_code == 200
    with app.app_context():
        links = db.session.scalars(select(DuplicateLink)).all()
        assert {str(link.canonical_issue_id) for link in links} == {first}
        assert len(links) == 2


# ------------------------------------------------------------------ evidence

def test_evidence_privacy_and_validation(app, people):
    rahul, priya, admin = as_user(app, "rahul"), as_user(app, "priya"), as_user(app, "admin")
    issue_id = create(rahul)
    stored = upload(rahul, issue_id)
    assert stored.status_code == 201 and stored.json["evidence"]["visibility"] == "PRIVATE"
    evidence_id = stored.json["evidence"]["id"]
    assert rahul.get(f"/api/civic/evidence/{evidence_id}/file").status_code == 200
    assert admin.get(f"/api/civic/evidence/{evidence_id}/file").status_code == 200
    validate(admin, issue_id)
    # Private by default: another resident neither sees nor downloads it.
    assert priya.get(f"/api/civic/evidence/{evidence_id}/file").status_code == 404
    assert priya.get(f"/api/civic/issues/{issue_id}").json["issue"]["evidence_count"] == 0
    assert rahul.get(f"/api/civic/issues/{issue_id}").json["issue"]["evidence_count"] == 1
    shared = post(admin, f"/api/civic/admin/evidence/{evidence_id}/visibility", {"visibility": "RESIDENTS"})
    assert shared.status_code == 200
    assert priya.get(f"/api/civic/evidence/{evidence_id}/file").status_code == 200
    assert priya.get(f"/api/civic/issues/{issue_id}").json["issue"]["evidence_count"] == 1
    assert upload(priya, issue_id).status_code == 404  # only the reporter adds evidence


def test_evidence_rejects_bad_files_and_enforces_limit(app, people):
    rahul = as_user(app, "rahul")
    issue_id = create(rahul)
    assert upload(rahul, issue_id, name="notes.pdf").status_code == 400
    assert upload(rahul, issue_id, name="fake.png", data=io.BytesIO(b"not an image")).status_code == 400
    assert upload(rahul, issue_id, visibility="PUBLIC").status_code == 400
    assert rahul.post(f"/api/civic/issues/{issue_id}/evidence", data={}, content_type="multipart/form-data",
                      headers={"X-CSRF-Token": csrf(rahul)}).status_code == 400
    for _ in range(5):
        assert upload(rahul, issue_id).status_code == 201
    assert upload(rahul, issue_id).json["error"]["code"] == "EVIDENCE_LIMIT_REACHED"
    first = rahul.get(f"/api/civic/issues/{issue_id}").json["issue"]["evidence"][0]["id"]
    assert send(rahul, "DELETE", f"/api/civic/issues/{issue_id}/evidence/{first}").status_code == 200
    assert upload(rahul, issue_id).status_code == 201


# ------------------------------------------------------------------ abuse reports

def test_abuse_report_redaction_keeps_audit_trail(app, people):
    rahul, priya, admin = as_user(app, "rahul"), as_user(app, "priya"), as_user(app, "admin")
    issue_id = create(rahul)
    assert post(rahul, f"/api/civic/issues/{issue_id}/report",
                {"concern_type": "ABUSIVE", "concern": "Reporting myself here."}).json["error"]["code"] == "OWN_ISSUE"
    raised = post(priya, f"/api/civic/issues/{issue_id}/report",
                  {"concern_type": "PERSONAL_INFO", "concern": "Shows a neighbour's house number clearly."})
    assert raised.status_code == 201
    again = post(priya, f"/api/civic/issues/{issue_id}/report",
                 {"concern_type": "ABUSIVE", "concern": "Reporting a second time again."})
    assert again.status_code == 409
    assert priya.get("/api/civic/admin/reports").status_code == 403
    queue = admin.get("/api/civic/admin/reports").json["reports"]
    assert len(queue) == 1
    resolved = post(admin, f"/api/civic/admin/reports/{queue[0]['id']}/resolve",
                    {"disposition": "REDACTED", "note": "Removed the identifying text."})
    assert resolved.status_code == 200 and resolved.json["report"]["status"] == "RESOLVED"
    assert "Removed by a coordinator" in priya.get(f"/api/civic/issues/{issue_id}").json["issue"]["description"]
    assert post(admin, f"/api/civic/admin/reports/{queue[0]['id']}/resolve",
                {"disposition": "DISMISSED", "note": "Already handled."}).status_code == 409
    with app.app_context():
        report = db.session.scalar(select(IssueModerationReport))
        assert "pothole" in report.original_description  # original retained for moderators only
        assert db.session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "CIVIC_REPORT_RESOLVED")) == 1


def test_abuse_report_can_request_correction_or_remove(app, people):
    admin, priya = as_user(app, "admin"), as_user(app, "priya")
    first, second = create(as_user(app, "rahul")), create(as_user(app, "amit"), latitude=20.2990, longitude=85.8260)
    for issue_id, disposition, expected in ((first, "CORRECTION_REQUESTED", "NEEDS_INFO"), (second, "REMOVED", "REJECTED")):
        post(priya, f"/api/civic/issues/{issue_id}/report", {"concern_type": "FALSE_INFO", "concern": "This looks inaccurate."})
    for report in admin.get("/api/civic/admin/reports").json["reports"]:
        disposition = "CORRECTION_REQUESTED" if report["issue_id"] == first else "REMOVED"
        assert post(admin, f"/api/civic/admin/reports/{report['id']}/resolve",
                    {"disposition": disposition, "note": "Moderator decision."}).status_code == 200
    assert admin.get(f"/api/civic/admin/issues?state=NEEDS_INFO").json["total"] == 1
    assert admin.get(f"/api/civic/admin/issues?state=REJECTED").json["total"] == 1


# ------------------------------------------------------------------ priority

def test_priority_is_transparent(app, people):
    issue_id = validated_issue(app)
    for name in ("priya", "amit"):
        support(as_user(app, name), issue_id)
    shown = as_user(app, "sneha").get(f"/api/civic/issues/{issue_id}").json["issue"]["priority"]
    assert shown["inputs"]["supporters"] == 2 and shown["inputs"]["supporter_points"] == 4
    assert shown["inputs"]["severity"] == "HIGH" and shown["inputs"]["severity_points"] == 10
    assert shown["score"] == pytest.approx(14.0, abs=0.1) and shown["band"] == "LOW"
    assert "does not guarantee" in shown["disclaimer"] and "supporters" in shown["formula"]


def test_priority_caps_and_bands(app, people):
    class Stub:
        severity = type("S", (), {"value": "CRITICAL"})()
        submitted_at = None
        created_at = datetime.now(timezone.utc) - timedelta(days=90)

    stub = Stub()
    stub.severity = __import__("app.modules.civic.models", fromlist=["IssueSeverity"]).IssueSeverity.CRITICAL
    result = priority.compute(stub, 500)
    assert result["inputs"]["supporter_points"] == 40 and result["inputs"]["age_points"] == 15.0
    assert result["score"] == 75.0 and result["band"] == "HIGH"
    listed = priority.compute(stub, 0, now=stub.created_at)
    assert listed["score"] == 20.0 and listed["band"] == "MEDIUM"


def test_list_sort_by_support(app, people):
    low = validated_issue(app, title="Garbage heap near the lane end", category="GARBAGE",
                          latitude=20.2990, longitude=85.8200)
    high = validated_issue(app, reporter="priya")
    for name in ("amit", "sneha"):
        support(as_user(app, name), high)
    support(as_user(app, "amit"), low)
    ordered = [item["id"] for item in as_user(app, "maya").get("/api/civic/issues?sort=support").json["issues"]]
    assert ordered == [high, low]
    assert as_user(app, "maya").get("/api/civic/issues?sort=popular").status_code == 400


# ------------------------------------------------------------------ routing and hand-off

def ready_issue(app):
    issue_id = validated_issue(app)
    rahul = as_user(app, "rahul")
    assert upload(rahul, issue_id).status_code == 201
    return issue_id


def test_route_requires_readiness_and_moderator(app, people):
    admin, rahul = as_user(app, "admin"), as_user(app, "rahul")
    issue_id = ready_issue(app)
    assert post(rahul, f"/api/civic/issues/{issue_id}/route").status_code == 403
    blocked = post(admin, f"/api/civic/issues/{issue_id}/route")
    assert blocked.status_code == 409 and blocked.json["error"]["code"] == "NOT_READY_FOR_ROUTING"
    assert "supporter" in str(blocked.json["error"]["fields"]) or "support" in str(blocked.json["error"]["fields"])
    detail = rahul.get(f"/api/civic/issues/{issue_id}").json["issue"]
    assert detail["readiness"]["required_supporters"] == 3 and len(detail["readiness"]["unmet"]) == 1
    with app.app_context():
        assert db.session.scalar(select(func.count()).select_from(IssueHandoff)) == 0


def test_route_needs_evidence(app, people):
    admin = as_user(app, "admin")
    issue_id = validated_issue(app)
    for name in ("priya", "amit", "sneha"):
        support(as_user(app, name), issue_id)
    blocked = post(admin, f"/api/civic/issues/{issue_id}/route")
    assert blocked.status_code == 409 and "photo" in str(blocked.json["error"]["fields"])


def test_route_builds_traceable_payload_and_follows_case(app, people):
    admin, rahul = as_user(app, "admin"), as_user(app, "rahul")
    issue_id = ready_issue(app)
    for name in ("priya", "amit", "sneha"):
        support(as_user(app, name), issue_id)
    routed = post(admin, f"/api/civic/issues/{issue_id}/route")
    assert routed.status_code == 201, routed.json
    payload = routed.json["handoff"]["payload"]
    assert payload["canonical_issue_id"] == issue_id and payload["category"] == "ROAD_DAMAGE"
    assert payload["community_support"] == 3 and len(payload["evidence"]) == 1
    assert payload["location"]["latitude"] == pytest.approx(20.2964) and payload["demonstration_data"] is True
    assert "rahul@example.test" not in str(payload) and "9876543210" not in str(payload)
    assert routed.json["issue"]["state"] == "READY_FOR_ROUTING"
    assert post(admin, f"/api/civic/issues/{issue_id}/route").json["error"]["code"] == "ALREADY_ROUTED"
    # Reporter follows the same issue; no second issue is created.
    seen = rahul.get(f"/api/civic/issues/{issue_id}").json["issue"]
    assert seen["state"] == "READY_FOR_ROUTING" and seen["handoff"]["routing_status"] == "PENDING_INTAKE"
    assert seen["authoritative_status"] is None
    # Withdrawing support after routing is blocked so the payload stays accurate.
    assert send(as_user(app, "priya"), "DELETE", f"/api/civic/issues/{issue_id}/support").status_code == 409
    ack = post(admin, f"/api/civic/issues/{issue_id}/handoff/acknowledge", {"authority_case_id": "DEMO-CASE-0001"})
    assert ack.status_code == 200 and ack.json["handoff"]["routing_status"] == "ACKNOWLEDGED"
    assert post(admin, f"/api/civic/issues/{issue_id}/handoff/acknowledge",
                {"authority_case_id": "DEMO-CASE-0001"}).status_code == 200
    clash = post(admin, f"/api/civic/issues/{issue_id}/handoff/acknowledge", {"authority_case_id": "DEMO-CASE-0002"})
    assert clash.status_code == 409
    seen = rahul.get(f"/api/civic/issues/{issue_id}").json["issue"]
    assert seen["handoff"]["authority_case_id"] == "DEMO-CASE-0001"
    timeline = rahul.get(f"/api/civic/issues/{issue_id}/timeline").json
    assert [e["type"] for e in timeline["events"]][-2:] == ["ROUTED", "AUTHORITY_ACKNOWLEDGED"]
    assert send(rahul, "DELETE", f"/api/civic/issues/{issue_id}").status_code == 409
    with app.app_context():
        assert db.session.scalar(select(PrioritySnapshot.trigger).where(PrioritySnapshot.trigger == "ROUTED")) == "ROUTED"


def test_acknowledge_before_routing_is_not_found(app, people):
    issue_id = validated_issue(app)
    result = post(as_user(app, "admin"), f"/api/civic/issues/{issue_id}/handoff/acknowledge", {"authority_case_id": "DEMO-1"})
    assert result.status_code == 404


def test_authority_status_is_read_from_module_6_when_available(app, people, monkeypatch):
    import sys
    import types
    stub = types.ModuleType("app.modules.authority.public")
    stub.case_status_for_issue = lambda issue_id: {"status": "IN_PROGRESS", "department": "Demo Roads Dept (simulated)"}
    package = types.ModuleType("app.modules.authority")
    package.__path__ = []
    monkeypatch.setitem(sys.modules, "app.modules.authority", package)
    monkeypatch.setitem(sys.modules, "app.modules.authority.public", stub)
    issue_id = validated_issue(app)
    shown = as_user(app, "rahul").get(f"/api/civic/issues/{issue_id}").json["issue"]
    assert shown["authoritative_status"]["status"] == "IN_PROGRESS"


# ------------------------------------------------------------------ unavailable schema

def test_missing_locality_is_reported(app, people):
    with app.app_context():
        db.session.execute(CivicLocality.__table__.update().values(is_active=False))
        db.session.commit()
    result = as_user(app, "rahul").get("/api/civic/issues")
    assert result.status_code == 503 and result.json["error"]["code"] == "LOCALITY_NOT_CONFIGURED"
