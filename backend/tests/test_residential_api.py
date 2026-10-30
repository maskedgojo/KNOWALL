"""Phase 5 HTTP tests. Kept in a separate app context per request (Phase 4A fix)."""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AuditLog, Flat, Household, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower, User,
)

PASSWORD = "StrongLocalTestPassword123!"


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "phase5-local-tests-only-not-for-production",
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
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json["csrf_token"]


def login(client, email):
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD},
                           headers={"X-CSRF-Token": csrf(client)})
    assert response.status_code == 200, response.json
    return response


@pytest.fixture()
def example(app):
    with app.app_context():
        db.session.add(SocietyProfile(
            id=1, name="Green Valley Residency", address="Fictional Demo Road",
            locality="Meadow Park", city="Demo City",
        ))
        tower_b = Tower(name="B")
        tower_a = Tower(name="A")
        db.session.add_all((tower_b, tower_a))
        db.session.flush()
        b402 = Flat(tower=tower_b, flat_number="402", floor_number=4)
        b403 = Flat(tower=tower_b, flat_number="403", floor_number=4)
        a101 = Flat(tower=tower_a, flat_number="101", floor_number=1)
        db.session.add_all((b402, b403, a101))
        db.session.flush()
        owner_home = Household(flat=b402, label="Owner Home")
        tenant_home = Household(flat=b402, label="Tenant Home")
        db.session.add_all((owner_home, tenant_home))
        db.session.flush()
        verified = datetime.now(timezone.utc)
        owner = User(display_name="Owner Example", email="owner@example.test",
                     password_hash=generate_password_hash(PASSWORD), email_verified_at=verified)
        family = User(display_name="Family Example", email="family@example.test",
                      password_hash=generate_password_hash(PASSWORD), email_verified_at=verified)
        tenant = User(display_name="Tenant Example", email="tenant@example.test",
                      password_hash=generate_password_hash(PASSWORD), email_verified_at=verified)
        applicant = User(display_name="Applicant Example", email="applicant@example.test",
                         password_hash=generate_password_hash(PASSWORD), email_verified_at=None)
        db.session.add_all((owner, family, tenant, applicant))
        db.session.flush()
        for user, role in ((owner, PermissionRole.RESIDENT), (family, PermissionRole.RESIDENT),
                           (tenant, PermissionRole.RESIDENT), (applicant, PermissionRole.APPLICANT)):
            db.session.add(RoleAssignment(user=user, role=role))
        today = date.today()
        owner_membership = Membership(user=owner, household=owner_home,
                                      category=ResidentCategory.OWNER, status=MembershipStatus.ACTIVE,
                                      valid_from=today - timedelta(days=10))
        tenant_membership = Membership(user=tenant, household=tenant_home,
                                       category=ResidentCategory.TENANT, status=MembershipStatus.ACTIVE,
                                       valid_from=today - timedelta(days=10), valid_until=today + timedelta(days=10))
        db.session.add_all((owner_membership, tenant_membership))
        db.session.flush()
        db.session.add(Membership(user=family, household=owner_home,
                                  category=ResidentCategory.FAMILY_MEMBER,
                                  sponsor=owner_membership, status=MembershipStatus.ACTIVE,
                                  valid_from=today - timedelta(days=5)))
        db.session.commit()
        return {
            "a": str(tower_a.id), "b": str(tower_b.id),
            "b402": str(b402.id), "b403": str(b403.id),
            "owner_household": str(owner_home.id), "tenant_household": str(tenant_home.id),
            "owner_id": str(owner.id), "family_id": str(family.id),
        }


def test_society_not_configured(client):
    response = client.get("/api/residential/society")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "SOCIETY_NOT_CONFIGURED"


def test_public_society_towers_and_sort(client, example):
    society = client.get("/api/residential/society")
    assert society.status_code == 200
    assert society.json["society"]["name"] == "Green Valley Residency"
    towers = client.get("/api/residential/towers")
    assert towers.status_code == 200
    assert [t["name"] for t in towers.json["towers"]] == ["A", "B"]


def test_public_flats_floor_filter_and_sort(client, example):
    response = client.get(f"/api/residential/towers/{example['b']}/flats?floor=4")
    assert response.status_code == 200
    assert [f["flat_number"] for f in response.json["flats"]] == ["402", "403"]
    assert all(f["floor_number"] == 4 for f in response.json["flats"])
    assert client.get(f"/api/residential/towers/{example['b']}/flats?floor=2").json == {"flats": []}


@pytest.mark.parametrize("floor", ["-1", "x", "1.5", "9999", " 4", "４"])
def test_invalid_floor_returns_validation_error(client, example, floor):
    response = client.get(f"/api/residential/towers/{example['b']}/flats", query_string={"floor": floor})
    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_tower_and_flat_404(client, example):
    assert client.get(f"/api/residential/towers/{uuid4()}/flats").status_code == 404
    assert client.get(f"/api/residential/flats/{uuid4()}").status_code == 404


def test_public_flat_does_not_leak_residents(client, example):
    response = client.get(f"/api/residential/flats/{example['b402']}")
    assert response.status_code == 200
    assert set(response.json["flat"]) == {"id", "tower_id", "tower_name", "flat_number", "floor_number"}
    assert "Owner Example" not in str(response.json)
    assert "Owner Home" not in str(response.json)


