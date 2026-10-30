"""Phase 8 API integration tests. Synthetic users/documents; no real OCR inference."""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, ApplicationReview, ApplicationStatus, AuditLog, DocumentType,
    Flat, Household, Membership, MembershipApplication, MembershipStatus,
    OCRResult, OCRStatus, PermissionRole, ResidentCategory, RoleAssignment,
    Tower, User, VerificationDocument,
)

PASSWORD = "ValidPasswordForTests2026!"


@pytest.fixture()
def app(tmp_path):
    instance = create_app({
        "TESTING": True, "SECRET_KEY": "phase8-test-secret",
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


def token(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def post(client, url, body):
    return client.post(url, json=body, headers={"X-CSRF-Token": token(client)})


def patch(client, url, body):
    return client.patch(url, json=body, headers={"X-CSRF-Token": token(client)})


def login(client, email):
    result = post(client, "/api/auth/login", {"email": email, "password": PASSWORD})
    assert result.status_code == 200, result.json


def logout(client):
    assert post(client, "/api/auth/logout", {}).status_code == 200


@pytest.fixture()
def seeded(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        other_flat = Flat(tower=tower, flat_number="403", floor_number=4)
        db.session.add_all([flat, other_flat])
        db.session.flush()
        home = Household(flat=flat, label="Sponsor family")
        db.session.add(home)
        db.session.flush()
        people = {}
        for key, role in [
            ("admin", PermissionRole.SOCIETY_ADMIN),
            ("applicant", PermissionRole.APPLICANT),
            ("owner", PermissionRole.RESIDENT),
            ("outsider", PermissionRole.APPLICANT),
            ("family", PermissionRole.APPLICANT),
        ]:
            person = User(
                email=f"{key}@example.test", display_name=key.title(),
                password_hash=generate_password_hash(PASSWORD),
                account_status=AccountStatus.ACTIVE,
                email_verified_at=datetime.now(timezone.utc),
            )
            db.session.add(person)
            db.session.flush()
            db.session.add(RoleAssignment(user_id=person.id, role=role))
            people[key] = person
        sponsor = Membership(
            user_id=people["owner"].id, household_id=home.id,
            category=ResidentCategory.OWNER, status=MembershipStatus.ACTIVE,
            valid_from=date.today() - timedelta(days=3),
        )
        db.session.add(sponsor)
        db.session.flush()
        owner_app = MembershipApplication(
            user_id=people["applicant"].id, flat_id=flat.id,
            category=ResidentCategory.OWNER, status=ApplicationStatus.PENDING,
            submitted_at=datetime.now(timezone.utc),
        )
        family_app = MembershipApplication(
            user_id=people["family"].id, flat_id=flat.id,
            household_id=home.id, sponsor_membership_id=sponsor.id,
            category=ResidentCategory.FAMILY_MEMBER, status=ApplicationStatus.PENDING,
            submitted_at=datetime.now(timezone.utc),
        )
        tenant_app = MembershipApplication(
            user_id=people["outsider"].id, flat_id=flat.id,
            category=ResidentCategory.TENANT, status=ApplicationStatus.PENDING,
            requested_valid_from=date.today(),
            requested_valid_until=date.today()+timedelta(days=120),
        )
        db.session.add_all([owner_app, family_app, tenant_app])
        db.session.commit()
        return {"owner_app": str(owner_app.id), "family_app": str(family_app.id),
                "tenant_app": str(tenant_app.id), "home": str(home.id),
                "sponsor": str(sponsor.id), "admin": str(people["admin"].id),
                "flat": str(flat.id), "other_flat": str(other_flat.id),
                "applicant": str(people["applicant"].id)}


def evidence(app, application_id, warnings=None, failed=False):
    with app.app_context():
        app_id = UUID(application_id)
        application = db.session.get(MembershipApplication, app_id)
        doc = VerificationDocument(
            application_id=app_id, uploaded_by_user_id=application.user_id,
            document_type=DocumentType.OCCUPANCY_LETTER,
            original_filename="fictional.png", storage_key=f"review/{application_id}.png",
            mime_type="image/png", file_size_bytes=50, sha256_checksum="a" * 64,
        )
        db.session.add(doc)
        db.session.flush()
        if warnings is not None or failed:
            db.session.add(OCRResult(
                document_id=doc.id, engine_name="surya",
                status=OCRStatus.FAILED if failed else OCRStatus.COMPLETED,
                warnings=warnings or [],
            ))
        db.session.commit()


def decision(client, ident, name="APPROVED", **kwargs):
    return post(client, f"/api/admin/applications/{ident}/decision", {
        "decision": name, **kwargs,
    })


def test_requires_login_and_admin(client, seeded):
    assert client.get("/api/admin/applications").status_code == 401
    login(client, "applicant@example.test")
    assert client.get("/api/admin/applications").status_code == 403
    assert decision(client, seeded["owner_app"]).status_code == 403


def test_admin_queue_and_detail(client, seeded):
    login(client, "admin@example.test")
    result = client.get("/api/admin/applications?status=PENDING&limit=2&offset=0")
    assert result.status_code == 200
    assert result.json["pagination"]["total"] == 3
    assert len(result.json["applications"]) == 2
    detail = client.get(f'/api/admin/applications/{seeded["owner_app"]}')
    assert detail.status_code == 200
    assert detail.json["application"]["applicant"]["email"] == "applicant@example.test"
    assert detail.json["application"]["documents"] == []


@pytest.mark.parametrize("query", ["?status=NOT_REAL", "?limit=0", "?limit=101", "?offset=-1"])
def test_queue_validation(client, seeded, query):
    login(client, "admin@example.test")
    assert client.get("/api/admin/applications" + query).status_code == 400


def test_cannot_approve_owner_without_document(client, seeded):
    login(client, "admin@example.test")
    result = decision(client, seeded["owner_app"], document_reviewed=True)
    assert result.status_code == 409
    assert result.json["error"]["code"] == "DOCUMENT_REQUIRED"


def test_cannot_approve_owner_without_manual_confirmation(client, app, seeded):
    evidence(app, seeded["owner_app"])
    login(client, "admin@example.test")
    assert decision(client, seeded["owner_app"]).status_code == 409


def test_ocr_warnings_need_acknowledgment(client, app, seeded):
    evidence(app, seeded["owner_app"], warnings=["Flat mismatch"])
    login(client, "admin@example.test")
    assert decision(client, seeded["owner_app"], document_reviewed=True).status_code == 409
    result = decision(client, seeded["owner_app"], document_reviewed=True,
                      acknowledge_ocr_warnings=True)
    assert result.status_code == 200, result.json


def test_owner_approval_creates_membership_role_review_audit(client, app, seeded):
    evidence(app, seeded["owner_app"])
    login(client, "admin@example.test")
    result = decision(client, seeded["owner_app"], document_reviewed=True,
                      acknowledge_ocr_warnings=True)
    assert result.status_code == 200, result.json
    data = result.json["application"]
    assert data["status"] == "APPROVED"
    assert data["resulting_membership_id"]
    with app.app_context():
        app_obj = db.session.get(MembershipApplication, UUID(seeded["owner_app"]))
        member = db.session.get(Membership, app_obj.resulting_membership_id)
        assert member.category == ResidentCategory.OWNER
        assert member.household.flat_id == UUID(seeded["flat"])
        assert db.session.scalar(select(RoleAssignment).where(
            RoleAssignment.user_id == app_obj.user_id,
            RoleAssignment.role == PermissionRole.RESIDENT,
            RoleAssignment.revoked_at.is_(None),
        )) is not None
        assert len(db.session.scalars(select(ApplicationReview).where(
            ApplicationReview.application_id == app_obj.id)).all()) == 1
        assert db.session.scalar(select(AuditLog).where(
            AuditLog.action == "APPLICATION_APPROVED")) is not None


def test_duplicate_decision_does_not_duplicate_memberships(client, app, seeded):
    evidence(app, seeded["owner_app"])
    login(client, "admin@example.test")
    assert decision(client, seeded["owner_app"], document_reviewed=True).status_code == 200
    assert decision(client, seeded["owner_app"], document_reviewed=True).status_code == 409
    with app.app_context():
        assert len(db.session.scalars(select(Membership).where(
            Membership.user_id == UUID(seeded["applicant"]))).all()) == 1


def test_rejection_requires_reason_and_retains_history(client, app, seeded):
    login(client, "admin@example.test")
    assert decision(client, seeded["owner_app"], "REJECTED").status_code == 400
    result = decision(client, seeded["owner_app"], "REJECTED", reason="The evidence is not acceptable")
    assert result.status_code == 200
    assert result.json["application"]["status"] == "REJECTED"
    with app.app_context():
        obj = db.session.get(MembershipApplication, UUID(seeded["owner_app"]))
        assert obj.resulting_membership_id is None


def test_correction_does_not_create_membership(client, app, seeded):
    login(client, "admin@example.test")
    result = decision(client, seeded["owner_app"], "NEEDS_CORRECTION", reason="Upload a clearer letter")
    assert result.status_code == 200
    assert result.json["application"]["status"] == "NEEDS_CORRECTION"
    with app.app_context():
        obj = db.session.get(MembershipApplication, UUID(seeded["owner_app"]))
        assert obj.resulting_membership_id is None


def test_family_requires_live_sponsor(client, app, seeded):
    login(client, "admin@example.test")
    with app.app_context():
        sponsor = db.session.get(Membership, UUID(seeded["sponsor"]))
        sponsor.status = MembershipStatus.SUSPENDED
        db.session.commit()
    assert decision(client, seeded["family_app"]).status_code == 409


def test_family_approval_works_without_default_document(client, seeded):
    login(client, "admin@example.test")
    result = decision(client, seeded["family_app"])
    assert result.status_code == 200, result.json
    assert result.json["application"]["resulting_membership_id"]


def test_tenant_approval_is_dated(client, app, seeded):
    evidence(app, seeded["tenant_app"])
    login(client, "admin@example.test")
    result = decision(client, seeded["tenant_app"], document_reviewed=True)
    assert result.status_code == 200, result.json
    with app.app_context():
        item = db.session.get(MembershipApplication, UUID(seeded["tenant_app"]))
        member = db.session.get(Membership, item.resulting_membership_id)
        assert member.valid_until is not None
        assert member.category == ResidentCategory.TENANT


def test_membership_suspend_reactivate_revoke(client, app, seeded):
    login(client, "admin@example.test")
    ident = seeded["sponsor"]
    suspended = patch(client, f"/api/admin/memberships/{ident}/status", {
        "status": "SUSPENDED", "reason": "Administrative review required",
    })
    assert suspended.status_code == 200, suspended.json
    assert suspended.json["membership"]["status"] == "SUSPENDED"
    active = patch(client, f"/api/admin/memberships/{ident}/status", {
        "status": "ACTIVE", "reason": "Review completed",
    })
    assert active.status_code == 200, active.json
    revoked = patch(client, f"/api/admin/memberships/{ident}/status", {
        "status": "REVOKED", "reason": "Membership ended",
    })
    assert revoked.status_code == 200, revoked.json
    assert patch(client, f"/api/admin/memberships/{ident}/status", {
        "status": "ACTIVE", "reason": "Invalid reopening",
    }).status_code == 409


def test_member_list_and_audit_protected(client, seeded):
    login(client, "applicant@example.test")
    assert client.get("/api/admin/memberships").status_code == 403
    logout(client)
    login(client, "admin@example.test")
    assert client.get("/api/admin/memberships").status_code == 200
    assert client.get("/api/admin/audit-logs").status_code == 200


def test_missing_object_error(client, seeded):
    from uuid import uuid4
    login(client, "admin@example.test")
    assert client.get(f"/api/admin/applications/{uuid4()}").status_code == 404
    assert patch(client, f"/api/admin/memberships/{uuid4()}/status", {
        "status": "SUSPENDED", "reason": "Not a real record",
    }).status_code == 404


def test_review_rejects_missing_csrf(client, seeded):
    login(client, "admin@example.test")
    response = client.post(f'/api/admin/applications/{seeded["owner_app"]}/decision',
                           json={"decision": "REJECTED", "reason": "Invalid"})
    assert response.status_code == 403


def test_admin_cannot_review_own_application(client, app, seeded):
    with app.app_context():
        own_application = MembershipApplication(
            user_id=UUID(seeded["admin"]), flat_id=UUID(seeded["flat"]),
            category=ResidentCategory.OWNER, status=ApplicationStatus.PENDING,
        )
        db.session.add(own_application)
        db.session.commit()
        application_id = str(own_application.id)
    login(client, "admin@example.test")
    assert decision(client, application_id, "REJECTED", reason="Not permitted").status_code == 403
