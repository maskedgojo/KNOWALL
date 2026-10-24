"""New family self-onboarding policy: integration tests using existing Flask fixtures."""
from datetime import timedelta
from io import BytesIO
from uuid import UUID

from PIL import Image
import pytest
from sqlalchemy import select

from test_onboarding_api import app, client, sample, login, post, latest_token, row_uuid
from app.extensions import db
from app.modules.identity.models import (
    AuditLog, Household, Invitation, MemberEvidenceRequest, Membership,
    MembershipApplication, MembershipStatus, PermissionRole, ResidentCategory,
    RoleAssignment,
)
from app.modules.identity.models.user import utc_now


def invite(app, sample, *, email="new@example.test", sponsor_email="owner@example.test", relationship="CHILD"):
    owner = app.test_client(); login(owner, sponsor_email)
    response = post(owner, "/api/invitations", {
        "flat_id": sample["flat"], "household_id": sample["home"],
        "sponsor_membership_id": sample["sponsor"], "category": "FAMILY_MEMBER",
        "email": email, "relationship_to_sponsor": relationship,
    })
    assert response.status_code == 201, response.json
    return latest_token(app)


def accept(app, token, *, email="new@example.test", relationship="CHILD"):
    recipient = app.test_client(); login(recipient, email)
    return recipient, post(recipient, "/api/invitations/accept", {
        "token": token, "relationship_to_sponsor": relationship,
        "declared_current_occupant": True,
    })


def test_family_acceptance_creates_membership_and_role_no_application(app, sample):
    token = invite(app, sample)
    recipient, result = accept(app, token)
    assert result.status_code == 201, result.json
    assert result.json["application"] is None
    assert result.json["outcome"] == "FAMILY_MEMBERSHIP_ACTIVATED"
    member = result.json["membership"]
    assert member["household_id"] == sample["home"]
    assert member["sponsor_membership_id"] == sample["sponsor"]
    assert member["relationship_to_sponsor"] == "CHILD"
    assert member["is_current_occupant"] is None
    assert member["declared_current_occupant"] is True
    assert recipient.get("/api/me/access").json["verified_resident"] is True
    with app.app_context():
        assert db.session.query(MembershipApplication).filter_by(category=ResidentCategory.FAMILY_MEMBER).count() == 0
        assert db.session.query(AuditLog).filter_by(action="FAMILY_MEMBERSHIP_AUTO_ACTIVATED").count() == 1
        assert db.session.query(RoleAssignment).filter_by(role=PermissionRole.RESIDENT, revoked_at=None).count() >= 2


def test_wrong_recipient_cannot_claim_token(app, sample):
    token = invite(app, sample)
    wrong, result = accept(app, token, email="outsider@example.test")
    assert result.status_code == 403
    assert accept(app, token)[1].status_code == 201


def test_unverified_recipient_is_rejected(app, sample):
    token = invite(app, sample, email="unverified@example.test")
    recipient, result = accept(app, token, email="unverified@example.test")
    assert result.status_code == 403
    assert result.json["error"]["code"] == "EMAIL_VERIFICATION_REQUIRED"


def test_family_acceptance_requires_a_relationship(app, sample):
    token = invite(app, sample, relationship=None)
    recipient = app.test_client(); login(recipient, "new@example.test")
    assert post(recipient, "/api/invitations/accept", {"token": token}).status_code == 400
    assert post(recipient, "/api/invitations/accept", {
        "token": token, "relationship_to_sponsor": "SPOUSE"}).status_code == 201


@pytest.mark.parametrize("status", [MembershipStatus.SUSPENDED, MembershipStatus.REVOKED])
def test_inactive_sponsor_rejects_family(app, sample, status):
    token = invite(app, sample)
    with app.app_context():
        sponsor = db.session.get(Membership, row_uuid(sample["sponsor"]))
        sponsor.status = status; db.session.commit()
    assert accept(app, token)[1].status_code == 409


def test_expired_sponsor_rejects_family(app, sample):
    token = invite(app, sample)
    with app.app_context():
        sponsor = db.session.get(Membership, row_uuid(sample["sponsor"]))
        sponsor.valid_until = utc_now().date() - timedelta(days=1)
        db.session.commit()
    assert accept(app, token)[1].status_code == 409


def test_invitation_household_rebound_rejected(app, sample):
    token = invite(app, sample)
    with app.app_context():
        inv = db.session.scalar(select(Invitation))
        inv.household_id = row_uuid(sample["other_home"])
        db.session.commit()
    assert accept(app, token)[1].status_code == 409


def test_reused_invitation_does_not_create_multiple_memberships(app, sample):
    token = invite(app, sample)
    recipient, first = accept(app, token)
    assert first.status_code == 201
    assert post(recipient, "/api/invitations/accept", {
        "token": token, "relationship_to_sponsor": "CHILD"}).status_code in (400, 409)
    with app.app_context():
        assert db.session.query(Membership).filter_by(category=ResidentCategory.FAMILY_MEMBER).count() == 1