def test_profile_requires_authentication(client):
    for url in ("/api/me/profile", "/api/me/memberships", "/api/me/households", "/api/me/access"):
        assert client.get(url).status_code == 401


def test_profile_update_csrf_and_validation(client, app, example):
    login(client, "owner@example.test")
    assert client.patch("/api/me/profile", json={"display_name": "Edited"}).status_code == 403
    invalid = client.patch("/api/me/profile", json={"email": "other@example.test"},
                           headers={"X-CSRF-Token": csrf(client)})
    assert invalid.status_code == 400
    assert "email" in invalid.json["error"]["fields"]
    update = client.patch("/api/me/profile", json={"display_name": "  Updated Owner  ", "phone": "+919999888777"},
                          headers={"X-CSRF-Token": csrf(client)})
    assert update.status_code == 200
    assert update.json["user"]["display_name"] == "Updated Owner"
    assert update.json["user"]["phone"] == "+919999888777"
    with app.app_context():
        records = db.session.scalars(select(AuditLog).where(AuditLog.action == "PROFILE_UPDATED")).all()
        assert len(records) == 1
        assert records[0].details == {"changed_fields": ["display_name", "phone"]}


def test_profile_update_clear_phone_and_reject_empty(client, example):
    login(client, "owner@example.test")
    assert client.patch("/api/me/profile", json={}, headers={"X-CSRF-Token": csrf(client)}).status_code == 400
    result = client.patch("/api/me/profile", json={"phone": None},
                          headers={"X-CSRF-Token": csrf(client)})
    assert result.status_code == 200
    assert result.json["user"]["phone"] is None


def test_owner_cannot_read_other_household_and_can_read_own(client, example):
    login(client, "owner@example.test")
    response = client.get("/api/me/households")
    assert response.status_code == 200
    assert [x["id"] for x in response.json["households"]] == [example["owner_household"]]
    assert {m["display_name"] for m in response.json["households"][0]["members"]} == {
        "Owner Example", "Family Example",
    }
    assert "Tenant Example" not in str(response.json)
    assert "@example.test" not in str(response.json)


def test_applicant_cannot_view_household(client, example):
    login(client, "applicant@example.test")
    assert client.get("/api/me/households").status_code == 403
    assert client.get("/api/me/memberships").json == {"memberships": []}
    access = client.get("/api/me/access").json
    assert access["verified_resident"] is False
    assert access["roles"] == ["APPLICANT"]


def test_family_member_loses_access_if_sponsor_suspended(client, app, example):
    login(client, "family@example.test")
    assert client.get("/api/me/households").status_code == 200
    with app.app_context():
        sponsor = db.session.scalar(select(Membership).where(Membership.user_id == UUID(example["owner_id"])))
        sponsor.status = MembershipStatus.SUSPENDED
        db.session.commit()
    assert client.get("/api/me/households").status_code == 403
    membership = client.get("/api/me/memberships").json["memberships"][0]
    assert membership["access_state"] == "SPONSOR_INELIGIBLE"


def test_expired_membership_does_not_allow_access(client, app, example):
    login(client, "tenant@example.test")
    with app.app_context():
        member = db.session.scalar(select(Membership).where(Membership.category == ResidentCategory.TENANT))
        member.valid_until = date.today() - timedelta(days=1)
        db.session.commit()
    assert client.get("/api/me/households").status_code == 403
    result = client.get("/api/me/access")
    assert result.status_code == 200
    assert result.json["verified_resident"] is False
    assert result.json["active_memberships"] == []


def test_role_revocation_disables_household_access(client, app, example):
    login(client, "owner@example.test")
    with app.app_context():
        row = db.session.scalar(select(RoleAssignment).join(User, User.id == RoleAssignment.user_id).where(User.email == "owner@example.test"))
        row.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    assert client.get("/api/me/households").status_code == 403
    assert client.get("/api/me/access").json["verified_resident"] is False


def test_openapi_and_swagger_routes_work(client, example):
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert b"swagger-ui" in docs.data
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert spec.json["openapi"].startswith("3.0")
    assert "/api/me/households" in spec.json["paths"]
    assert "/api/auth/password/reset" in spec.json["paths"]


def test_family_access_invalid_if_sponsor_role_revoked(client, app, example):
    login(client, "family@example.test")
    with app.app_context():
        owner_role = db.session.scalar(
            select(RoleAssignment)
            .join(User, User.id == RoleAssignment.user_id)
            .where(User.email == "owner@example.test")
        )
        owner_role.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    assert client.get("/api/me/households").status_code == 403
    assert client.get("/api/me/access").json["verified_resident"] is False


def test_household_member_not_leaked_from_unrelated_flat(client, example):
    login(client, "tenant@example.test")
    response = client.get("/api/me/households")
    assert response.status_code == 200
    assert [home["id"] for home in response.json["households"]] == [example["tenant_household"]]
    assert "Owner Example" not in str(response.json)
    assert "Family Example" not in str(response.json)
