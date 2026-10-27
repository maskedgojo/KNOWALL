"""Phase 9 integration contract tests; synthetic single-society members."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.access import KNOWN_PERMISSIONS, requires_permission
from app.modules.identity.models import (
    AccountStatus, Flat, Household, Membership, MembershipStatus,
    PermissionRole, ResidentCategory, RoleAssignment, Tower, User,
)

PASSWORD = "PhaseNineStrongPass!123"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "phase9-only-test-secret-key",
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


def login(client, email):
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    result = client.post("/api/auth/login", json={"email": email, "password": PASSWORD},
                         headers={"X-CSRF-Token": csrf})
    assert result.status_code == 200, result.json


@pytest.fixture()
def sample(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        home = Household(flat=flat, label="Owner Household")
        db.session.add(home)
        db.session.flush()
        actors = {}
        for name, role, verified in (
            ("applicant", PermissionRole.APPLICANT, True),
            ("unverified", PermissionRole.APPLICANT, False),
            ("resident", PermissionRole.RESIDENT, True),
            ("admin", PermissionRole.SOCIETY_ADMIN, True),
            ("unverified_admin", PermissionRole.SOCIETY_ADMIN, False),
            ("platform_admin", PermissionRole.PLATFORM_ADMIN, True),
            ("platform_resident", PermissionRole.PLATFORM_ADMIN, True),
            ("committee", PermissionRole.COMMITTEE_MEMBER, True),
            ("role_only", PermissionRole.RESIDENT, True),
            ("suspended_member", PermissionRole.RESIDENT, True),
        ):
            user = User(
                email=f"{name}@example.test", display_name=name,
                password_hash=generate_password_hash(PASSWORD),
                account_status=AccountStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc) if verified else None,
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user=user, role=role))
            actors[name] = user
        for name, status in (
            ("resident", MembershipStatus.ACTIVE),
            ("platform_resident", MembershipStatus.ACTIVE),
            ("committee", MembershipStatus.ACTIVE),
            ("suspended_member", MembershipStatus.SUSPENDED),
        ):
            db.session.add(Membership(
                user=actors[name], household=home, category=ResidentCategory.OWNER,
                status=status, valid_from=date.today() - timedelta(days=2),
            ))
        db.session.commit()
        return {n: str(u.id) for n, u in actors.items()}


def test_anonymous_access_is_401(client):
    assert client.get("/api/me/access").status_code == 401
    assert client.get("/api/admin/applications").status_code == 401


def test_applicant_gets_only_account_permissions(client, sample):
    login(client, "applicant@example.test")
    result = client.get("/api/me/access")
    assert result.status_code == 200
    p = set(result.json["permissions"])
    assert result.json["verified_resident"] is False
    assert "identity.profile.update" in p
    assert "identity.applications.submit" in p
    assert "identity.households.read" not in p
    assert "identity.admin.manage" not in p
    assert "civic.issues.create" not in p


def test_unverified_user_cannot_submit_through_permission_policy(client, sample):
    login(client, "unverified@example.test")
    p = client.get("/api/me/access").json["permissions"]
    assert "identity.profile.read" in p
    assert "identity.applications.submit" not in p


def test_active_resident_gets_society_capabilities(client, sample):
    login(client, "resident@example.test")
    result = client.get("/api/me/access")
    assert result.status_code == 200
    assert result.json["verified_resident"] is True
    p = set(result.json["permissions"])
    assert "identity.households.read" in p
    assert "society.notices.read" in p
    assert "society.notices.manage" not in p
    assert "civic.issues.create" in p
    assert "identity.admin.manage" not in p


def test_resident_role_without_membership_does_not_grant_access(client, sample):
    login(client, "role_only@example.test")
    result = client.get("/api/me/access")
    assert result.json["verified_resident"] is False
    assert "identity.households.read" not in result.json["permissions"]
    assert client.get("/api/me/households").status_code == 403


def test_suspended_membership_removes_resident_capabilities(client, sample):
    login(client, "suspended_member@example.test")
    result = client.get("/api/me/access")
    assert result.json["verified_resident"] is False
    assert "society.notices.read" not in result.json["permissions"]


def test_admin_does_not_require_resident_membership(client, sample):
    login(client, "admin@example.test")
    result = client.get("/api/me/access")
    assert result.status_code == 200
    permissions = set(result.json["permissions"])
    assert result.json["verified_resident"] is False
    assert "identity.admin.manage" in permissions
    assert "identity.admin.applications.read" in permissions
    assert "identity.admin.applications.decide" in permissions
    assert "identity.admin.memberships.manage" in permissions
    assert "identity.admin.audit.read" in permissions
    assert "identity.admin.documents.review" in permissions
    assert "identity.invitations.create" in permissions
    assert "society.notices.manage" in permissions
    assert "society.notices.read" not in permissions
    assert client.get("/api/admin/applications").status_code == 200


def test_unverified_admin_cannot_use_admin_routes(client, sample):
    login(client, "unverified_admin@example.test")
    permissions = client.get("/api/me/access").json["permissions"]
    assert "identity.admin.manage" not in permissions
    assert "society.notices.manage" not in permissions
    assert client.get("/api/admin/applications").status_code == 403


def test_platform_admin_keeps_admin_access_without_notice_management(client, sample):
    login(client, "platform_admin@example.test")
    result = client.get("/api/me/access")
    permissions = set(result.json["permissions"])
    assert result.json["verified_resident"] is False
    assert "identity.admin.manage" in permissions
    assert "identity.admin.applications.read" in permissions
    assert "society.notices.manage" not in permissions
    assert "society.notices.read" not in permissions


def test_platform_admin_membership_grants_read_without_notice_management(client, sample):
    login(client, "platform_resident@example.test")
    result = client.get("/api/me/access")
    permissions = set(result.json["permissions"])
    assert result.json["verified_resident"] is True
    assert "identity.admin.manage" in permissions
    assert "society.notices.read" in permissions
    assert "identity.households.read" in permissions
    assert "society.notices.manage" not in permissions


def test_committee_member_can_read_notices_but_cannot_manage_them(client, sample):
    login(client, "committee@example.test")
    result = client.get("/api/me/access")
    permissions = set(result.json["permissions"])
    assert result.json["verified_resident"] is True
    assert "society.notices.read" in permissions
    assert "society.notices.manage" not in permissions
    assert "identity.admin.manage" not in permissions


def test_revoking_admin_role_removes_access_next_request(client, app, sample):
    login(client, "admin@example.test")
    assert client.get("/api/admin/applications").status_code == 200
    with app.app_context():
        actor = db.session.scalar(select(User).where(User.email == "admin@example.test"))
        row = db.session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == actor.id))
        row.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    assert client.get("/api/admin/applications").status_code == 403
    permissions = client.get("/api/me/access").json["permissions"]
    assert "identity.admin.manage" not in permissions
    assert "society.notices.manage" not in permissions


def test_membership_expiration_revokes_effective_capabilities(client, app, sample):
    login(client, "resident@example.test")
    assert "identity.households.read" in client.get("/api/me/access").json["permissions"]
    with app.app_context():
        actor = db.session.scalar(select(User).where(User.email == "resident@example.test"))
        row = db.session.scalar(select(Membership).where(Membership.user_id == actor.id))
        row.valid_until = date.today() - timedelta(days=1)
        db.session.commit()
    assert "identity.households.read" not in client.get("/api/me/access").json["permissions"]
    assert client.get("/api/me/households").status_code == 403


def test_unknown_permission_fail_closed():
    assert "society.notices.manage" in KNOWN_PERMISSIONS
    assert "society.voting.cast" not in KNOWN_PERMISSIONS
    with pytest.raises(ValueError):
        requires_permission("society.voting.cast")
