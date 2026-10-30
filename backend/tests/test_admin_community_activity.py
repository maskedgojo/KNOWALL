"""Society Admin read-only community activity."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)
from app.modules.polls.models import Poll

PASSWORD = "CommunityActivityPass!123"
FORBIDDEN_KEYS = {"created_by_user_id", "user_id", "my_option_id", "actor_user_id", "voter_user_id", "details"}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "community-activity-secret",
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


def test_society_admin_can_review_public_activity_without_private_fields(client, app, people):
    assert client.get("/api/admin/community/discussions").status_code == 401
    login(client, "resident@example.test")
    assert client.get("/api/admin/community/discussions").status_code == 403
    discussion = post(client, "/api/discussions", {"title": "Gate hours", "body": "The side gate closes at 9."})
    assert discussion.status_code == 201, discussion.json
    discussion_id = discussion.json["discussion"]["id"]
    comment = post(client, f"/api/discussions/{discussion_id}/comments", {
        "body": "Thanks for confirming.", "parent_comment_id": None,
    })
    assert comment.status_code == 201, comment.json
    reply = post(client, f"/api/discussions/{discussion_id}/comments", {
        "body": "The reply stays in the thread.", "parent_comment_id": comment.json["comment"]["id"],
    })
    assert reply.status_code == 201, reply.json
    suggestion = post(client, "/api/suggestions", {
        "title": "Lobby lighting", "description": "Lights stay off after 7 pm.", "category": "MAINTENANCE",
    })
    assert suggestion.status_code == 201, suggestion.json
    poll = post(client, "/api/polls", {
        "question": "Saturday garden work?",
        "options": ["Morning", "Afternoon"],
        "opens_at": datetime.now(timezone.utc).isoformat(),
        "closes_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
    })
    assert poll.status_code == 201, poll.json
    poll_id = poll.json["poll"]["id"]
    option_id = poll.json["poll"]["options"][0]["id"]
    assert post(client, f"/api/polls/{poll_id}/votes", {"option_id": option_id}).status_code == 201
    dispute = post(client, "/api/disputes", {
        "title": "Parking dispute", "description": "Private parking narrative.",
    })
    assert dispute.status_code == 201, dispute.json
    proposal = post(client, "/api/proposals", {"title": "Repaint the lobby", "summary": "Use pale grey."})
    assert proposal.status_code == 201, proposal.json
    logout(client)

    login(client, "platform@example.test")
    assert client.get("/api/admin/community/polls").status_code == 403
    logout(client)

    login(client, "admin@example.test")
    assert post(client, "/api/admin/community/discussions", {}).status_code == 405
    assert client.get("/api/admin/community/disputes").status_code == 404
    listed = client.get("/api/admin/community/discussions?limit=30&offset=0")
    assert listed.status_code == 200, listed.json
    assert "discussions" in listed.json
    suggestion_list = client.get("/api/admin/community/suggestions?limit=30&offset=0")
    assert suggestion_list.status_code == 200, suggestion_list.json
    assert suggestion_list.json["suggestions"][0]["title"] == "Lobby lighting"
    poll_list = client.get("/api/admin/community/polls?limit=30&offset=0")
    assert poll_list.status_code == 200, poll_list.json
    assert poll_list.json["polls"][0]["question"] == "Saturday garden work?"
    assert all(option["vote_count"] is None for option in poll_list.json["polls"][0]["options"])
    proposal_list = client.get("/api/admin/community/proposals?limit=30&offset=0")
    assert proposal_list.status_code == 200, proposal_list.json
    assert proposal_list.json["proposals"][0]["title"] == "Repaint the lobby"
    detail = client.get(f"/api/admin/community/discussions/{discussion_id}")
    assert detail.status_code == 200, detail.json
    assert detail.json["discussion"]["comment_count"] == 2
    assert {comment["body"] for comment in detail.json["comments"]} == {
        "Thanks for confirming.", "The reply stays in the thread.",
    }
    suggestions = client.get("/api/admin/community/suggestions")
    assert suggestions.json["suggestions"][0]["status"] == "SUBMITTED"
    assert "decision" not in suggestions.json["suggestions"][0]
    open_poll = client.get(f"/api/admin/community/polls/{poll_id}")
    assert open_poll.status_code == 200, open_poll.json
    assert open_poll.json["poll"]["status"] == "OPEN"
    assert open_poll.json["poll"]["binding"] is False
    assert all(option["vote_count"] is None for option in open_poll.json["poll"]["options"])
    proposals = client.get("/api/admin/community/proposals")
    assert proposals.json["proposals"][0]["voting_open"] is False
    assert "tally" not in proposals.json["proposals"][0]
    combined = " ".join(response.get_data(as_text=True) for response in (listed, detail, suggestions, open_poll, proposals))
    assert "Private parking narrative" not in combined
    assert "Parking dispute" not in combined
    assert people["resident"] not in combined
    found = set()
    for response in (listed, detail, suggestions, open_poll, proposals):
        walk_keys(response.json, found)
    assert FORBIDDEN_KEYS.isdisjoint(found)

    with app.app_context():
        stored = db.session.get(Poll, UUID(poll_id))
        stored.opens_at = datetime.now(timezone.utc) - timedelta(hours=2)
        stored.closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    closed = client.get(f"/api/admin/community/polls/{poll_id}")
    counts = {option["label"]: option["vote_count"] for option in closed.json["poll"]["options"]}
    assert counts == {"Morning": 1, "Afternoon": 0}
    closed_text = closed.get_data(as_text=True)
    assert people["resident"] not in closed_text
    closed_keys = set()
    walk_keys(closed.json, closed_keys)
    assert FORBIDDEN_KEYS.isdisjoint(closed_keys)
