"""Discussion API tests. In-memory schema only; does not migrate the project database."""
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

PASSWORD = "DiscussionStrongPass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "discussion-test-secret-key",
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
            ("committee", PermissionRole.COMMITTEE_MEMBER, True),
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


def test_anonymous_discussion_reads_and_writes(client):
    assert client.get("/api/discussions").status_code == 401
    assert client.post("/api/discussions", json={"title": "Gate hours", "body": "When does it close?"}).status_code == 403
    assert post(client, "/api/discussions", {"title": "Gate hours", "body": "When does it close?"}).status_code == 401


def test_membership_is_required_and_society_id_is_rejected(client, app, people):
    login(client, "admin@example.test")
    assert client.get("/api/discussions").status_code == 403
    logout(client)
    login(client, "applicant@example.test")
    assert post(client, "/api/discussions", {"title": "Gate hours", "body": "When does it close?"}).status_code == 403
    logout(client)
    login(client, "resident@example.test")
    rejected = post(client, "/api/discussions", {
        "title": "Gate hours", "body": "When does it close?", "society_id": 1,
    })
    assert rejected.status_code == 400
    assert rejected.json["error"]["fields"]["society_id"] == "Unknown field."
    with app.app_context():
        db.session.delete(db.session.get(SocietyProfile, 1))
        db.session.commit()
    missing = post(client, "/api/discussions", {"title": "Gate hours", "body": "When does it close?"})
    assert missing.status_code == 404
    assert missing.json["error"]["code"] == "SOCIETY_NOT_CONFIGURED"


def test_resident_creates_lists_and_audits_without_storing_body(client, app, people):
    login(client, "resident@example.test")
    created = post(client, "/api/discussions", {"title": "Gate hours", "body": "When does the side gate close?"})
    assert created.status_code == 201, created.json
    discussion = created.json["discussion"]
    assert discussion["society_id"] == 1
    assert discussion["author_display_name"] == "Resident"
    assert discussion["comment_count"] == 0
    listed = client.get("/api/discussions")
    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "no-store"
    assert [row["id"] for row in listed.json["discussions"]] == [discussion["id"]]
    with app.app_context():
        entry = db.session.scalar(select(AuditLog).where(AuditLog.action == "DISCUSSION_CREATED"))
        assert entry.entity_type == "DISCUSSION"
        assert entry.details == {"title": "Gate hours"}
        assert "body" not in entry.details


def test_comments_stay_inside_one_discussion(client, people):
    login(client, "resident@example.test")
    first = post(client, "/api/discussions", {"title": "Gate hours", "body": "When does the side gate close?"}).json["discussion"]["id"]
    second = post(client, "/api/discussions", {"title": "Garden day", "body": "Saturday morning works for me."}).json["discussion"]["id"]
    parent = post(client, f"/api/discussions/{first}/comments", {"body": "It closes at 9 pm.", "parent_comment_id": None})
    assert parent.status_code == 201, parent.json
    parent_id = parent.json["comment"]["id"]
    logout(client)
    login(client, "committee@example.test")
    reply = post(client, f"/api/discussions/{first}/comments", {
        "body": "Thanks, that matches the board note.", "parent_comment_id": parent_id,
    })
    assert reply.status_code == 201, reply.json
    assert reply.json["comment"]["parent_comment_id"] == parent_id
    assert reply.json["comment"]["author_display_name"] == "Committee"
    crossed = post(client, f"/api/discussions/{second}/comments", {
        "body": "This reply belongs elsewhere.", "parent_comment_id": parent_id,
    })
    assert crossed.status_code == 409
    assert crossed.json["error"]["code"] == "COMMENT_PARENT_MISMATCH"
    missing_parent = post(client, f"/api/discussions/{second}/comments", {
        "body": "No such comment.", "parent_comment_id": "00000000-0000-4000-8000-000000000099",
    })
    assert missing_parent.status_code == 404
    assert missing_parent.json["error"]["code"] == "COMMENT_NOT_FOUND"
    detail = client.get(f"/api/discussions/{first}")
    assert detail.status_code == 200
    assert detail.json["discussion"]["comment_count"] == 2
    assert [row["id"] for row in detail.json["comments"]][0] == parent_id
    assert client.get(f"/api/discussions/{second}").json["comments"] == []
    absent = client.get("/api/discussions/00000000-0000-4000-8000-000000000099")
    assert absent.status_code == 404
    short = post(client, "/api/discussions", {"title": "No", "body": "Too short a title."})
    assert short.status_code == 400
    assert "title" in short.json["error"]["fields"]