def test_expired_invitation_rejected_and_unconsumed(app, sample):
    token = invite(app, sample)
    with app.app_context():
        inv = db.session.scalar(select(Invitation))
        inv.created_at = utc_now() - timedelta(days=9)
        inv.expires_at = utc_now() - timedelta(days=1)
        db.session.commit()
    assert accept(app, token)[1].status_code == 400


def test_suspending_sponsor_blocks_existing_family_access(app, sample):
    token = invite(app, sample)
    recipient, result = accept(app, token)
    assert result.status_code == 201
    with app.app_context():
        sponsor = db.session.get(Membership, row_uuid(sample["sponsor"]))
        sponsor.status = MembershipStatus.SUSPENDED
        db.session.commit()
    assert recipient.get("/api/me/access").json["verified_resident"] is False
    assert recipient.get("/api/me/memberships").json["memberships"][0]["access_state"] == "SPONSOR_INELIGIBLE"


def test_owner_tenant_still_create_draft(app, sample):
    admin = app.test_client(); login(admin, "admin@example.test")
    invite_response = post(admin, "/api/invitations", {
        "flat_id": sample["flat"], "category": "TENANT", "email": "new@example.test"})
    assert invite_response.status_code == 201
    token = latest_token(app)
    recipient = app.test_client(); login(recipient, "new@example.test")
    result = post(recipient, "/api/invitations/accept", {"token": token})
    assert result.status_code == 201
    assert result.json["outcome"] == "APPLICATION_DRAFT_CREATED"
    assert result.json["application"]["status"] == "DRAFT"
    assert result.json["membership"] is None


def test_household_directory_requires_admin_and_shows_family(app, sample):
    token = invite(app, sample)
    recipient, result = accept(app, token)
    assert result.status_code == 201
    assert recipient.get("/api/admin/households").status_code == 403
    admin = app.test_client(); login(admin, "admin@example.test")
    directory = admin.get("/api/admin/households")
    assert directory.status_code == 200, directory.json
    house = next(h for h in directory.json["households"] if h["household_id"] == sample["home"])
    family = next(m for m in house["members"] if m["category"] == "FAMILY_MEMBER")
    assert family["sponsor_membership_id"] == sample["sponsor"]
    assert family["sponsor_display_name"] == "Owner"
    assert "email" not in family and "date_of_birth" not in family


def test_evidence_request_review_and_no_automatic_suspension(app, sample, tmp_path):
    app.config["OCR_PRIVATE_DIR"] = str(tmp_path / "member-evidence")
    token = invite(app, sample)
    recipient, accepted = accept(app, token)
    assert accepted.status_code == 201
    membership_id = accepted.json["membership"]["id"]
    admin = app.test_client(); login(admin, "admin@example.test")
    result = post(admin, f"/api/admin/memberships/{membership_id}/evidence-requests", {
        "reason": "Residence relationship details require additional clarification.",
        "evidence_needed": "Please upload an appropriate non-sensitive residence confirmation."})
    assert result.status_code == 201, result.json
    eid = result.json["request"]["id"]
    assert result.json["request"]["status"] == "REQUESTED"
    assert recipient.get("/api/me/access").json["verified_resident"] is True
    assert recipient.get("/api/me/evidence-requests").json["requests"][0]["id"] == eid
    assert recipient.get(f"/api/member-evidence/{eid}/file").status_code == 404
    image = BytesIO(); Image.new("RGB", (16, 16), "white").save(image, "PNG"); image.seek(0)
    response = recipient.post(f"/api/me/evidence-requests/{eid}/upload",
        data={"file": (image, "support.png")}, content_type="multipart/form-data",
        headers={"X-CSRF-Token": recipient.get("/api/auth/csrf").json["csrf_token"]})
    assert response.status_code == 200, response.json
    assert response.json["request"]["status"] == "SUBMITTED"
    outsider = app.test_client(); login(outsider, "outsider@example.test")
    assert outsider.get(f"/api/member-evidence/{eid}/file").status_code == 404
    assert admin.get(f"/api/member-evidence/{eid}/file").status_code == 200
    decision = post(admin, f"/api/admin/evidence-requests/{eid}/resolve", {
        "decision": "ACCEPTED", "review_note": "Reviewed sufficient evidence."})
    assert decision.status_code == 200, decision.json
    assert decision.json["request"]["retention_delete_after"] is not None
    assert recipient.get("/api/me/access").json["verified_resident"] is True


def test_evidence_request_forbidden_to_resident(app, sample):
    recipient = app.test_client(); login(recipient, "new@example.test")
    assert post(recipient, f"/api/admin/memberships/{sample['sponsor']}/evidence-requests", {
        "reason": "I have a test reason", "evidence_needed": "A document"}).status_code == 403
    assert recipient.get("/api/admin/evidence-requests").status_code == 403


