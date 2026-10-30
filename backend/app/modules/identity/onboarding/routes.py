"""Phase 6: safe, single-society resident applications and bound invitations.

Owner/Tenant applications never grant membership without administrator approval.
Eligible FAMILY_MEMBER invitations directly activate sponsorship-bound membership.
All writes use the shared CSRF guard.
"""
import hashlib
import secrets
from datetime import date, timedelta
from urllib.parse import quote
from uuid import UUID

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.access import has_permission, effective_permissions
from app.modules.identity.auth.mailer import deliver_auth_email
from app.modules.identity.auth.recovery import as_utc, rate_limited
from app.modules.identity.auth.routes import EMAIL_PATTERN, error, json_object
from app.modules.identity.models import (
    ApplicationStatus, AuditLog, Flat, Household, Invitation, Membership,
    MembershipApplication, MembershipStatus, PermissionRole, ResidentCategory, RoleAssignment, User,
)
from app.modules.identity.models.user import utc_now
from app.modules.identity.models.membership import RELATIONSHIPS_TO_SPONSOR
from app.modules.identity.residential.routes import _access_state, _active_roles, _unit, _membership_summary
from app.modules.identity.access.sponsorship import eligible_family_sponsor

onboarding_bp = Blueprint("onboarding", __name__, url_prefix="/api/membership/applications")
invitations_bp = Blueprint("invitations", __name__, url_prefix="/api/invitations")
OPEN = (ApplicationStatus.DRAFT, ApplicationStatus.PENDING,
        ApplicationStatus.IN_REVIEW, ApplicationStatus.NEEDS_CORRECTION)
INVITE_TTL_DAYS = 7
MAX_NOTES = 1200


def _uuid(value):
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


def _category(value):
    try:
        return ResidentCategory(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _date(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Use YYYY-MM-DD for dates.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Use a valid YYYY-MM-DD date.") from exc


def _relationship(value):
    if value is None:
        return None
    if not isinstance(value, str) or value not in RELATIONSHIPS_TO_SPONSOR:
        raise ValueError("relationship_to_sponsor must be SPOUSE, CHILD, PARENT, SIBLING, GRANDPARENT, GRANDCHILD or OTHER.")
    return value


def _declared_occupancy(value):
    if value is not None and not isinstance(value, bool):
        raise ValueError("declared_current_occupant must be true, false or null.")
    return value


def _notes(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value.strip()) > MAX_NOTES:
        raise ValueError("Notes must be text up to 1200 characters.")
    return value.strip() or None


def _dates(body, category):
    if category != ResidentCategory.TENANT and (
        body.get("requested_valid_from") is not None or body.get("requested_valid_until") is not None
    ):
        raise ValueError("Requested tenancy dates apply only to tenants.")
    start = _date(body.get("requested_valid_from"))
    end = _date(body.get("requested_valid_until"))
    if start and end and end < start:
        raise ValueError("Tenancy end date must not precede start date.")
    return start, end


def _is_admin():
    return has_permission("identity.admin.manage")

def _valid_sponsor(sponsor, household_id=None, flat_id=None):
    """Retained for existing call sites; shared with admin approval/review."""
    return eligible_family_sponsor(sponsor, household_id=household_id, flat_id=flat_id)


def _existing_membership(flat_id, category):
    # An expired tenancy with status still ACTIVE must not block renewal.
    matches = db.session.scalars(
        select(Membership).join(Household, Membership.household_id == Household.id)
        .where(Membership.user_id == current_user.id, Household.flat_id == flat_id,
               Membership.category == category, Membership.status == MembershipStatus.ACTIVE)
    ).all()
    return any(_access_state(member) in ("ACTIVE", "NOT_STARTED") for member in matches)


def _open_application(flat_id, category):
    return db.session.scalar(
        select(MembershipApplication.id).where(
            MembershipApplication.user_id == current_user.id,
            MembershipApplication.flat_id == flat_id,
            MembershipApplication.category == category,
            MembershipApplication.status.in_(OPEN),
        ).limit(1)
    ) is not None


def _serialize(app):
    return {
        "id": str(app.id), "flat": _unit(app.flat),
        "category": app.category.value, "status": app.status.value,
        "household_id": str(app.household_id) if app.household_id else None,
        "sponsor_membership_id": str(app.sponsor_membership_id) if app.sponsor_membership_id else None,
        "invitation_id": str(app.invitation_id) if app.invitation_id else None,
        "resulting_membership_id": str(app.resulting_membership_id) if app.resulting_membership_id else None,
        "applicant_notes": app.applicant_notes,
        "relationship_to_sponsor": app.relationship_to_sponsor,
        "declared_current_occupant": app.declared_current_occupant,
        "requested_valid_from": app.requested_valid_from.isoformat() if app.requested_valid_from else None,
        "requested_valid_until": app.requested_valid_until.isoformat() if app.requested_valid_until else None,
        "evidence_required": app.category != ResidentCategory.FAMILY_MEMBER,
        "documents_uploaded": len(app.documents),
        "created_at": app.created_at.isoformat(),
        "submitted_at": app.submitted_at.isoformat() if app.submitted_at else None,
        "decided_at": app.decided_at.isoformat() if app.decided_at else None,
    }


def _owned(application_id):
    return db.session.scalar(select(MembershipApplication).where(
        MembershipApplication.id == application_id,
        MembershipApplication.user_id == current_user.id,
    ))


def _audit(action, entity, entity_id, details=None):
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action, entity_type=entity,
        entity_id=entity_id, details=details or {},
    ))


