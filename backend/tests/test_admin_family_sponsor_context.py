"""Contract and access checks for explicit family-sponsor admin review context.

All identities are fictional. Does not invoke Surya or external email services.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, ApplicationStatus, AuditLog, DocumentType, Flat, Household,
    Membership, MembershipApplication, MembershipStatus, OCRResult, OCRStatus,
    PermissionRole, ResidentCategory, RoleAssignment, Tower, User,
    VerificationDocument,
)

PASSWORD = "FamilySponsorContextDemo!2026"


@pytest.fixture()
def app(tmp_path):
    instance = create_app({
        "TESTING": True, "SECRET_KEY": "sponsor-context-test-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False, "MAIL_DELIVERY_MODE": "memory",
        "OCR_PRIVATE_DIR": str(tmp_path / "files"),
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


def post(client, path, data):
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    return client.post(path, json=data, headers={"X-CSRF-Token": csrf})


def patch(client, path, data):
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    return client.patch(path, json=data, headers={"X-CSRF-Token": csrf})


def login(client, email):
    response = post(client, "/api/auth/login", {"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.json


def get_detail(client, application_id):
    return client.get(f"/api/admin/applications/{application_id}")


def approve(client, application_id):
    return post(client, f"/api/admin/applications/{application_id}/decision", {
        "decision": "APPROVED", "reason": "Manual family sponsor review completed",
    })


@pytest.fixture()
def sample(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        owner_home = Household(flat=flat, label="Owner household")
        tenant_home = Household(flat=flat, label="Tenant household")
        db.session.add_all([owner_home, tenant_home])
        db.session.flush()

        people = {}
        for key, name, role in (
            ("admin", "Society Admin", PermissionRole.SOCIETY_ADMIN),
            ("owner", "Rahul Sharma", PermissionRole.RESIDENT),
            ("tenant", "Amit Kumar", PermissionRole.RESIDENT),
            ("family", "Priya Sharma", PermissionRole.APPLICANT),
            ("family2", "Sneha Kumar", PermissionRole.APPLICANT),
            ("outsider", "Unrelated Resident", PermissionRole.RESIDENT),
        ):
            person = User(email=f"{key}@example.test", display_name=name,
                          password_hash=generate_password_hash(PASSWORD),
                          account_status=AccountStatus.ACTIVE,
                          email_verified_at=datetime.now(timezone.utc))
            db.session.add(person)
            db.session.flush()
            db.session.add(RoleAssignment(user_id=person.id, role=role))
            people[key] = person
        db.session.flush()
        owner = Membership(user_id=people["owner"].id, household_id=owner_home.id,
                           category=ResidentCategory.OWNER, status=MembershipStatus.ACTIVE,
                           valid_from=date.today() - timedelta(days=10))
        tenant = Membership(user_id=people["tenant"].id, household_id=tenant_home.id,
                            category=ResidentCategory.TENANT, status=MembershipStatus.ACTIVE,
                            valid_from=date.today() - timedelta(days=10),
                            valid_until=date.today() + timedelta(days=90))
        db.session.add_all([owner, tenant])
        db.session.flush()
        # Two different sponsors in two households, but the SAME flat.
        family_owner = MembershipApplication(
            user_id=people["family"].id, flat_id=flat.id, household_id=owner_home.id,
            sponsor_membership_id=owner.id, category=ResidentCategory.FAMILY_MEMBER,
            status=ApplicationStatus.PENDING, relationship_to_sponsor="SPOUSE",
            submitted_at=datetime.now(timezone.utc),
        )
        family_tenant = MembershipApplication(
            user_id=people["family2"].id, flat_id=flat.id, household_id=tenant_home.id,
            sponsor_membership_id=tenant.id, category=ResidentCategory.FAMILY_MEMBER,
            status=ApplicationStatus.PENDING, relationship_to_sponsor="CHILD",
            submitted_at=datetime.now(timezone.utc),
        )
        db.session.add_all([family_owner, family_tenant])
        db.session.commit()
        return {
            "owner": str(owner.id), "tenant": str(tenant.id),
            "owner_app": str(family_owner.id), "tenant_app": str(family_tenant.id),
            "owner_home": str(owner_home.id), "tenant_home": str(tenant_home.id),
            "flat": str(flat.id), "owner_user": str(people["owner"].id),
        }


def test_owner_sponsor_context_correct_and_private(client, sample):
    login(client, "admin@example.test")
    res = get_detail(client, sample["owner_app"])
    assert res.status_code == 200, res.json
    ctx = res.json["sponsor_context"]
    assert ctx == {
        "membership_id": sample["owner"], "display_name": "Rahul Sharma",
        "category": "OWNER", "membership_status": "ACTIVE",
        "household_id": sample["owner_home"], "household_label": "Owner household",
        "flat_id": sample["flat"], "eligible_to_sponsor": True,
        "valid_from": (date.today() - timedelta(days=10)).isoformat(),
        "valid_until": None,
    }
    assert res.json["application"]["relationship_to_sponsor"] == "SPOUSE"
    for forbidden in ("email", "phone", "occupation", "date_of_birth", "password", "token"):
        assert forbidden not in ctx


def test_tenant_sponsor_never_substituted_with_owner(client, sample):
    login(client, "admin@example.test")
    res = get_detail(client, sample["tenant_app"])
    assert res.status_code == 200
    assert res.json["sponsor_context"]["membership_id"] == sample["tenant"]
    assert res.json["sponsor_context"]["display_name"] == "Amit Kumar"
    assert res.json["sponsor_context"]["household_id"] == sample["tenant_home"]
    assert res.json["sponsor_context"]["category"] == "TENANT"


def test_wrong_household_same_flat_is_never_eligible(client, app, sample):
    with app.app_context():
        family = db.session.get(MembershipApplication, UUID(sample["tenant_app"]))
        family.household_id = UUID(sample["owner_home"])
        db.session.commit()
    login(client, "admin@example.test")
    res = get_detail(client, sample["tenant_app"])
    assert res.status_code == 200
    ctx = res.json["sponsor_context"]
    assert ctx["membership_id"] == sample["tenant"]
    assert ctx["household_id"] == sample["tenant_home"]
    assert ctx["eligible_to_sponsor"] is False
    assert approve(client, sample["tenant_app"]).json["error"]["code"] == "SPONSOR_INELIGIBLE"


def test_missing_sponsor_on_draft_yields_null_context(client, app, sample):
    with app.app_context():
        family = db.session.get(MembershipApplication, UUID(sample["tenant_app"]))
        family.status = ApplicationStatus.DRAFT
        family.sponsor_membership_id = None
        db.session.commit()
    login(client, "admin@example.test")
    res = get_detail(client, sample["tenant_app"])
    assert res.status_code == 200
    assert res.json["sponsor_context"] is None
    assert res.json["application"]["category"] == "FAMILY_MEMBER"
    assert approve(client, sample["tenant_app"]).status_code == 409


@pytest.mark.parametrize("status", [MembershipStatus.SUSPENDED, MembershipStatus.REVOKED, MembershipStatus.EXPIRED])
def test_inactive_sponsor_visible_but_not_eligible(client, app, sample, status):
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(sample["owner"]))
        sponsor.status = status
        db.session.commit()
    login(client, "admin@example.test")
    res = get_detail(client, sample["owner_app"])
    assert res.status_code == 200
    assert res.json["sponsor_context"]["membership_status"] == status.value
    assert res.json["sponsor_context"]["eligible_to_sponsor"] is False
    denied = approve(client, sample["owner_app"])
    assert denied.status_code == 409
    assert denied.json["error"]["code"] == "SPONSOR_INELIGIBLE"


def test_expired_validity_date_with_active_db_status_denies_approval(client, app, sample):
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(sample["tenant"]))
        sponsor.valid_until = date.today() - timedelta(days=1)
        db.session.commit()
    login(client, "admin@example.test")
    detail = get_detail(client, sample["tenant_app"])
    assert detail.json["sponsor_context"]["membership_status"] == "ACTIVE"
    assert detail.json["sponsor_context"]["eligible_to_sponsor"] is False
    assert approve(client, sample["tenant_app"]).status_code == 409


def test_unverified_sponsor_account_not_eligible(client, app, sample):
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(sample["owner"]))
        sponsor.user.email_verified_at = None
        db.session.commit()
    login(client, "admin@example.test")
    assert get_detail(client, sample["owner_app"]).json["sponsor_context"]["eligible_to_sponsor"] is False
    assert approve(client, sample["owner_app"]).status_code == 409


def test_sponsor_role_revoked_denies_approval(client, app, sample):
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(sample["owner"]))
        grant = db.session.scalar(select(RoleAssignment).where(
            RoleAssignment.user_id == sponsor.user_id,
            RoleAssignment.role == PermissionRole.RESIDENT,
            RoleAssignment.revoked_at.is_(None)))
        grant.revoked_at = datetime.now(timezone.utc)
        db.session.commit()
    login(client, "admin@example.test")
    assert get_detail(client, sample["owner_app"]).json["sponsor_context"]["eligible_to_sponsor"] is False
    assert approve(client, sample["owner_app"]).status_code == 409


def test_nonadmin_cannot_get_sponsor_context(client, sample):
    assert get_detail(client, sample["owner_app"]).status_code == 401
    login(client, "owner@example.test")
    assert get_detail(client, sample["owner_app"]).status_code == 403


def test_original_applicant_name_mismatch_preserved_with_sponsor_advisory(client, app, sample):
    with app.app_context():
        application = db.session.get(MembershipApplication, UUID(sample["owner_app"]))
        doc = VerificationDocument(
            application_id=application.id, uploaded_by_user_id=application.user_id,
            document_type=DocumentType.OCCUPANCY_LETTER,
            original_filename="fictional.png", storage_key="synthetic/letter.png",
            mime_type="image/png", file_size_bytes=500, sha256_checksum="a" * 64,
        )
        db.session.add(doc)
        db.session.flush()
        db.session.add(OCRResult(
            document_id=doc.id, status=OCRStatus.COMPLETED, engine_name="surya",
            extracted_fields={"resident_name": "Rahul Sharma"},
            comparison_results={"resident_name": {
                "entered": "Priya Sharma", "extracted": "Rahul Sharma", "status": "MISMATCH",
            }}, warnings=["resident_name: mismatch; manual review required"],
        ))
        db.session.commit()
    login(client, "admin@example.test")
    res = get_detail(client, sample["owner_app"])
    assert res.status_code == 200, res.json
    ocr = res.json["application"]["documents"][0]["latest_ocr"]
    assert ocr["comparisons"]["resident_name"]["status"] == "MISMATCH"
    assert ocr["sponsor_name_advisory"]["status"] == "MATCHES_SPONSOR_NAME"
    assert ocr["sponsor_name_advisory"]["advisory_only"] is True
    # A name match is advisory. Original review warnings are not erased.
    assert ocr["warnings"]
    assert approve(client, sample["owner_app"]).status_code == 200  # human admin decision


def test_live_revalidation_does_not_trust_previous_get(client, app, sample):
    login(client, "admin@example.test")
    assert get_detail(client, sample["owner_app"]).json["sponsor_context"]["eligible_to_sponsor"]
    # Another admin revokes sponsor between review GET and decision POST.
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(sample["owner"]))
        sponsor.status = MembershipStatus.REVOKED
        db.session.commit()
    denied = approve(client, sample["owner_app"])
    assert denied.status_code == 409
    assert denied.json["error"]["code"] == "SPONSOR_INELIGIBLE"
    with app.app_context():
        application = db.session.get(MembershipApplication, UUID(sample["owner_app"]))
        assert application.status == ApplicationStatus.PENDING
        assert application.resulting_membership_id is None
        assert not db.session.scalars(select(AuditLog).where(
            AuditLog.action == "APPLICATION_APPROVED")).all()


def test_human_approval_creates_member_only_if_eligible(client, app, sample):
    login(client, "admin@example.test")
    response = approve(client, sample["tenant_app"])
    assert response.status_code == 200, response.json
    assert response.json["application"]["status"] == "APPROVED"
    with app.app_context():
        item = db.session.get(MembershipApplication, UUID(sample["tenant_app"]))
        member = db.session.get(Membership, item.resulting_membership_id)
        assert member.sponsor_membership_id == UUID(sample["tenant"])
        assert member.household_id == UUID(sample["tenant_home"])
        assert member.category == ResidentCategory.FAMILY_MEMBER


def test_application_flat_must_equal_sponsor_household_flat(client, app, sample):
    with app.app_context():
        tower = db.session.scalar(select(Tower).where(Tower.name == "B"))
        other_flat = Flat(tower=tower, flat_number="403", floor_number=4)
        db.session.add(other_flat)
        db.session.flush()
        family = db.session.get(MembershipApplication, UUID(sample["owner_app"]))
        family.flat_id = other_flat.id
        db.session.commit()
    login(client, "admin@example.test")
    ctx = get_detail(client, sample["owner_app"]).json["sponsor_context"]
    assert ctx["membership_id"] == sample["owner"]
    assert ctx["eligible_to_sponsor"] is False
    assert approve(client, sample["owner_app"]).status_code == 409


def test_corrupt_relationship_is_not_approved(client, app, sample):
    # Normal invitation/application APIs reject this value at input time;
    # approval also fails closed if a legacy/imported row contains it.
    with app.app_context():
        family = db.session.get(MembershipApplication, UUID(sample["owner_app"]))
        family.relationship_to_sponsor = "NOT_A_RELATIONSHIP"
        db.session.commit()
    login(client, "admin@example.test")
    response = approve(client, sample["owner_app"])
    assert response.status_code == 409
    assert response.json["error"]["code"] == "INVALID_FAMILY_RELATIONSHIP"
