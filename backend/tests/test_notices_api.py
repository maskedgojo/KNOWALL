"""Notice V1 API tests. In-memory schema only; does not migrate the project database."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, Flat, Household, User,
)
from app.modules.notices.models import Notice

PASSWORD = "NoticeV1StrongPass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "notice-v1-test-secret-key",
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


def patch(client, url, body):
    return client.patch(url, json=body, headers={"X-CSRF-Token": csrf(client)})


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
        actors = {}
        for name, role, member in (
            ("admin", PermissionRole.SOCIETY_ADMIN, False),
            ("platform", PermissionRole.PLATFORM_ADMIN, False),
            ("resident", PermissionRole.RESIDENT, True),
            ("committee", PermissionRole.COMMITTEE_MEMBER, True),
            ("applicant", PermissionRole.APPLICANT, False),
        ):
            user = User(
                email=f"{name}@example.test", display_name=name,
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
            actors[name] = user
        db.session.commit()
        return {name: str(user.id) for name, user in actors.items()}


def draft(client, **overrides):
    payload = {"title": "Water shutdown", "body": "Supply stops at noon.", "expires_at": None}
    payload.update(overrides)
    return post(client, "/api/admin/notices", payload)


def test_anonymous_reads_require_auth_and_writes_require_csrf(client):
    assert client.get("/api/notices").status_code == 401
    assert client.post("/api/admin/notices", json={"title": "Water", "body": "Noon"}).status_code == 403
    assert client.post(
        "/api/admin/notices", json={"title": "Water", "body": "Noon"},
        headers={"X-CSRF-Token": csrf(client)},
    ).status_code == 401


def test_resident_read_does_not_grant_management(client, people):
    login(client, "resident@example.test")
    denied = draft(client)
    assert denied.status_code == 403
    assert denied.json["error"]["code"] == "FORBIDDEN"
    assert client.get("/api/admin/notices").status_code == 403


def test_platform_admin_and_committee_cannot_manage(client, people):
    login(client, "platform@example.test")
    assert draft(client).status_code == 403
    logout(client)
    login(client, "committee@example.test")
    assert draft(client).status_code == 403
    assert client.get("/api/notices").status_code == 200


def test_society_admin_manages_without_resident_read(client, people):
    login(client, "admin@example.test")
    created = draft(client)
    assert created.status_code == 201, created.json
    assert created.json["notice"]["society_id"] == 1
    assert created.json["notice"]["status"] == "DRAFT"
    assert client.get("/api/notices").status_code == 403
    access = client.get("/api/me/access").json["permissions"]
    assert "society.notices.manage" in access
    assert "society.notices.read" not in access


def test_client_cannot_choose_society_or_skip_profile(client, app, people):
    login(client, "admin@example.test")
    rejected = draft(client, society_id=2)
    assert rejected.status_code == 400
    assert rejected.json["error"]["fields"]["society_id"] == "Unknown field."
    with app.app_context():
        db.session.delete(db.session.get(SocietyProfile, 1))
        db.session.commit()
    missing = draft(client)
    assert missing.status_code == 404
    assert missing.json["error"]["code"] == "SOCIETY_NOT_CONFIGURED"


def test_draft_edit_publish_immutability_and_audit(client, app, people):
    login(client, "admin@example.test")
    created = draft(client)
    notice_id = created.json["notice"]["id"]
    edited = patch(client, f"/api/admin/notices/{notice_id}", {
        "title": "Water shutdown tomorrow", "body": "Supply stops at 1 pm.",
    })
    assert edited.status_code == 200, edited.json
    assert edited.json["notice"]["title"] == "Water shutdown tomorrow"
    published = post(client, f"/api/admin/notices/{notice_id}/publish", {})
    assert published.status_code == 200, published.json
    assert published.json["notice"]["status"] == "PUBLISHED"
    assert published.json["notice"]["visible_to_residents"] is True
    frozen = patch(client, f"/api/admin/notices/{notice_id}", {"title": "Changed after publish"})
    assert frozen.status_code == 409
    assert frozen.json["error"]["code"] == "NOTICE_IMMUTABLE"
    with app.app_context():
        stored = db.session.get(Notice, UUID(notice_id))
        assert stored.title == "Water shutdown tomorrow"
        audit = db.session.scalar(select(AuditLog).where(
            AuditLog.action == "NOTICE_PUBLISHED", AuditLog.entity_type == "NOTICE",
        ))
        assert str(audit.entity_id) == notice_id
        assert audit.details["title"] == "Water shutdown tomorrow"
        assert "body" not in audit.details


def test_published_notice_is_readable_only_by_current_readers(client, people):
    login(client, "admin@example.test")
    created = draft(client)
    notice_id = created.json["notice"]["id"]
    logout(client)
    login(client, "resident@example.test")
    assert client.get(f"/api/notices/{notice_id}").status_code == 404
    hidden = {row["id"] for row in client.get("/api/notices").json["notices"]}
    assert notice_id not in hidden
    logout(client)
    login(client, "admin@example.test")
    assert post(client, f"/api/admin/notices/{notice_id}/publish", {}).status_code == 200
    logout(client)
    login(client, "resident@example.test")
    listed = client.get("/api/notices")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json["notices"]] == [notice_id]
    detail = client.get(f"/api/notices/{notice_id}")
    assert detail.status_code == 200
    assert detail.json["notice"]["body"] == "Supply stops at noon."
    logout(client)
    login(client, "applicant@example.test")
    assert client.get("/api/notices").status_code == 403
    assert client.get(f"/api/notices/{notice_id}").status_code == 403


def test_expiry_hides_without_archiving_and_archive_is_terminal(client, app, people):
    login(client, "admin@example.test")
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = draft(client, expires_at=future)
    notice_id = created.json["notice"]["id"]
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    expired_draft = draft(client, title="Already over", body="Too late.", expires_at=past)
    assert expired_draft.status_code == 201, expired_draft.json
    assert post(client, f"/api/admin/notices/{expired_draft.json['notice']['id']}/publish", {}).status_code == 400
    assert post(client, f"/api/admin/notices/{notice_id}/publish", {}).status_code == 200
    current = draft(client, title="Still current", body="This notice has no expiry.")
    assert current.status_code == 201, current.json
    current_id = current.json["notice"]["id"]
    assert post(client, f"/api/admin/notices/{current_id}/publish", {}).status_code == 200
    with app.app_context():
        row = db.session.get(Notice, UUID(notice_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()
    managed = client.get(f"/api/admin/notices/{notice_id}")
    assert managed.status_code == 200
    assert managed.json["notice"]["status"] == "PUBLISHED"
    assert managed.json["notice"]["visible_to_residents"] is False
    logout(client)
    login(client, "resident@example.test")
    listed = client.get("/api/notices")
    assert listed.status_code == 200
    assert listed.headers["Cache-Control"] == "no-store"
    assert [item["id"] for item in listed.json["notices"]] == [current_id]
    assert client.get(f"/api/notices/{notice_id}").status_code == 404
    assert client.get(f"/api/notices/{current_id}").status_code == 200
    logout(client)
    login(client, "admin@example.test")
    archived = post(client, f"/api/admin/notices/{notice_id}/archive", {})
    assert archived.status_code == 200
    assert archived.json["notice"]["status"] == "ARCHIVED"
    assert archived.json["notice"]["published_at"] is not None
    again = post(client, f"/api/admin/notices/{notice_id}/archive", {})
    assert again.status_code == 409
    assert post(client, f"/api/admin/notices/{notice_id}/publish", {}).status_code == 409
    assert patch(client, f"/api/admin/notices/{notice_id}", {"title": "Still frozen"}).status_code == 409


def test_archive_draft_and_replacement_leaves_source_unchanged(client, app, people):
    login(client, "admin@example.test")
    created = draft(client)
    notice_id = created.json["notice"]["id"]
    assert post(client, f"/api/admin/notices/{notice_id}/replacements", {}).status_code == 409
    assert post(client, f"/api/admin/notices/{notice_id}/publish", {}).status_code == 200
    replacement = post(client, f"/api/admin/notices/{notice_id}/replacements", {})
    assert replacement.status_code == 201, replacement.json
    copy = replacement.json["notice"]
    assert copy["status"] == "DRAFT"
    assert copy["replaces_notice_id"] == notice_id
    assert copy["id"] != notice_id
    source = client.get(f"/api/admin/notices/{notice_id}").json["notice"]
    assert source["status"] == "PUBLISHED"
    assert source["body"] == "Supply stops at noon."
    edited = patch(client, f"/api/admin/notices/{copy['id']}", {
        "title": "Corrected shutdown", "body": "Supply stops at 3 pm.", "expires_at": None,
    })
    assert edited.status_code == 200
    assert post(client, f"/api/admin/notices/{copy['id']}/publish", {}).status_code == 200
    logout(client)
    login(client, "committee@example.test")
    visible = client.get("/api/notices").json["notices"]
    assert [row["title"] for row in visible] == ["Corrected shutdown", "Water shutdown"]
    logout(client)
    login(client, "admin@example.test")
    draft_id = draft(client, title="Unused draft", body="Withdraw this.").json["notice"]["id"]
    withdrawn = post(client, f"/api/admin/notices/{draft_id}/archive", {})
    assert withdrawn.status_code == 200
    assert withdrawn.json["notice"]["published_at"] is None
    logout(client)
    login(client, "resident@example.test")
    assert client.get(f"/api/notices/{draft_id}").status_code == 404
    with app.app_context():
        actions = set(db.session.scalars(select(AuditLog.action).where(AuditLog.entity_type == "NOTICE")).all())
    assert {"NOTICE_CREATED", "NOTICE_PUBLISHED", "NOTICE_REPLACEMENT_CREATED", "NOTICE_ARCHIVED"} <= actions


def test_invalid_pagination_and_naive_expiry_are_rejected(client, people):
    login(client, "admin@example.test")
    naive = draft(client, expires_at="2026-10-25T12:00:00")
    assert naive.status_code == 400
    assert naive.json["error"]["fields"]["expires_at"] == "Expiry must include a timezone."
    assert client.get("/api/admin/notices?limit=0").status_code == 400
    logout(client)
    login(client, "resident@example.test")
    assert client.get("/api/notices?offset=-1").status_code == 400
