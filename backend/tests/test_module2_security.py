"""Security checks for polls, disputes, proposals, and governance history."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)
from app.modules.polls.models import Poll, PollOption, PollVote

PASSWORD = "Module2SecurityPass!123"
SAFE_EVENT_KEYS = {"id", "occurred_at", "event_type", "summary", "resource_path"}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "module2-security-secret",
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
        other_home = Household(flat=flat, label="Neighbor household")
        db.session.add_all([home, other_home])
        db.session.flush()
        ids = {}
        for name, role, member, household in (
            ("admin", PermissionRole.SOCIETY_ADMIN, False, None),
            ("resident", PermissionRole.RESIDENT, True, home),
            ("neighbor", PermissionRole.RESIDENT, True, other_home),
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
                    user=user, household=household, category=ResidentCategory.OWNER,
                    status=MembershipStatus.ACTIVE,
                    valid_from=datetime.now(timezone.utc).date() - timedelta(days=2),
                ))
            ids[name] = user.id
        db.session.commit()
        return {name: str(value) for name, value in ids.items()}


def open_poll(client):
    created = post(client, "/api/polls", {
        "question": "Saturday garden work?",
        "options": ["Morning", "Afternoon"],
        "opens_at": datetime.now(timezone.utc).isoformat(),
        "closes_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    })
    assert created.status_code == 201, created.json
    return created.json["poll"]


def test_poll_window_duplicate_constraint_and_hidden_identities(client, app, people):
    assert client.post("/api/polls", json={"question": "Too soon", "options": ["A", "B"]}).status_code == 403
    login(client, "resident@example.test")
    later = datetime.now(timezone.utc) + timedelta(hours=3)
    scheduled = post(client, "/api/polls", {
        "question": "Future garden day?",
        "options": ["Yes", "No"],
        "opens_at": later.isoformat(),
        "closes_at": (later + timedelta(hours=1)).isoformat(),
    })
    assert scheduled.status_code == 201, scheduled.json
    early = post(client, f"/api/polls/{scheduled.json['poll']['id']}/votes", {
        "option_id": scheduled.json["poll"]["options"][0]["id"], "user_id": people["neighbor"],
    })
    assert early.status_code == 400
    assert early.json["error"]["fields"]["user_id"] == "Unknown field."
    poll = open_poll(client)
    option_id = poll["options"][0]["id"]
    assert post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id}).status_code == 201
    assert post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id}).status_code == 409
    logout(client)
    login(client, "neighbor@example.test")
    assert post(client, f"/api/polls/{poll['id']}/votes", {"option_id": poll["options"][1]["id"]}).status_code == 201
    logout(client)
    login(client, "resident@example.test")
    visible = client.get(f"/api/polls/{poll['id']}").get_data(as_text=True)
    assert people["neighbor"] not in visible
    assert "Morning" in visible
    assert '"vote_count": null' in visible or '"vote_count":null' in visible
    with app.app_context():
        stored = db.session.get(Poll, UUID(poll["id"]))
        option = db.session.scalars(select(PollOption).where(PollOption.poll_id == stored.id)).first()
        db.session.add(PollVote(
            poll_id=stored.id, option_id=option.id, user_id=UUID(people["neighbor"]),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        stored = db.session.get(Poll, UUID(poll["id"]))
        stored.opens_at = datetime.now(timezone.utc) - timedelta(hours=2)
        stored.closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.add(AuditLog(
            actor_user_id=UUID(people["neighbor"]), action="POLL_RESPONSE", entity_type="POLL",
            entity_id=stored.id,
            details={"voter_user_id": people["neighbor"], "choice": "Afternoon", "token": "poll-secret"},
        ))
        db.session.commit()
    closed = client.get(f"/api/polls/{poll['id']}")
    assert closed.json["poll"]["status"] == "CLOSED"
    assert closed.json["poll"]["binding"] is False
    assert post(client, f"/api/polls/{poll['id']}/votes", {"option_id": option_id}).status_code == 409
    history = client.get("/api/governance/history")
    body = history.get_data(as_text=True)
    assert "poll-secret" not in body
    assert people["neighbor"] not in body
    assert "Afternoon" not in body
    assert all(set(event) == SAFE_EVENT_KEYS for event in history.json["events"])


def test_dispute_ownership_and_history_privacy(client, app, people):
    login(client, "resident@example.test")
    forged = post(client, "/api/disputes", {
        "title": "Parking dispute",
        "description": "Private parking narrative.",
        "created_by_user_id": people["neighbor"],
        "society_id": 1,
        "status": "CLOSED",
    })
    assert forged.status_code == 400
    assert set(forged.json["error"]["fields"]) == {"created_by_user_id", "society_id", "status"}
    created = post(client, "/api/disputes", {
        "title": "Parking dispute", "description": "Private parking narrative.",
    })
    assert created.status_code == 201, created.json
    dispute_id = created.json["dispute"]["id"]
    logout(client)
    login(client, "neighbor@example.test")
    assert client.get("/api/disputes").json["disputes"] == []
    missing = client.get(f"/api/disputes/{dispute_id}")
    assert missing.status_code == 404
    guessed = client.get(f"/api/disputes/{uuid4()}")
    assert guessed.status_code == 404
    history = client.get("/api/governance/history").get_data(as_text=True)
    assert "Private parking narrative" not in history
    assert "Parking dispute" not in history
    assert client.patch(
        f"/api/disputes/{dispute_id}", json={"status": "CLOSED"}, headers={"X-CSRF-Token": csrf(client)}
    ).status_code == 405


def test_suggestions_discussions_and_proposals_reject_forged_privileged_fields(client, app, people):
    login(client, "resident@example.test")
    suggestion = post(client, "/api/suggestions", {
        "title": "Lobby lighting",
        "description": "Lights stay off after 7 pm.",
        "category": "MAINTENANCE",
        "status": "APPROVED",
        "society_id": 1,
        "created_by_user_id": people["admin"],
    })
    assert suggestion.status_code == 400
    created = post(client, "/api/suggestions", {
        "title": "Lobby lighting", "description": "Lights stay off after 7 pm.", "category": "MAINTENANCE",
    })
    assert created.status_code == 201, created.json
    discussion = post(client, "/api/discussions", {
        "title": "Gate hours", "body": "The side gate closes at 9.", "society_id": 2,
    })
    assert discussion.status_code == 400
    posted = post(client, "/api/discussions", {"title": "Gate hours", "body": "The side gate closes at 9."})
    assert posted.status_code == 201, posted.json
    comment = post(client, f"/api/discussions/{posted.json['discussion']['id']}/comments", {
        "body": "Thanks for confirming.", "parent_comment_id": None, "created_by_user_id": people["neighbor"],
    })
    assert comment.status_code == 400
    assert post(client, f"/api/discussions/{posted.json['discussion']['id']}/comments", {
        "body": "Thanks for confirming.", "parent_comment_id": None,
    }).status_code == 201
    proposal = post(client, "/api/proposals", {
        "title": "Repaint the lobby", "summary": "Use pale grey.", "status": "PASSED", "voting_open": True,
    })
    assert proposal.status_code == 400
    saved = post(client, "/api/proposals", {"title": "Repaint the lobby", "summary": "Use pale grey."})
    assert saved.status_code == 201, saved.json
    assert saved.json["proposal"]["voting_open"] is False
    assert "tally" not in saved.json["proposal"]
    assert client.post(
        f"/api/proposals/{saved.json['proposal']['id']}/votes",
        json={"choice": "yes"}, headers={"X-CSRF-Token": csrf(client)},
    ).status_code == 404
    with app.app_context():
        suggestion_audit = db.session.scalar(select(AuditLog).where(AuditLog.action == "SUGGESTION_CREATED"))
        suggestion_audit.details = {
            "title": "Lobby lighting", "category": "MAINTENANCE", "status": "SUBMITTED",
            "description": "Lights stay off after 7 pm.", "email": "resident@example.test",
        }
        comment_audit = db.session.scalar(select(AuditLog).where(AuditLog.action == "COMMENT_CREATED"))
        comment_audit.details = {
            "comment_id": "hidden", "body": "Thanks for confirming.", "token": "comment-secret",
        }
        db.session.commit()
    history = client.get("/api/governance/history").get_data(as_text=True)
    for secret in ("Lights stay off after 7 pm.", "resident@example.test", "Thanks for confirming.", "comment-secret"):
        assert secret not in history
    assert "Repaint the lobby" in history
    assert '"voting_open": true' not in history.lower()
