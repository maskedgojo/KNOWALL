"""Phase 6 integration tests (cookie sessions + CSRF, SQLite test DB).

No tests bypass Flask's real route, login, permission, or CSRF checks.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
import re

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, ApplicationStatus, AuditLog, Flat, Household, Invitation,
    Membership, MembershipApplication, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, Tower, User,
)

PASSWORD = "ValidPasswordForTests2026!"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True, "SECRET_KEY": "phase6-test-secret-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False, "MAIL_DELIVERY_MODE": "memory",
        "RECOVERY_IP_LIMIT": 1000,
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


def post(client, path, body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf(client)})


def patch(client, path, body):
    return client.patch(path, json=body, headers={"X-CSRF-Token": csrf(client)})


def login(client, email):
    response = post(client, "/api/auth/login", {"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.json


@pytest.fixture()
def sample(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        b402 = Flat(tower=tower, flat_number="402", floor_number=4)
        b403 = Flat(tower=tower, flat_number="403", floor_number=4)
        db.session.add_all([b402, b403])
        db.session.flush()
        home = Household(flat=b402, label="Owner family")
        other = Household(flat=b403, label="Other household")
        db.session.add_all([home, other])
        db.session.flush()
        verified_at = datetime.now(timezone.utc)
        persons = [
            ("owner", "owner@example.test", PermissionRole.RESIDENT, verified_at),
            ("admin", "admin@example.test", PermissionRole.SOCIETY_ADMIN, verified_at),
            ("applicant", "new@example.test", PermissionRole.APPLICANT, verified_at),
            ("unverified", "unverified@example.test", PermissionRole.APPLICANT, None),
            ("outsider", "outsider@example.test", PermissionRole.APPLICANT, verified_at),
        ]
        users = {}
        for key, email, role, verified in persons:
            user = User(display_name=key.title(), email=email,
                        password_hash=generate_password_hash(PASSWORD),
                        account_status=AccountStatus.ACTIVE, email_verified_at=verified)
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user=user, role=role))
            users[key] = user
        membership = Membership(
            user=users["owner"], household=home, category=ResidentCategory.OWNER,
            status=MembershipStatus.ACTIVE, valid_from=date.today() - timedelta(days=3),
        )
        db.session.add(membership)
        db.session.commit()
        return {"flat": str(b402.id), "other_flat": str(b403.id),
                "home": str(home.id), "other_home": str(other.id),
                "sponsor": str(membership.id), "admin": str(users["admin"].id)}


def latest_token(app):
    messages = app.extensions["knowall_outbox"]
    match = re.search(r"token=([A-Za-z0-9_-]+)", messages[-1]["body"])
    assert match is not None
    return match.group(1)


def create_owner(client, sample):
    return post(client, "/api/membership/applications", {
        "flat_id": sample["flat"], "category": "OWNER", "applicant_notes": "New resident",
    })


def test_unauthenticated_routes_rejected(client, sample):
    assert client.get("/api/membership/applications/me").status_code == 401
    assert client.get("/api/invitations/me").status_code == 401
    assert post(client, "/api/membership/applications", {"flat_id": sample["flat"], "category": "OWNER"}).status_code == 401


def test_draft_create_update_submit_and_history(client, app, sample):
    login(client, "new@example.test")
    create = create_owner(client, sample)
    assert create.status_code == 201, create.json
    row = create.json["application"]
    assert row["status"] == "DRAFT" and row["evidence_required"] is True
    application_id = row["id"]
    edited = patch(client, f"/api/membership/applications/{application_id}", {
        "applicant_notes": "Corrected draft", "flat_id": sample["other_flat"],
    })
    assert edited.status_code == 200, edited.json
    assert edited.json["application"]["flat"]["id"] == sample["other_flat"]
    submitted = post(client, f"/api/membership/applications/{application_id}/submit", {})
    assert submitted.status_code == 200, submitted.json
    assert submitted.json["application"]["status"] == "PENDING"
    assert patch(client, f"/api/membership/applications/{application_id}", {"applicant_notes": "oops"}).status_code == 409
    rows = client.get("/api/membership/applications/me").json["applications"]
    assert len(rows) == 1 and rows[0]["id"] == application_id
    assert client.get("/api/me/access").json["verified_resident"] is False
    with app.app_context():
        assert db.session.scalar(select(MembershipApplication).where(MembershipApplication.id == row_uuid(application_id))).status == ApplicationStatus.PENDING
        assert db.session.scalars(select(AuditLog).where(AuditLog.action == "APPLICATION_SUBMITTED")).first() is not None


def row_uuid(raw):
    from uuid import UUID
    return UUID(raw)


def test_unverified_account_can_draft_but_cannot_submit(client, sample):
    login(client, "unverified@example.test")
    draft = create_owner(client, sample)
    assert draft.status_code == 201
    assert post(client, f"/api/membership/applications/{draft.json['application']['id']}/submit", {}).status_code == 403


def test_duplicate_open_application_and_existing_membership(client, sample):
    login(client, "new@example.test")
    assert create_owner(client, sample).status_code == 201
    again = create_owner(client, sample)
    assert again.status_code == 409
    login(client, "owner@example.test")
    already = create_owner(client, sample)
    assert already.status_code == 409


def test_applications_private_to_owner(client, sample):
    login(client, "new@example.test")
    row = create_owner(client, sample).json["application"]
    login(client, "outsider@example.test")
    assert client.get(f"/api/membership/applications/{row['id']}").status_code == 404
    assert patch(client, f"/api/membership/applications/{row['id']}", {"applicant_notes": "stolen"}).status_code == 404
    assert post(client, f"/api/membership/applications/{row['id']}/submit", {}).status_code == 404


def test_family_self_application_forbidden(client, sample):
    login(client, "new@example.test")
    result = post(client, "/api/membership/applications", {"flat_id": sample["flat"], "category": "FAMILY_MEMBER"})
    assert result.status_code == 403
    assert result.json["error"]["code"] == "INVITATION_REQUIRED"


def test_tenant_dates_and_bad_dates(client, sample):
    login(client, "new@example.test")
    wrong = post(client, "/api/membership/applications", {
        "flat_id": sample["flat"], "category": "TENANT", "requested_valid_from": "2027-10-01", "requested_valid_until": "2027-09-01",
    })
    assert wrong.status_code == 400
    valid = post(client, "/api/membership/applications", {
        "flat_id": sample["flat"], "category": "TENANT", "requested_valid_from": "2027-09-01", "requested_valid_until": "2027-10-01",
    })
    assert valid.status_code == 201
    assert valid.json["application"]["requested_valid_until"] == "2027-10-01"


def test_create_family_invite_auto_activates_once(client, app, sample):
    login(client, "owner@example.test")
    invited = post(client, "/api/invitations", {
        "flat_id": sample["flat"], "household_id": sample["home"],
        "sponsor_membership_id": sample["sponsor"],
        "category": "FAMILY_MEMBER", "email": "new@example.test",
    })
    assert invited.status_code == 201, invited.json
    raw = latest_token(app)
    assert "token" not in invited.json["invitation"]
    recipient = app.test_client()
    login(recipient, "new@example.test")
    accepted = post(recipient, "/api/invitations/accept", {"token": raw, "relationship_to_sponsor": "CHILD"})
    assert accepted.status_code == 201, accepted.json
    assert accepted.json["outcome"] == "FAMILY_MEMBERSHIP_ACTIVATED"
    assert accepted.json["application"] is None
    assert accepted.json["membership"]["category"] == "FAMILY_MEMBER"
    assert accepted.json["membership"]["sponsor_membership_id"] == sample["sponsor"]
    assert post(recipient, "/api/invitations/accept", {"token": raw, "relationship_to_sponsor": "CHILD"}).status_code in (400, 409)
    assert recipient.get("/api/me/access").json["verified_resident"] is True
    assert len(recipient.get("/api/invitations/me").json["invitations"]) == 1


def test_wrong_email_does_not_consume_invitation(client, app, sample):
    login(client, "owner@example.test")
    assert post(client, "/api/invitations", {
        "flat_id": sample["flat"], "household_id": sample["home"],
        "sponsor_membership_id": sample["sponsor"],
        "category": "FAMILY_MEMBER", "email": "new@example.test",
    }).status_code == 201
    raw = latest_token(app)
    wrong = app.test_client()
    login(wrong, "outsider@example.test")
    assert post(wrong, "/api/invitations/accept", {"token": raw}).status_code == 403
    recipient = app.test_client()
    login(recipient, "new@example.test")
    assert post(recipient, "/api/invitations/accept", {"token": raw, "relationship_to_sponsor": "SPOUSE"}).status_code == 201


def test_suspended_sponsor_blocks_accept(client, app, sample):
    login(client, "owner@example.test")
    assert post(client, "/api/invitations", {
        "flat_id": sample["flat"], "household_id": sample["home"],
        "sponsor_membership_id": sample["sponsor"],
        "category": "FAMILY_MEMBER", "email": "new@example.test",
    }).status_code == 201
    raw = latest_token(app)
    with app.app_context():
        membership = db.session.get(Membership, row_uuid(sample["sponsor"]))
        membership.status = MembershipStatus.SUSPENDED
        db.session.commit()
    recipient = app.test_client()
    login(recipient, "new@example.test")
    assert post(recipient, "/api/invitations/accept", {"token": raw}).status_code == 409


def test_nonadmin_cannot_invite_tenant_or_wrong_household(client, sample):
    login(client, "owner@example.test")
    denied = post(client, "/api/invitations", {
        "flat_id": sample["flat"], "category": "TENANT", "email": "new@example.test",
    })
    assert denied.status_code == 403
    bad = post(client, "/api/invitations", {
        "flat_id": sample["other_flat"], "category": "FAMILY_MEMBER",
        "household_id": sample["other_home"], "sponsor_membership_id": sample["sponsor"],
        "email": "new@example.test",
    })
    assert bad.status_code == 403


def test_admin_can_invite_tenant_and_accept(client, app, sample):
    login(client, "admin@example.test")
    invitation = post(client, "/api/invitations", {
        "flat_id": sample["flat"], "category": "TENANT", "email": "new@example.test",
    })
    assert invitation.status_code == 201, invitation.json
    raw = latest_token(app)
    target = app.test_client()
    login(target, "new@example.test")
    accept = post(target, "/api/invitations/accept", {"token": raw})
    assert accept.status_code == 201, accept.json
    assert accept.json["application"]["category"] == "TENANT"
    assert post(target, f"/api/membership/applications/{accept.json['application']['id']}/submit", {}).status_code == 200


def test_expired_invite_rejected(client, app, sample):
    login(client, "admin@example.test")
    assert post(client, "/api/invitations", {
        "flat_id": sample["flat"], "category": "OWNER", "email": "new@example.test",
    }).status_code == 201
    raw = latest_token(app)
    with app.app_context():
        row = db.session.scalar(select(Invitation))
        row.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.session.commit()
    target = app.test_client()
    login(target, "new@example.test")
    assert post(target, "/api/invitations/accept", {"token": raw}).status_code == 400


def test_unverified_invitee_cannot_accept(client, app, sample):
    login(client, "admin@example.test")
    assert post(client, "/api/invitations", {
        "flat_id": sample["flat"], "category": "OWNER", "email": "unverified@example.test",
    }).status_code == 201
    raw = latest_token(app)
    target = app.test_client()
    login(target, "unverified@example.test")
    assert post(target, "/api/invitations/accept", {"token": raw}).status_code == 403


def test_invite_requires_csrf(client, sample):
    login(client, "admin@example.test")
    no_csrf = client.post("/api/invitations", json={
        "flat_id": sample["flat"], "category": "OWNER", "email": "new@example.test",
    })
    assert no_csrf.status_code == 403


def test_correction_reupload_ready_state(client, app, sample):
    login(client, "new@example.test")
    row = create_owner(client, sample).json["application"]
    application_id = row_uuid(row["id"])
    assert post(client, f"/api/membership/applications/{application_id}/submit", {}).status_code == 200
    # Phase 8 will expose the authorized admin decision endpoint; simulate its database outcome.
    with app.app_context():
        application = db.session.get(MembershipApplication, application_id)
        application.status = ApplicationStatus.NEEDS_CORRECTION
        db.session.commit()
    response = patch(client, f"/api/membership/applications/{application_id}", {
        "applicant_notes": "Corrected application details",
    })
    assert response.status_code == 200
    again = post(client, f"/api/membership/applications/{application_id}/submit", {})
    assert again.status_code == 200 and again.json["application"]["status"] == "PENDING"
