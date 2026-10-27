"""Polls, private disputes, proposals, and missing-table responses. In-memory schema only."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select, text
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)

PASSWORD = "ExtendedModule2Pass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "extended-module2-secret",
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
            ("neighbor", PermissionRole.RESIDENT, True),
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


def window(hours=2):
    opens = datetime.now(timezone.utc) + timedelta(minutes=1)
    return opens.isoformat(), (opens + timedelta(hours=hours)).isoformat()


def test_missing_discussion_table_is_not_a_not_found(client, app, people):
    login(client, "resident@example.test")
    with app.app_context():
        db.session.execute(text("DROP TABLE discussion_comments"))
        db.session.execute(text("DROP TABLE discussions"))
        db.session.commit()
    missing = client.get("/api/discussions")
    assert missing.status_code == 503
    assert missing.json["error"]["code"] == "SCHEMA_NOT_READY"
    assert "not found" not in missing.json["error"]["message"].lower()


def test_informal_poll_hides_counts_until_close_and_allows_one_response(client, app, people):
    login(client, "resident@example.test")
    opens, closes = window()
    created = post(client, "/api/polls", {
        "question": "Saturday garden work?",
        "options": ["Morning", "Afternoon"],
        "opens_at": opens,
        "closes_at": closes,
        "society_id": 1,
    })
    assert created.status_code == 400
    created = post(client, "/api/polls", {
        "question": "Saturday garden work?",
        "options": ["Morning", "Afternoon"],
        "opens_at": datetime.now(timezone.utc).isoformat(),
        "closes_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    })
    assert created.status_code == 201, created.json
    poll = created.json["poll"]
    assert poll["binding"] is False
    assert poll["status"] == "OPEN"
    assert all(option["vote_count"] is None for option in poll["options"])
    option_id = poll["options"][0]["id"]
    voted = post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id})
    assert voted.status_code == 201, voted.json
    assert "user_id" not in voted.json
    again = post(client, f"/api/polls/{poll['id']}/votes", {"option_id": poll["options"][1]["id"]})
    assert again.status_code == 409
    assert again.json["error"]["code"] == "ALREADY_VOTED"
    logout(client)
    login(client, "neighbor@example.test")
    other = post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id})
    assert other.status_code == 201
    visible = client.get(f"/api/polls/{poll['id']}").json["poll"]
    assert all(option["vote_count"] is None for option in visible["options"])
    assert "resident@" not in client.get(f"/api/polls/{poll['id']}").get_data(as_text=True)
    with app.app_context():
        from app.modules.polls.models import Poll
        stored = db.session.get(Poll, UUID(poll["id"]))
        stored.opens_at = datetime.now(timezone.utc) - timedelta(hours=2)
        stored.closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    closed = client.get(f"/api/polls/{poll['id']}")
    assert closed.json["poll"]["status"] == "CLOSED"
    assert sum(option["vote_count"] for option in closed.json["poll"]["options"]) == 2
    assert post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id}).status_code == 409


def test_dispute_is_private_and_absent_from_governance_history(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/disputes", {
        "title": "Parking dispute",
        "description": "A private account of the parking conflict.",
        "status": "CLOSED",
    })
    assert created.status_code == 400
    created = post(client, "/api/disputes", {
        "title": "Parking dispute",
        "description": "A private account of the parking conflict.",
    })
    assert created.status_code == 201, created.json
    dispute_id = created.json["dispute"]["id"]
    assert created.json["dispute"]["status"] == "SUBMITTED"
    assert client.patch(
        f"/api/disputes/{dispute_id}", json={"status": "CLOSED"}, headers={"X-CSRF-Token": csrf(client)}
    ).status_code == 405
    logout(client)
    login(client, "neighbor@example.test")
    assert client.get("/api/disputes").json["disputes"] == []
    hidden = client.get(f"/api/disputes/{dispute_id}")
    assert hidden.status_code == 404
    history = client.get("/api/governance/history").get_data(as_text=True)
    assert "private account of the parking" not in history
    assert "Parking dispute" not in history
    with app.app_context():
        entry = db.session.scalar(select(AuditLog).where(AuditLog.action == "DISPUTE_SUBMITTED"))
        assert "description" not in entry.details


def test_proposal_cannot_accept_a_ballot(client, app, people):
    login(client, "admin@example.test")
    assert client.get("/api/proposals").status_code == 403
    logout(client)
    login(client, "resident@example.test")
    rejected = post(client, "/api/proposals", {"title": "Repaint the lobby", "summary": "Use the approved pale grey.", "status": "PASSED"})
    assert rejected.status_code == 400
    created = post(client, "/api/proposals", {"title": "Repaint the lobby", "summary": "Use the approved pale grey."})
    assert created.status_code == 201, created.json
    proposal = created.json["proposal"]
    assert proposal["voting_open"] is False
    assert proposal["status"] == "SUBMITTED"
    assert client.post(
        f"/api/proposals/{proposal['id']}/votes",
        json={"choice": "yes"},
        headers={"X-CSRF-Token": csrf(client)},
    ).status_code == 404
    with app.app_context():
        entry = db.session.scalar(select(AuditLog).where(AuditLog.action == "PROPOSAL_SUBMITTED"))
        assert entry.details == {"title": "Repaint the lobby", "status": "SUBMITTED", "voting_open": False}
        assert "summary" not in entry.details
