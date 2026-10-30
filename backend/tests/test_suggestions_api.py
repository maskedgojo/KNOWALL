"""Suggestion API tests. In-memory schema only; does not migrate the project database."""
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

PASSWORD = "SuggestionStrongPass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "suggestion-test-secret-key",
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
            ("resident", PermissionRole.RESIDENT, True),
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


def payload(**overrides):
    body = {
        "title": "Lobby lighting",
        "description": "The ground-floor lobby lights stay off after 7 pm.",
        "category": "MAINTENANCE",
    }
    body.update(overrides)
    return body


def test_anonymous_suggestion_reads_and_writes(client):
    assert client.get("/api/suggestions").status_code == 401
    assert client.post("/api/suggestions", json=payload()).status_code == 403
    assert post(client, "/api/suggestions", payload()).status_code == 401


def test_membership_is_required_and_privileged_fields_are_rejected(client, app, people):
    login(client, "admin@example.test")
    assert client.get("/api/suggestions").status_code == 403
    logout(client)
    login(client, "applicant@example.test")
    assert post(client, "/api/suggestions", payload()).status_code == 403
    logout(client)
    login(client, "resident@example.test")
    rejected = post(client, "/api/suggestions", payload(status="APPROVED", society_id=1))
    assert rejected.status_code == 400
    assert set(rejected.json["error"]["fields"]) == {"status", "society_id"}
    with app.app_context():
        db.session.delete(db.session.get(SocietyProfile, 1))
        db.session.commit()
    missing = post(client, "/api/suggestions", payload())
    assert missing.status_code == 404
    assert missing.json["error"]["code"] == "SOCIETY_NOT_CONFIGURED"


def test_resident_submits_lists_and_reads_without_a_decision_route(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/suggestions", payload())
    assert created.status_code == 201, created.json
    suggestion = created.json["suggestion"]
    assert suggestion["status"] == "SUBMITTED"
    assert suggestion["society_id"] == 1
    assert suggestion["author_display_name"] == "Resident"
    assert suggestion["category"] == "MAINTENANCE"
    listed = client.get("/api/suggestions")
    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "no-store"
    assert [row["id"] for row in listed.json["suggestions"]] == [suggestion["id"]]
    detail = client.get(f"/api/suggestions/{suggestion['id']}")
    assert detail.status_code == 200
    assert detail.json["suggestion"]["description"].startswith("The ground-floor")
    assert client.get("/api/suggestions/00000000-0000-4000-8000-000000000099").status_code == 404
    assert client.patch(
        f"/api/suggestions/{suggestion['id']}",
        json={"status": "APPROVED"},
        headers={"X-CSRF-Token": csrf(client)},
    ).status_code == 405
    invalid = post(client, "/api/suggestions", payload(title="No", category="URGENT"))
    assert invalid.status_code == 400
    assert set(invalid.json["error"]["fields"]) == {"title", "category"}
    with app.app_context():
        entry = db.session.scalar(select(AuditLog).where(AuditLog.action == "SUGGESTION_CREATED"))
        assert entry.entity_type == "SUGGESTION"
        assert entry.details == {"title": "Lobby lighting", "category": "MAINTENANCE", "status": "SUBMITTED"}
        assert "description" not in entry.details
