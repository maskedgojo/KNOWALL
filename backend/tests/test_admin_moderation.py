"""Society Admin actions: hide discussions, decide proposals, handle private disputes."""
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

PASSWORD = "AdminModerationPass!123"
FORBIDDEN_KEYS = {"created_by_user_id", "user_id", "actor_user_id", "details", "hidden_by_user_id",
                  "decided_by_user_id", "handled_by_user_id"}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "admin-moderation-secret",
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
    assert post(client, "/api/auth/login", {"email": email, "password": PASSWORD}).status_code == 200


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
        ids = {}
        for name, role, member in (
            ("admin", PermissionRole.SOCIETY_ADMIN, False),
            ("platform", PermissionRole.PLATFORM_ADMIN, False),
            ("resident", PermissionRole.RESIDENT, True),
            ("neighbour", PermissionRole.RESIDENT, True),
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
            ids[name] = user.id
        db.session.commit()
        return {name: str(value) for name, value in ids.items()}


def history_text(client) -> str:
    response = client.get("/api/governance/history")
    assert response.status_code == 200, response.json
    return response.get_data(as_text=True)


def test_admin_hides_and_restores_a_discussion(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/discussions", {"title": "Rude post", "body": "Offensive text."})
    discussion_id = created.json["discussion"]["id"]
    assert post(client, f"/api/admin/community/discussions/{discussion_id}/hide", {"reason": "Abusive"}).status_code == 403
    logout(client)

    login(client, "platform@example.test")
    assert post(client, f"/api/admin/community/discussions/{discussion_id}/hide", {"reason": "Abusive"}).status_code == 403
    logout(client)

    login(client, "admin@example.test")
    assert post(client, f"/api/admin/community/discussions/{discussion_id}/hide", {"reason": "x"}).status_code == 400
    hidden = post(client, f"/api/admin/community/discussions/{discussion_id}/hide", {"reason": "Abusive language"})
    assert hidden.status_code == 200, hidden.json
    assert hidden.json["discussion"]["hidden"] is True
    assert hidden.json["discussion"]["hidden_reason"] == "Abusive language"
    assert hidden.json["discussion"]["hidden_by_display_name"] == "Admin"
    assert post(client, f"/api/admin/community/discussions/{discussion_id}/hide", {"reason": "Again"}).status_code == 409
    listed = client.get("/api/admin/community/discussions")
    assert listed.json["discussions"][0]["hidden"] is True
    found = set()
    walk_keys(listed.json, found)
    assert FORBIDDEN_KEYS.isdisjoint(found)
    logout(client)

    login(client, "neighbour@example.test")
    assert client.get("/api/discussions").json["discussions"] == []
    assert client.get(f"/api/discussions/{discussion_id}").status_code == 404
    assert post(client, f"/api/discussions/{discussion_id}/comments", {"body": "Hi", "parent_comment_id": None}).status_code == 404
    assert "Rude post" not in history_text(client)
    logout(client)

    login(client, "admin@example.test")
    restored = post(client, f"/api/admin/community/discussions/{discussion_id}/restore", {})
    assert restored.status_code == 200, restored.json
    assert restored.json["discussion"]["hidden"] is False
    assert post(client, f"/api/admin/community/discussions/{discussion_id}/restore", {}).status_code == 409
    logout(client)

    login(client, "neighbour@example.test")
    assert client.get(f"/api/discussions/{discussion_id}").status_code == 200
    with app.app_context():
        actions = [row.action for row in db.session.scalars(select(AuditLog).where(AuditLog.entity_type == "DISCUSSION"))]
    assert "DISCUSSION_HIDDEN" in actions and "DISCUSSION_RESTORED" in actions


def test_admin_records_one_proposal_decision(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/proposals", {"title": "Repaint the lobby", "summary": "Use pale grey."})
    proposal_id = created.json["proposal"]["id"]
    assert created.json["proposal"]["decided_at"] is None
    assert post(client, f"/api/admin/community/proposals/{proposal_id}/decision", {"decision": "APPROVED"}).status_code == 403
    logout(client)

    login(client, "admin@example.test")
    url = f"/api/admin/community/proposals/{proposal_id}/decision"
    assert post(client, url, {"decision": "MAYBE"}).status_code == 400
    assert post(client, url, {"decision": "APPROVED", "tally": 3}).status_code == 400
    decided = post(client, url, {"decision": "APPROVED", "note": "Budgeted for March."})
    assert decided.status_code == 200, decided.json
    assert decided.json["proposal"]["status"] == "APPROVED"
    assert decided.json["proposal"]["voting_open"] is False
    assert decided.json["proposal"]["decided_by_display_name"] == "Admin"
    again = post(client, url, {"decision": "REJECTED"})
    assert again.status_code == 409
    assert again.json["error"]["code"] == "PROPOSAL_ALREADY_DECIDED"
    logout(client)

    login(client, "neighbour@example.test")
    seen = client.get(f"/api/proposals/{proposal_id}").json["proposal"]
    assert seen["status"] == "APPROVED"
    assert seen["decision_note"] == "Budgeted for March."
    assert "Society Admin approved proposal" in history_text(client)


def test_admin_handles_private_dispute(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/disputes", {"title": "Parking dispute", "description": "Private parking narrative."})
    dispute_id = created.json["dispute"]["id"]
    assert client.get("/api/admin/disputes").status_code == 403
    assert post(client, f"/api/admin/disputes/{dispute_id}/status", {"status": "RESOLVED", "response": "Done"}).status_code == 403
    logout(client)

    login(client, "neighbour@example.test")
    assert client.get(f"/api/disputes/{dispute_id}").status_code == 404
    logout(client)

    login(client, "platform@example.test")
    assert client.get("/api/admin/disputes").status_code == 403
    logout(client)

    login(client, "admin@example.test")
    listed = client.get("/api/admin/disputes")
    assert listed.status_code == 200, listed.json
    row = listed.json["disputes"][0]
    assert row["title"] == "Parking dispute"
    assert row["author_display_name"] == "Resident"
    assert people["resident"] not in listed.get_data(as_text=True)
    found = set()
    walk_keys(listed.json, found)
    assert FORBIDDEN_KEYS.isdisjoint(found)
    assert client.get("/api/admin/disputes?status=CLOSED").status_code == 400
    assert client.get("/api/admin/disputes?status=RESOLVED").json["disputes"] == []
    assert client.get(f"/api/admin/disputes/{dispute_id}").status_code == 200

    url = f"/api/admin/disputes/{dispute_id}/status"
    assert post(client, url, {"status": "SUBMITTED"}).status_code == 400
    missing_response = post(client, url, {"status": "RESOLVED"})
    assert missing_response.status_code == 400
    assert "response" in missing_response.json["error"]["fields"]
    review = post(client, url, {"status": "IN_REVIEW"})
    assert review.status_code == 200, review.json
    assert review.json["dispute"]["status"] == "IN_REVIEW"
    assert post(client, url, {"status": "IN_REVIEW"}).status_code == 409
    resolved = post(client, url, {"status": "RESOLVED", "response": "Spot B-12 is reassigned to you."})
    assert resolved.status_code == 200, resolved.json
    assert resolved.json["dispute"]["handled_by_display_name"] == "Admin"
    reopened = post(client, url, {"status": "IN_REVIEW"})
    assert reopened.status_code == 200
    assert reopened.json["dispute"]["admin_response"] == "Spot B-12 is reassigned to you."
    logout(client)

    login(client, "resident@example.test")
    mine = client.get(f"/api/disputes/{dispute_id}").json["dispute"]
    assert mine["status"] == "IN_REVIEW"
    assert mine["admin_response"] == "Spot B-12 is reassigned to you."
    changed = client.patch(f"/api/disputes/{dispute_id}", json={"status": "RESOLVED"}, headers={"X-CSRF-Token": csrf(client)})
    assert changed.status_code == 405
    assert "Parking dispute" not in history_text(client)
    with app.app_context():
        entry = db.session.scalars(select(AuditLog).where(AuditLog.action == "DISPUTE_STATUS_CHANGED")).first()
        assert entry.details == {"from": "SUBMITTED", "to": "IN_REVIEW"}