@onboarding_bp.post("")
@login_required
def create_application():
    body, failure = json_object({"flat_id", "category", "applicant_notes", "requested_valid_from", "requested_valid_until", "declared_current_occupant", "relationship_to_sponsor"})
    if failure:
        return failure
    flat_id = _uuid(body.get("flat_id"))
    category = _category(body.get("category"))
    if flat_id is None or category is None:
        return error("VALIDATION_ERROR", "A valid flat_id and resident category are required.", 400)
    if category == ResidentCategory.FAMILY_MEMBER:
        return error("INVITATION_REQUIRED", "Family members must use a verified sponsor invitation.", 403)
    flat = db.session.get(Flat, flat_id)
    if flat is None:
        return error("FLAT_NOT_FOUND", "Flat not found.", 404)
    try:
        notes = _notes(body.get("applicant_notes"))
        relation = _relationship(body.get("relationship_to_sponsor"))
        occupancy = _declared_occupancy(body.get("declared_current_occupant"))
        if relation is not None:
            raise ValueError("Family relationships are recorded only for sponsored family applications.")
        start, end = _dates(body, category)
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    if _existing_membership(flat_id, category):
        return error("ALREADY_A_RESIDENT", "You already have an active membership of this category for this flat.", 409)
    if _open_application(flat_id, category):
        return error("APPLICATION_ALREADY_OPEN", "An application is already open for this flat and category.", 409)

    application = MembershipApplication(
        user_id=current_user.id, flat_id=flat_id, category=category,
        status=ApplicationStatus.DRAFT, applicant_notes=notes,
        declared_current_occupant=occupancy,
        requested_valid_from=start, requested_valid_until=end,
    )
    try:
        db.session.add(application)
        db.session.flush()
        _audit("APPLICATION_DRAFT_CREATED", "MEMBERSHIP_APPLICATION", application.id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("APPLICATION_ALREADY_OPEN", "An application is already open for this flat and category.", 409)
    return jsonify({"application": _serialize(application)}), 201


@onboarding_bp.get("/me")
@login_required
def my_applications():
    applications = db.session.scalars(
        select(MembershipApplication).where(MembershipApplication.user_id == current_user.id)
        .order_by(MembershipApplication.created_at.desc())
    ).all()
    return jsonify({"applications": [_serialize(a) for a in applications]}), 200


@onboarding_bp.get("/<uuid:application_id>")
@login_required
def application_detail(application_id):
    application = _owned(application_id)
    if application is None:
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    return jsonify({"application": _serialize(application)}), 200


@onboarding_bp.patch("/<uuid:application_id>")
@login_required
def edit_application(application_id):
    application = _owned(application_id)
    if application is None:
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    if application.status not in (ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_CORRECTION):
        return error("INVALID_APPLICATION_STATE", "Only draft or correction-requested applications can be edited.", 409)
    body, failure = json_object({"flat_id", "category", "applicant_notes", "requested_valid_from", "requested_valid_until", "declared_current_occupant", "relationship_to_sponsor"})
    if failure:
        return failure
    if not body:
        return error("VALIDATION_ERROR", "Provide at least one field to change.", 400)
    flat_id = _uuid(body["flat_id"]) if "flat_id" in body else application.flat_id
    category = _category(body["category"]) if "category" in body else application.category
    if flat_id is None or category is None:
        return error("VALIDATION_ERROR", "Invalid flat or category.", 400)
    if application.invitation_id and (flat_id != application.flat_id or category != application.category):
        return error("INVITATION_BINDING", "An invited applicant cannot change the invited flat or category.", 409)
    if category == ResidentCategory.FAMILY_MEMBER and application.invitation_id is None:
        return error("INVITATION_REQUIRED", "Family members require a sponsor invitation.", 403)
    if db.session.get(Flat, flat_id) is None:
        return error("FLAT_NOT_FOUND", "Flat not found.", 404)
    try:
        notes = _notes(body.get("applicant_notes", application.applicant_notes))
        relation = _relationship(body.get("relationship_to_sponsor", application.relationship_to_sponsor))
        occupancy = _declared_occupancy(body.get("declared_current_occupant", application.declared_current_occupant))
        if category != ResidentCategory.FAMILY_MEMBER and relation is not None:
            raise ValueError("Only sponsored family members may declare a relationship to a sponsor.")
        requested = {
            "requested_valid_from": body.get("requested_valid_from", application.requested_valid_from.isoformat() if application.requested_valid_from else None),
            "requested_valid_until": body.get("requested_valid_until", application.requested_valid_until.isoformat() if application.requested_valid_until else None),
        }
        start, end = _dates(requested, category)
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    if (flat_id != application.flat_id or category != application.category) and (
        _open_application(flat_id, category) or _existing_membership(flat_id, category)
    ):
        return error("APPLICATION_ALREADY_OPEN", "A membership or open application already exists.", 409)
    application.flat_id = flat_id
    application.category = category
    application.applicant_notes = notes
    application.relationship_to_sponsor = relation
    application.declared_current_occupant = occupancy
    application.requested_valid_from = start
    application.requested_valid_until = end
    _audit("APPLICATION_UPDATED", "MEMBERSHIP_APPLICATION", application.id)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("APPLICATION_ALREADY_OPEN", "A conflicting application already exists.", 409)
    return jsonify({"application": _serialize(application)}), 200


@onboarding_bp.post("/<uuid:application_id>/submit")
@login_required
def submit_application(application_id):
    application = _owned(application_id)
    if application is None:
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    if application.status not in (ApplicationStatus.DRAFT, ApplicationStatus.NEEDS_CORRECTION):
        return error("INVALID_APPLICATION_STATE", "Application is not available for submission.", 409)
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify your email before submitting.", 403)
    if _existing_membership(application.flat_id, application.category):
        return error("ALREADY_A_RESIDENT", "You already have an active membership for this flat and category.", 409)
    if application.category == ResidentCategory.FAMILY_MEMBER:
        if application.invitation_id is None or application.household_id is None:
            return error("INVITATION_REQUIRED", "An accepted sponsor invitation is required.", 409)
        sponsor = db.session.get(Membership, application.sponsor_membership_id) if application.sponsor_membership_id else None
        if not _valid_sponsor(sponsor, application.household_id, application.flat_id):
            return error("SPONSOR_INELIGIBLE", "Your sponsor is no longer eligible.", 409)
    # Evidence will be added in Phase 7; Phase 8 must refuse owner/tenant
    # APPROVAL without valid documents and manual review. Pending != verified.
    application.status = ApplicationStatus.PENDING
    application.submitted_at = utc_now()
    _audit("APPLICATION_SUBMITTED", "MEMBERSHIP_APPLICATION", application.id,
           {"category": application.category.value})
    db.session.commit()
    return jsonify({"application": _serialize(application)}), 200


@invitations_bp.post("")
@login_required
def create_invitation():
    body, failure = json_object({"flat_id", "household_id", "category", "sponsor_membership_id", "email", "relationship_to_sponsor"})
    if failure:
        return failure
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify your email before inviting someone.", 403)
    if rate_limited("invitation_create"):
        return error("RATE_LIMITED", "Too many invitation requests. Try again later.", 429)
    flat_id = _uuid(body.get("flat_id"))
    household_id = _uuid(body.get("household_id")) if body.get("household_id") is not None else None
    sponsor_id = _uuid(body.get("sponsor_membership_id")) if body.get("sponsor_membership_id") is not None else None
    category = _category(body.get("category"))
    try:
        relation = _relationship(body.get("relationship_to_sponsor"))
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    raw_email = body.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    if (flat_id is None or category is None or not EMAIL_PATTERN.fullmatch(email)
            or len(email) > 255 or email == current_user.email
            or (body.get("household_id") is not None and household_id is None)
            or (body.get("sponsor_membership_id") is not None and sponsor_id is None)):
        return error("VALIDATION_ERROR", "Check flat, category, email and household/sponsor IDs.", 400)
    if db.session.get(Flat, flat_id) is None:
        return error("FLAT_NOT_FOUND", "Flat not found.", 404)
    household = db.session.get(Household, household_id) if household_id else None
    if household_id is not None and (household is None or household.flat_id != flat_id):
        return error("HOUSEHOLD_MISMATCH", "Household does not belong to the requested flat.", 400)

    privileged = _is_admin()
    sponsor = db.session.get(Membership, sponsor_id) if sponsor_id else None
    if category != ResidentCategory.FAMILY_MEMBER and relation is not None:
        return error("VALIDATION_ERROR", "Relationship is only applicable to family invitations.", 400)
    if category == ResidentCategory.FAMILY_MEMBER:
        if household_id is None or sponsor is None or not _valid_sponsor(sponsor, household_id, flat_id):
            return error("SPONSOR_INELIGIBLE", "An eligible same-household sponsor is required.", 403)
        if not privileged and sponsor.user_id != current_user.id:
            return error("FORBIDDEN", "You can invite only from your own eligible sponsorship.", 403)
    else:
        if sponsor_id is not None:
            return error("VALIDATION_ERROR", "Only family invitations may have a sponsor.", 400)
        if not privileged:
            return error("FORBIDDEN", "Only an administrator can invite an owner or tenant.", 403)

    now = utc_now()
    raw = secrets.token_urlsafe(32)
    invitation = Invitation(
        flat_id=flat_id, household_id=household_id, invited_by_user_id=current_user.id,
        invited_email=email, token_hash=hashlib.sha256(raw.encode("ascii")).hexdigest(),
        category=category, sponsor_membership_id=sponsor_id,
        relationship_to_sponsor=relation,
        created_at=now, expires_at=now + timedelta(days=INVITE_TTL_DAYS),
    )
    db.session.add(invitation)
    db.session.flush()
    _audit("INVITATION_CREATED", "INVITATION", invitation.id,
           {"category": category.value, "flat_id": str(flat_id)})
    db.session.commit()
    link = f"{current_app.config['FRONTEND_BASE_URL'].rstrip('/')}/invitations/accept?token={quote(raw, safe='')}"
    try:
        deliver_auth_email(to_address=email, subject="Your KNOWALL resident invitation",
                           body=(f"You have been invited to join a household in Green Valley Residency as a family member.\n"
                                 if category == ResidentCategory.FAMILY_MEMBER else
                                 "You have been invited to apply to Green Valley Residency.\n")
                           + f"Accept within seven days: {link}\nIf unexpected, ignore this email.\n")
    except Exception:
        current_app.logger.exception("Unable to deliver invitation")
        invitation.revoked_at = utc_now()
        db.session.commit()
        return error("INVITATION_DELIVERY_FAILED", "Unable to deliver invitation. Try again later.", 503)
    # The raw token is deliberately omitted. Only the intended mailbox sees it.
    return jsonify({"invitation": {"id": str(invitation.id), "email": email,
                                   "flat_id": str(flat_id), "category": category.value,
                                   "expires_at": invitation.expires_at.isoformat(),
                                   "relationship_to_sponsor": invitation.relationship_to_sponsor}}), 201


@invitations_bp.get("/me")
@login_required
def my_invitations():
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify your email first.", 403)
    now = utc_now()
    rows = db.session.scalars(select(Invitation).where(Invitation.invited_email == current_user.email)
                              .order_by(Invitation.created_at.desc())).all()
    return jsonify({"invitations": [{
        "id": str(inv.id), "flat_id": str(inv.flat_id),
        "category": inv.category.value if inv.category else None,
        "relationship_to_sponsor": inv.relationship_to_sponsor,
        "household_id": str(inv.household_id) if inv.household_id else None,
        "status": ("USED" if inv.used_at else "REVOKED" if inv.revoked_at else
                   "EXPIRED" if as_utc(inv.expires_at) <= now else "ACTIVE"),
        "expires_at": inv.expires_at.isoformat(),
    } for inv in rows]}), 200


@invitations_bp.post("/accept")
@login_required
def accept_invitation():
    body, failure = json_object({"token", "relationship_to_sponsor", "declared_current_occupant"})
    if failure:
        return failure
    if current_user.email_verified_at is None:
        return error("EMAIL_VERIFICATION_REQUIRED", "Verify your email before accepting.", 403)
    try:
        accepted_relation = _relationship(body.get("relationship_to_sponsor"))
        occupancy = _declared_occupancy(body.get("declared_current_occupant"))
    except ValueError as exc:
        return error("VALIDATION_ERROR", str(exc), 400)
    raw = body.get("token")
    if not isinstance(raw, str) or not 20 <= len(raw) <= 300 or not raw.isascii():
        return error("INVALID_INVITATION", "Invitation is invalid or expired.", 400)
    digest = hashlib.sha256(raw.encode("ascii")).hexdigest()
    invitation = db.session.scalar(select(Invitation).where(Invitation.token_hash == digest))
    now = utc_now()
    if (invitation is None or invitation.category is None or
            invitation.used_at is not None or invitation.revoked_at is not None or
            as_utc(invitation.expires_at) <= now):
        return error("INVALID_INVITATION", "Invitation is invalid or expired.", 400)
    if invitation.category != ResidentCategory.FAMILY_MEMBER and accepted_relation is not None:
        return error("VALIDATION_ERROR", "Relationship is only applicable to family invitations.", 400)
    if invitation.invited_email != current_user.email:
        return error("INVITATION_EMAIL_MISMATCH", "This invitation is addressed to another account.", 403)
    if invitation.household_id is not None:
        household = db.session.get(Household, invitation.household_id)
        if household is None or household.flat_id != invitation.flat_id:
            return error("HOUSEHOLD_MISMATCH", "Invitation household is invalid.", 409)
    if invitation.category == ResidentCategory.FAMILY_MEMBER:
        sponsor = db.session.get(Membership, invitation.sponsor_membership_id) if invitation.sponsor_membership_id else None
        if not _valid_sponsor(sponsor, invitation.household_id, invitation.flat_id):
            return error("SPONSOR_INELIGIBLE", "Invitation sponsor is no longer eligible.", 409)
    # Existing Owner/Tenant invitations preserve the review-based draft workflow.
    # Family invitations deliberately do NOT create a new application; the
    # invitation, membership and audit events remain our permanent history.
    if invitation.category == ResidentCategory.FAMILY_MEMBER:
        relationship = accepted_relation if "relationship_to_sponsor" in body else invitation.relationship_to_sponsor
        if relationship is None:
            return error("RELATIONSHIP_REQUIRED", "Declare your relationship to the sponsor.", 400)
        if invitation.household_id is None or invitation.sponsor_membership_id is None:
            return error("SPONSOR_INELIGIBLE", "Family invitation requires an explicit eligible sponsor and household.", 409)

        # Consistent lock order: sponsor first, then recipient User, then the
        # conditional invitation claim. Admin suspension/revocation locks the
        # same sponsor membership row before changing its status.
        db.session.execute(select(Membership.id).where(
            Membership.id == invitation.sponsor_membership_id).with_for_update()).first()
        db.session.execute(select(User.id).where(User.id == current_user.id).with_for_update()).first()
        db.session.expire_all()
        recipient_user = db.session.get(User, current_user.id)
        db.session.refresh(recipient_user)
        if (not recipient_user.is_active or recipient_user.email_verified_at is None
                or recipient_user.email != invitation.invited_email):
            db.session.rollback()
            return error("RECIPIENT_INELIGIBLE", "Recipient is no longer verified or eligible.", 403)
        sponsor = db.session.get(Membership, invitation.sponsor_membership_id)
        if not _valid_sponsor(sponsor, invitation.household_id, invitation.flat_id):
            db.session.rollback()
            return error("SPONSOR_INELIGIBLE", "Invitation sponsor is no longer eligible.", 409)
        if _existing_membership(invitation.flat_id, ResidentCategory.FAMILY_MEMBER):
            db.session.rollback()
            return error("ALREADY_A_RESIDENT", "An active family membership already exists for this flat.", 409)
        if _open_application(invitation.flat_id, ResidentCategory.FAMILY_MEMBER):
            db.session.rollback()
            return error("APPLICATION_ALREADY_OPEN", "Resolve the existing family application before accepting another invitation.", 409)
        claim = db.session.execute(
            update(Invitation).where(
                Invitation.id == invitation.id, Invitation.used_at.is_(None),
                Invitation.revoked_at.is_(None), Invitation.expires_at > now,
            ).values(used_at=now, accepted_by_user_id=current_user.id)
            .execution_options(synchronize_session=False)
        )
        if claim.rowcount != 1:
            db.session.rollback()
            return error("INVALID_INVITATION", "Invitation is invalid or already accepted.", 409)
        membership = Membership(
            user_id=current_user.id, household_id=invitation.household_id,
            sponsor_membership_id=sponsor.id,
            category=ResidentCategory.FAMILY_MEMBER, status=MembershipStatus.ACTIVE,
            valid_from=now.date(), valid_until=sponsor.valid_until,
            relationship_to_sponsor=relationship,
            # Self-declaration never masquerades as admin-confirmed occupancy.
            is_current_occupant=None, declared_current_occupant=occupancy,
        )
        try:
            db.session.add(membership)
            db.session.flush()
            active_role = db.session.scalar(select(RoleAssignment.id).where(
                RoleAssignment.user_id == current_user.id,
                RoleAssignment.role == PermissionRole.RESIDENT,
                RoleAssignment.revoked_at.is_(None),
            ).limit(1))
            if active_role is None:
                db.session.add(RoleAssignment(
                    user_id=current_user.id, role=PermissionRole.RESIDENT,
                    granted_by_user_id=sponsor.user_id,
                ))
            _audit("FAMILY_MEMBERSHIP_AUTO_ACTIVATED", "MEMBERSHIP", membership.id,
                   {"invitation_id": str(invitation.id),
                    "sponsor_membership_id": str(sponsor.id),
                    "household_id": str(invitation.household_id),
                    "declared_current_occupant": occupancy,
                    "relationship_to_sponsor": relationship})
            _audit("INVITATION_ACCEPTED", "INVITATION", invitation.id,
                   {"membership_id": str(membership.id), "category": "FAMILY_MEMBER"})
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return error("MEMBERSHIP_CONFLICT", "An active membership or used invitation already exists.", 409)
        return jsonify({
            "outcome": "FAMILY_MEMBERSHIP_ACTIVATED",
            "application": None,
            "membership": _membership_summary(membership),
            "access": {"permissions": effective_permissions(),
                       "verified_resident": _access_state(membership) == "ACTIVE"},
        }), 201

    if _existing_membership(invitation.flat_id, invitation.category) or _open_application(invitation.flat_id, invitation.category):
        return error("APPLICATION_ALREADY_OPEN", "A membership or open application already exists for this flat and category.", 409)

    # Atomic claim remains unchanged for Owner/Tenant invitations.
    result = db.session.execute(
        update(Invitation).where(Invitation.id == invitation.id,
            Invitation.used_at.is_(None), Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        ).values(used_at=now, accepted_by_user_id=current_user.id)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.session.rollback()
        return error("INVALID_INVITATION", "Invitation is invalid or already used.", 409)
    application = MembershipApplication(
        user_id=current_user.id, flat_id=invitation.flat_id,
        household_id=invitation.household_id,
        sponsor_membership_id=invitation.sponsor_membership_id,
        invitation_id=invitation.id, category=invitation.category,
        relationship_to_sponsor=None,
        declared_current_occupant=occupancy,
        status=ApplicationStatus.DRAFT,
    )
    try:
        db.session.add(application)
        db.session.flush()
        _audit("INVITATION_ACCEPTED", "INVITATION", invitation.id,
               {"application_id": str(application.id)})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("APPLICATION_ALREADY_OPEN", "A conflicting application already exists.", 409)
    return jsonify({"outcome": "APPLICATION_DRAFT_CREATED", "application": _serialize(application),
                    "membership": None}), 201
