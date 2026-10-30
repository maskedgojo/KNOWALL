"""Governance history tests. In-memory schema only; does not migrate the project database."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)

PASSWORD = "HistoryStrongPass!123"
PUBLIC_ACTIONS = {
    "NOTICE_PUBLISHED", "NOTICE_ARCHIVED", "DISCUSSION_CREATED", "COMMENT_CREATED", "SUGGESTION_CREATED",
}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "governance-history-test-secret",
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


def notice(client, title):
    created = post(client, "/api/admin/notices", {
        "title": title, "body": "Supply stops at noon.", "expires_at": None,
    })
    assert created.status_code == 201, created.json
    return created.json["notice"]["id"]


def test_history_requires_an_eligible_resident(client, people):
    assert client.get("/api/governance/history").status_code == 401
    login(client, "admin@example.test")
    assert client.get("/api/governance/history").status_code == 403
    logout(client)
    login(client, "applicant@example.test")
    assert client.get("/api/governance/history").status_code == 403


def test_history_lists_only_public_society_events_in_stable_order(client, app, people):
    login(client, "admin@example.test")
    live_id = notice(client, "Water shutdown")
    assert post(client, f"/api/admin/notices/{live_id}/publish", {}).status_code == 200
    hidden_id = notice(client, "Hidden draft title")
    assert post(client, f"/api/admin/notices/{hidden_id}/archive", {}).status_code == 200
    archived_id = notice(client, "Archived announcement")
    assert post(client, f"/api/admin/notices/{archived_id}/publish", {}).status_code == 200
    assert post(client, f"/api/admin/notices/{archived_id}/archive", {}).status_code == 200
    logout(client)

    login(client, "resident@example.test")
    discussion = post(client, "/api/discussions", {"title": "Gate hours", "body": "When does it close?"})
    assert discussion.status_code == 201, discussion.json
    discussion_id = discussion.json["discussion"]["id"]
    assert post(client, f"/api/discussions/{discussion_id}/comments", {
        "body": "It closes at 9 pm.", "parent_comment_id": None,
    }).status_code == 201
    suggestion = post(client, "/api/suggestions", {
        "title": "Lobby lighting",
        "description": "The lobby lights stay off after 7 pm.",
        "category": "MAINTENANCE",
    })
    assert suggestion.status_code == 201, suggestion.json

    with app.app_context():
        db.session.add(AuditLog(
            action="PASSWORD_RESET", entity_type="USER", entity_id=uuid4(),
            details={"token": "reset-token-value", "email": "hidden@example.test"},
        ))
        db.session.add(AuditLog(
            action="NOTICE_PUBLISHED", entity_type="NOTICE", entity_id=uuid4(),
            details={"title": "Other society notice", "token": "ballot-secret"},
        ))
        db.session.commit()
        visible = list(db.session.scalars(
            select(AuditLog).where(AuditLog.action.in_(PUBLIC_ACTIONS)).order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        ))
        known_ids = {live_id, archived_id, discussion_id, suggestion.json["suggestion"]["id"]}
        visible = [row for row in visible if row.entity_id and str(row.entity_id) in known_ids]
        visible = [row for row in visible if not (
            row.action == "NOTICE_ARCHIVED" and str(row.entity_id) == hidden_id
        )]
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        for index, row in enumerate(visible):
            row.created_at = start + timedelta(minutes=index)
        db.session.commit()
        expected_ids = [str(row.id) for row in reversed(visible)]

    listed = client.get("/api/governance/history?limit=10&offset=0")
    assert listed.status_code == 200, listed.json
    assert listed.headers["Cache-Control"] == "no-store"
    assert [event["id"] for event in listed.json["events"]] == expected_ids
    payload = listed.get_data(as_text=True)
    for secret in ("reset-token-value", "hidden@example.test", "ballot-secret", "Hidden draft title", "Supply stops", "lobby lights"):
        assert secret not in payload
    by_type = {event["event_type"]: event for event in listed.json["events"] if event["event_type"] != "NOTICE_PUBLISHED"}
    published = [event for event in listed.json["events"] if event["event_type"] == "NOTICE_PUBLISHED"]
    assert any(event["resource_path"] == f"/notices/{live_id}" for event in published)
    assert all(event["resource_path"] != f"/notices/{archived_id}" for event in listed.json["events"])
    assert by_type["DISCUSSION_CREATED"]["resource_path"] == f"/discussions/{discussion_id}"
    assert by_type["SUGGESTION_CREATED"]["summary"] == 'Suggestion submitted: "Lobby lighting" (Maintenance).'
    assert set(listed.json["events"][0]) == {"id", "occurred_at", "event_type", "summary", "resource_path"}
    page = client.get("/api/governance/history?limit=1&offset=1")
    assert [event["id"] for event in page.json["events"]] == expected_ids[1:2]
    assert client.get("/api/governance/history?limit=0").status_code == 400
