"""Family relationship, privacy, verified occupancy and profile integration tests.

Uses Flask sessions/CSRF and SQLite like the existing KNOWALL API suite.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
import re

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AuditLog, Flat, Household, Invitation, Membership, MembershipStatus,
    MembershipApplication, ApplicationStatus, PermissionRole, ResidentCategory,
    RoleAssignment, Tower, User,
)

PASSWORD = "FamilyEnhancementPass2026!"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True, "SECRET_KEY": "only-for-enhancement-tests",
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


def patch(client, url, obj):
    return client.patch(url, json=obj, headers={"X-CSRF-Token": csrf(client)})


def post(client, url, obj):
    return client.post(url, json=obj, headers={"X-CSRF-Token": csrf(client)})


def login(client, email):
    response = post(client, "/api/auth/login", {"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.json


@pytest.fixture()
def data(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        owner_home = Household(flat=flat, label="Owner Household")
        tenant_home = Household(flat=flat, label="Tenant Household")
        db.session.add_all([owner_home, tenant_home])
        db.session.flush()
        users = {}
        for name, role in [
            ("owner", PermissionRole.RESIDENT), ("family", PermissionRole.RESIDENT),
            ("tenant", PermissionRole.RESIDENT), ("admin", PermissionRole.SOCIETY_ADMIN),
            ("invitee", PermissionRole.APPLICANT),
        ]:
            user = User(display_name=name.title(), email=f"{name}@example.test",
                        password_hash=generate_password_hash(PASSWORD),
                        email_verified_at=datetime.now(timezone.utc))
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user=user, role=role))
            users[name] = user
        owner_membership = Membership(user=users["owner"], household=owner_home,
                                      category=ResidentCategory.OWNER,
                                      status=MembershipStatus.ACTIVE, valid_from=date.today())
        tenant_membership = Membership(user=users["tenant"], household=tenant_home,
                                       category=ResidentCategory.TENANT,
                                       status=MembershipStatus.ACTIVE, valid_from=date.today(),
                                       valid_until=date.today()+timedelta(days=180))
        db.session.add_all([owner_membership, tenant_membership])
        db.session.flush()
        family_membership = Membership(user=users["family"], household=owner_home,
                                       category=ResidentCategory.FAMILY_MEMBER,
                                       status=MembershipStatus.ACTIVE, valid_from=date.today(),
                                       sponsor=owner_membership, relationship_to_sponsor="SPOUSE")
        db.session.add(family_membership)
        db.session.commit()
        return {
            "flat": str(flat.id), "owner_home": str(owner_home.id),
            "tenant_home": str(tenant_home.id),
            "owner_membership": str(owner_membership.id),
            "tenant_membership": str(tenant_membership.id),
            "family_membership": str(family_membership.id),
        }


def test_private_profile_supports_optional_birth_date_and_occupation(client, app, data):
    login(client, "owner@example.test")
    updated = patch(client, "/api/me/profile", {
        "date_of_birth": "1991-08-16", "occupation": "  Engineer  ",
    })
    assert updated.status_code == 200, updated.json
    assert updated.json["user"]["date_of_birth"] == "1991-08-16"
    assert updated.json["user"]["occupation"] == "Engineer"
    assert client.get("/api/auth/me").json["user"]["occupation"] == "Engineer"
    with app.app_context():
        records = db.session.scalars(select(AuditLog).where(AuditLog.action == "PROFILE_UPDATED")).all()
        assert records[-1].details["changed_fields"] == ["date_of_birth", "occupation"]


def test_profile_rejects_invalid_dates_and_types(client, data):
    login(client, "owner@example.test")
    for body in (
        {"date_of_birth": "2026-14-40"},
        {"date_of_birth": "1880-01-01"},
        {"date_of_birth": "2999-01-01"},
        {"occupation": 42},
        {"occupation": "a" * 101},
    ):
        response = patch(client, "/api/me/profile", body)
        assert response.status_code == 400, (body, response.json)
    assert patch(client, "/api/me/profile", {"date_of_birth": None, "occupation": None}).status_code == 200


def test_family_tree_scoped_to_own_household_without_private_profile_fields(client, data):
    login(client, "family@example.test")
    response = client.get("/api/me/family-tree")
    assert response.status_code == 200, response.json
    trees = response.json["households"]
    assert len(trees) == 1 and trees[0]["household_id"] == data["owner_home"]
    assert {row["display_name"] for row in trees[0]["members"]} == {"Owner", "Family"}
    assert trees[0]["relationships"] == [{
        "sponsor_membership_id": data["owner_membership"],
        "family_membership_id": data["family_membership"],
        "relationship_to_sponsor": "SPOUSE",
    }]
    assert "Tenant" not in str(response.json)
    for key in ("email", "phone", "occupation", "date_of_birth", "password_hash"):
        assert key not in str(response.json)


def test_tenant_cannot_see_owner_family_tree(client, data):
    login(client, "tenant@example.test")
    response = client.get("/api/me/family-tree")
    assert response.status_code == 200
    assert [t["household_id"] for t in response.json["households"]] == [data["tenant_home"]]
    assert "Family" not in str(response.json)


def test_nonresident_cannot_read_family_tree(client, data):
    assert client.get("/api/me/family-tree").status_code == 401
    login(client, "invitee@example.test")
    assert client.get("/api/me/family-tree").status_code == 403


def test_invitation_relationship_flows_to_active_membership(client, app, data):
    login(client, "owner@example.test")
    invitation = post(client, "/api/invitations", {
        "flat_id": data["flat"], "household_id": data["owner_home"],
        "sponsor_membership_id": data["owner_membership"],
        "category": "FAMILY_MEMBER", "email": "invitee@example.test",
        "relationship_to_sponsor": "CHILD",
    })
    assert invitation.status_code == 201, invitation.json
    assert invitation.json["invitation"]["relationship_to_sponsor"] == "CHILD"
    message = app.extensions["knowall_outbox"][-1]["body"]
    raw_token = re.search(r"token=([A-Za-z0-9_-]+)", message).group(1)
    invitee = app.test_client()
    login(invitee, "invitee@example.test")
    accepted = post(invitee, "/api/invitations/accept", {
        "token": raw_token,
        "relationship_to_sponsor": "SIBLING",
        "declared_current_occupant": True,
    })
    assert accepted.status_code == 201, accepted.json
    membership = accepted.json["membership"]
    assert accepted.json["outcome"] == "FAMILY_MEMBERSHIP_ACTIVATED"
    assert membership["relationship_to_sponsor"] == "SIBLING"
    assert membership["is_current_occupant"] is None  # declaration is NOT admin confirmation
    assert invitee.get("/api/me/access").json["verified_resident"] is True


def test_nonfamily_cannot_set_relationship(client, data):
    login(client, "invitee@example.test")
    result = post(client, "/api/membership/applications", {
        "flat_id": data["flat"], "category": "OWNER",
        "relationship_to_sponsor": "SPOUSE",
    })
    assert result.status_code == 400, result.json


def test_invalid_relationship_and_occupancy_rejected(client, data):
    login(client, "invitee@example.test")
    assert post(client, "/api/membership/applications", {
        "flat_id": data["flat"], "category": "OWNER", "declared_current_occupant": "yes",
    }).status_code == 400
    draft = post(client, "/api/membership/applications", {
        "flat_id": data["flat"], "category": "OWNER",
    })
    assert draft.status_code == 201
    app_id = draft.json["application"]["id"]
    assert patch(client, f"/api/membership/applications/{app_id}", {
        "relationship_to_sponsor": "UNCLE",
    }).status_code == 400
    assert patch(client, f"/api/membership/applications/{app_id}", {
        "declared_current_occupant": "yes",
    }).status_code == 400


def test_admin_occupancy_requires_permission_and_boolean(client, app, data):
    login(client, "owner@example.test")
    url = f"/api/admin/memberships/{data['owner_membership']}/occupancy"
    assert patch(client, url, {"is_current_occupant": True, "reason": "Manually verified"}).status_code == 403
    admin = app.test_client()
    login(admin, "admin@example.test")
    assert patch(admin, url, {"is_current_occupant": "true", "reason": "Checked"}).status_code == 400
    assert patch(admin, url, {"is_current_occupant": True, "reason": "x"}).status_code == 400
    ok = patch(admin, url, {"is_current_occupant": False, "reason": "Owner lives elsewhere"})
    assert ok.status_code == 200, ok.json
    assert ok.json["membership"]["is_current_occupant"] is False
    assert ok.json["membership"]["occupancy_confirmed_at"] is not None
    with app.app_context():
        updated = db.session.get(Membership, UUID(data["owner_membership"]))
        assert updated.occupancy_confirmed_by_user_id is not None
        logs = db.session.scalars(select(AuditLog).where(AuditLog.action == "MEMBERSHIP_OCCUPANCY_CONFIRMED")).all()
        assert logs[-1].details["current"] is False


def test_occupancy_unknown_until_admin_confirms(client, data):
    login(client, "tenant@example.test")
    entry = client.get("/api/me/memberships").json["memberships"][0]
    assert entry["is_current_occupant"] is None
    assert entry["occupancy_confirmed_at"] is None


def test_family_relationship_not_based_on_shared_password(client, data):
    login(client, "family@example.test")
    summary = client.get("/api/me/memberships").json["memberships"][0]
    assert summary["relationship_to_sponsor"] == "SPOUSE"
    assert summary["sponsor_membership_id"] == data["owner_membership"]


def test_admin_can_correct_existing_family_relationship_with_audit(client, app, data):
    login(client, "admin@example.test")
    url = f"/api/admin/memberships/{data['family_membership']}/relationship"
    bad = patch(client, url, {"relationship_to_sponsor": "NEIGHBOR", "reason": "Incorrect"})
    assert bad.status_code == 400
    ok = patch(client, url, {"relationship_to_sponsor": "SIBLING", "reason": "Corrected after member confirmation"})
    assert ok.status_code == 200, ok.json
    assert ok.json["membership"]["relationship_to_sponsor"] == "SIBLING"
    with app.app_context():
        records = db.session.scalars(select(AuditLog).where(AuditLog.action == "FAMILY_RELATIONSHIP_CORRECTED")).all()
        assert len(records) == 1
        assert records[0].details["previous"] == "SPOUSE"


def test_admin_cannot_set_family_relation_for_tenant(client, app, data):
    login(client, "admin@example.test")
    result = patch(client, f"/api/admin/memberships/{data['tenant_membership']}/relationship", {
        "relationship_to_sponsor": "SPOUSE", "reason": "Invalid test"
    })
    assert result.status_code == 409