def test_tenant_sponsor_kept_separate_from_owner_same_flat(app, sample):
    from werkzeug.security import generate_password_hash
    from app.modules.identity.models import User, AccountStatus
    with app.app_context():
        original_flat = db.session.get(Household, row_uuid(sample["home"])).flat
        tenant_home = Household(flat=original_flat, label="Tenant household")
        tenant_user = User(display_name="Tenant Sponsor", email="tenant-sponsor@example.test",
            password_hash=generate_password_hash("ValidPasswordForTests2026!"),
            account_status=AccountStatus.ACTIVE, email_verified_at=utc_now())
        db.session.add_all([tenant_home, tenant_user]); db.session.flush()
        db.session.add(RoleAssignment(user_id=tenant_user.id, role=PermissionRole.RESIDENT))
        tenant = Membership(user_id=tenant_user.id, household_id=tenant_home.id,
            category=ResidentCategory.TENANT, status=MembershipStatus.ACTIVE,
            valid_from=utc_now().date() - timedelta(days=1))
        db.session.add(tenant); db.session.commit()
        th_id, ts_id = str(tenant_home.id), str(tenant.id)
    inviter = app.test_client(); login(inviter, "tenant-sponsor@example.test")
    sent = post(inviter, "/api/invitations", {
        "flat_id": sample["flat"], "household_id": th_id,
        "sponsor_membership_id": ts_id,
        "category": "FAMILY_MEMBER", "email": "new@example.test",
        "relationship_to_sponsor": "SPOUSE"})
    assert sent.status_code == 201, sent.json
    _, activated = accept(app, latest_token(app), relationship="SPOUSE")
    assert activated.status_code == 201, activated.json
    assert activated.json["membership"]["sponsor_membership_id"] == ts_id
    assert activated.json["membership"]["household_id"] == th_id
    admin = app.test_client(); login(admin, "admin@example.test")
    directory = admin.get("/api/admin/households").json["households"]
    owner_home = next(h for h in directory if h["household_id"] == sample["home"])
    tenant_home_data = next(h for h in directory if h["household_id"] == th_id)
    assert not any(m["category"] == "FAMILY_MEMBER" for m in owner_home["members"])
    family = next(m for m in tenant_home_data["members"] if m["category"] == "FAMILY_MEMBER")
    assert family["sponsor_display_name"] == "Tenant Sponsor"


def test_pending_legacy_family_application_is_not_auto_activated(app, sample):
    from app.modules.identity.models import User, ApplicationStatus
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "new@example.test"))
        old = MembershipApplication(user_id=user.id, flat_id=row_uuid(sample["flat"]),
            household_id=row_uuid(sample["home"]), sponsor_membership_id=row_uuid(sample["sponsor"]),
            category=ResidentCategory.FAMILY_MEMBER, status=ApplicationStatus.PENDING,
            relationship_to_sponsor="CHILD", submitted_at=utc_now())
        db.session.add(old); db.session.commit()
        old_id = old.id
    token = invite(app, sample)
    assert accept(app, token)[1].status_code == 409
    with app.app_context():
        old = db.session.get(MembershipApplication, old_id)
        assert old.status == ApplicationStatus.PENDING
        assert old.resulting_membership_id is None


def test_evidence_resident_cannot_submit_to_another_member(app, sample):
    admin = app.test_client(); login(admin, "admin@example.test")
    created = post(admin, f"/api/admin/memberships/{sample['sponsor']}/evidence-requests", {
        "reason": "Admin has identified a genuine data discrepancy.",
        "evidence_needed": "Any suitable evidence confirming occupancy."})
    assert created.status_code == 201
    entry_id = created.json["request"]["id"]
    outsider = app.test_client(); login(outsider, "outsider@example.test")
    photo = BytesIO(); Image.new("RGB", (12, 12), "white").save(photo, "PNG"); photo.seek(0)
    response = outsider.post(f"/api/me/evidence-requests/{entry_id}/upload",
        data={"file": (photo, "x.png")}, content_type="multipart/form-data",
        headers={"X-CSRF-Token": outsider.get("/api/auth/csrf").json["csrf_token"]})
    assert response.status_code == 404


def test_evidence_request_cannot_approve_pending_upload_or_create_duplicate(app, sample):
    admin = app.test_client(); login(admin, "admin@example.test")
    url = f"/api/admin/memberships/{sample['sponsor']}/evidence-requests"
    payload = {"reason": "Membership inconsistency needs review.",
               "evidence_needed": "Suitable supporting resident letter."}
    first = post(admin, url, payload)
    assert first.status_code == 201
    assert post(admin, url, payload).status_code == 409
    id = first.json["request"]["id"]
    assert post(admin, f"/api/admin/evidence-requests/{id}/resolve", {
        "decision": "ACCEPTED", "review_note": "No document uploaded."}).status_code == 409
    assert post(admin, f"/api/admin/evidence-requests/{id}/resolve", {
        "decision": "CANCELLED", "review_note": "No longer needed."}).status_code == 200
    assert post(admin, url, payload).status_code == 201
