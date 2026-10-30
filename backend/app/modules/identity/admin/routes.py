"""Single-society administrator decisions and resident membership management.

OCR data assists a human reviewer but never authorizes approval by itself.
All modifying routes use the shared Flask CSRF guard. Transactions preserve
review, membership, role and audit consistency.
"""
from flask import Blueprint, jsonify, request
import re
from flask_login import current_user
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.modules.identity.access import requires_permission
from app.modules.identity.access.sponsorship import eligible_family_sponsor
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models import (
    ApplicationReview, ApplicationStatus, AuditLog, Flat, Household,
    Membership, MembershipApplication, MembershipStatus, OCRResult, OCRStatus,
    PermissionRole, ResidentCategory, ReviewDecision, RoleAssignment, User,
    VerificationDocument,
)
from app.modules.identity.models.user import utc_now
from app.modules.identity.models.membership import RELATIONSHIPS_TO_SPONSOR
from app.modules.identity.onboarding.routes import _serialize
from app.modules.identity.residential.routes import _access_state, _membership_summary, _today

admin_bp = Blueprint("resident_admin", __name__, url_prefix="/api/admin")
# Reuse the single cross-module permission policy. It checks live role grants,
# current account status and email verification on every request.
admin_required = requires_permission("identity.admin.manage")

def _audit(action, entity_type, entity_id, details):
    db.session.add(AuditLog(
        actor_user_id=current_user.id, action=action,
        entity_type=entity_type, entity_id=entity_id, details=details,
    ))


def _application_base(application):
    data = _serialize(application)
    data["applicant"] = {
        "id": str(application.user_id),
        "display_name": application.user.display_name,
        "email": application.user.email,
        "email_verified": application.user.email_verified_at is not None,
        "phone": application.user.phone,
    }
    return data


def _latest_ocr(document):
    if not document.ocr_results:
        return None
    latest = max(document.ocr_results, key=lambda r: (r.created_at, str(r.id)))
    return {
        "id": str(latest.id), "status": latest.status.value,
        "fields": latest.extracted_fields, "comparisons": latest.comparison_results,
        "warnings": latest.warnings or [], "error_message": latest.error_message,
    }


def _linked_sponsor(application, *, lock=False):
    """Resolve ONLY the sponsor_membership_id explicitly saved on the application.

    During approval, lock the sponsor row in the same transaction as the
    application decision. Revocation/status changes also lock this row.
    """
    if application.category != ResidentCategory.FAMILY_MEMBER or not application.sponsor_membership_id:
        return None
    query = (select(Membership)
             .options(selectinload(Membership.user), selectinload(Membership.household))
             .where(Membership.id == application.sponsor_membership_id))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    return db.session.scalar(query)


def _sponsor_context(application, sponsor):
    if sponsor is None:
        return None
    household = sponsor.household
    return {
        "membership_id": str(sponsor.id),
        "display_name": sponsor.user.display_name if sponsor.user else None,
        "category": sponsor.category.value,
        "membership_status": sponsor.status.value,
        "household_id": str(sponsor.household_id),
        "household_label": household.label if household else None,
        "flat_id": str(household.flat_id) if household else None,
        "eligible_to_sponsor": eligible_family_sponsor(
            sponsor, household_id=application.household_id, flat_id=application.flat_id,
        ) if application.household_id is not None else False,
        "valid_from": sponsor.valid_from.isoformat(),
        "valid_until": sponsor.valid_until.isoformat() if sponsor.valid_until else None,
    }


def _sponsor_name_advisory(ocr, sponsor):
    """Additional name hint, never replacing existing applicant comparison."""
    fields = ocr.get("fields") or {}
    extracted = fields.get("resident_name")
    name = sponsor.user.display_name if sponsor and sponsor.user else None
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", str(value or "").casefold())
    if not extracted or not name:
        status = "NAME_NOT_AVAILABLE"
    elif normalize(extracted) == normalize(name):
        status = "MATCHES_SPONSOR_NAME"
    else:
        status = "DOES_NOT_MATCH_SPONSOR_NAME"
    return {"status": status, "advisory_only": True,
            "basis": "linked_sponsor_display_name",
            "extracted_name": extracted}


def _application_detail(application, *, sponsor=None):
    data = _application_base(application)
    data["documents"] = [
        {
            "id": str(d.id), "document_type": d.document_type.value,
            "filename": d.original_filename, "uploaded_at": d.uploaded_at.isoformat(),
            "download_url": f"/api/documents/{d.id}/file", "latest_ocr": _latest_ocr(d),
        }
        for d in application.documents if d.deleted_at is None
    ]
    # Preserve the original OCR-vs-APPLICANT comparison unchanged. For family
    # applications, a separate advisory comparison may explain why a letter
    # names the sponsor rather than the applicant.
    if application.category == ResidentCategory.FAMILY_MEMBER:
        for document in data["documents"]:
            ocr = document.get("latest_ocr")
            if ocr is not None:
                ocr["sponsor_name_advisory"] = _sponsor_name_advisory(ocr, sponsor)
    data["reviews"] = [
        {"id": str(r.id), "decision": r.decision.value,
         "reason": r.reason, "reviewer_user_id": str(r.reviewer_user_id),
         "created_at": r.created_at.isoformat()}
        for r in sorted(application.reviews, key=lambda x: x.created_at)
    ]
    return data


def _load_application(application_id):
    return db.session.scalar(
        select(MembershipApplication).options(
            selectinload(MembershipApplication.user),
            selectinload(MembershipApplication.flat).selectinload(Flat.tower),
            selectinload(MembershipApplication.documents).selectinload(VerificationDocument.ocr_results),
            selectinload(MembershipApplication.reviews),
        ).where(MembershipApplication.id == application_id)
    )


def _pagination():
    try:
        limit = int(request.args.get("limit", "30"))
        offset = int(request.args.get("offset", "0"))
    except (ValueError, TypeError):
        return None
    return (limit, offset) if 1 <= limit <= 100 and 0 <= offset <= 100000 else None


def _resident_role(user_id):
    existing = db.session.scalar(select(RoleAssignment.id).where(
        RoleAssignment.user_id == user_id,
        RoleAssignment.role == PermissionRole.RESIDENT,
        RoleAssignment.revoked_at.is_(None),
    ).limit(1))
    if existing is None:
        db.session.add(RoleAssignment(
            user_id=user_id, role=PermissionRole.RESIDENT,
            granted_by_user_id=current_user.id,
        ))


def _has_eligible_membership(user_id):
    # A role is not a substitute for a live membership; this is for keeping
    # the RESIDENT role in sync after suspension or revocation.
    entries = db.session.scalars(select(Membership).where(
        Membership.user_id == user_id,
        Membership.status == MembershipStatus.ACTIVE,
    )).all()
    return any(_access_state(item) == "ACTIVE" for item in entries)


def _sync_resident_role(user_id):
    if _has_eligible_membership(user_id):
        _resident_role(user_id)
    else:
        db.session.execute(update(RoleAssignment).where(
            RoleAssignment.user_id == user_id,
            RoleAssignment.role == PermissionRole.RESIDENT,
            RoleAssignment.revoked_at.is_(None),
        ).values(revoked_at=utc_now()).execution_options(synchronize_session=False))


@admin_bp.get("/applications")
@admin_required
def list_applications():
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "limit must be 1–100 and offset must be nonnegative.", 400)
    limit, offset = pagination
    status_name = request.args.get("status")
    status = None
    if status_name:
        try:
            status = ApplicationStatus(status_name)
        except ValueError:
            return error("VALIDATION_ERROR", "Unknown application status.", 400)
    conditions = [MembershipApplication.status == status] if status else []
    count = db.session.scalar(select(func.count()).select_from(MembershipApplication).where(*conditions))
    entries = db.session.scalars(select(MembershipApplication).options(
        selectinload(MembershipApplication.user),
        selectinload(MembershipApplication.flat).selectinload(Flat.tower),
        selectinload(MembershipApplication.documents),
    ).where(*conditions).order_by(MembershipApplication.created_at.desc(), MembershipApplication.id.desc())
        .limit(limit).offset(offset)).all()
    return jsonify({"applications": [_application_base(a) for a in entries],
                    "pagination": {"limit": limit, "offset": offset, "total": count}}), 200


@admin_bp.get("/applications/<uuid:application_id>")
@admin_required
def application_detail(application_id):
    item = _load_application(application_id)
    if item is None:
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    if item.category == ResidentCategory.FAMILY_MEMBER:
        sponsor = _linked_sponsor(item)
        return jsonify({"application": _application_detail(item, sponsor=sponsor),
                        "sponsor_context": _sponsor_context(item, sponsor)}), 200
    return jsonify({"application": _application_detail(item)}), 200


@admin_bp.post("/applications/<uuid:application_id>/decision")
@admin_required
def decide_application(application_id):
    body, failure = json_object({"decision", "reason", "document_reviewed", "acknowledge_ocr_warnings"})
    if failure:
        return failure
    try:
        decision = ReviewDecision(body.get("decision"))
    except (ValueError, TypeError):
        return error("VALIDATION_ERROR", "decision must be APPROVED, REJECTED or NEEDS_CORRECTION.", 400)
    reason = body.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason.strip()) > 1200):
        return error("VALIDATION_ERROR", "Reason must be text up to 1200 characters.", 400)
    reason = reason.strip() if isinstance(reason, str) else None
    if decision != ReviewDecision.APPROVED and not reason:
        return error("VALIDATION_ERROR", "A reason is required for rejection or correction.", 400)
    if body.get("document_reviewed", False) not in (True, False) or not isinstance(body.get("document_reviewed", False), bool):
        return error("VALIDATION_ERROR", "document_reviewed must be a boolean.", 400)
    if not isinstance(body.get("acknowledge_ocr_warnings", False), bool):
        return error("VALIDATION_ERROR", "acknowledge_ocr_warnings must be a boolean.", 400)

    # PostgreSQL row lock blocks competing decisions. On SQLite the conditional
    # status UPDATE below is the fallback protecting atomic state changes.
    db.session.execute(select(MembershipApplication.id)
        .where(MembershipApplication.id == application_id).with_for_update()).first()
    item = _load_application(application_id)
    if item is None:
        db.session.rollback()
        return error("APPLICATION_NOT_FOUND", "Application not found.", 404)
    if item.user_id == current_user.id:
        db.session.rollback()
        return error("SELF_REVIEW_FORBIDDEN", "An administrator cannot decide their own application.", 403)
    if item.status not in (ApplicationStatus.PENDING, ApplicationStatus.IN_REVIEW):
        db.session.rollback()
        return error("INVALID_APPLICATION_STATE", "Only pending applications can be decided.", 409)

    if decision == ReviewDecision.APPROVED:
        if not item.user.is_active or item.user.email_verified_at is None:
            db.session.rollback()
            return error("APPLICANT_INELIGIBLE", "Applicant account is not active and email-verified.", 409)
        documents = [doc for doc in item.documents if doc.deleted_at is None]
        if item.category != ResidentCategory.FAMILY_MEMBER:
            if not documents:
                db.session.rollback()
                return error("DOCUMENT_REQUIRED", "At least one residence document must be uploaded.", 409)
            if body.get("document_reviewed") is not True:
                db.session.rollback()
                return error("MANUAL_REVIEW_REQUIRED", "Administrator must confirm manual document review.", 409)
            warnings = any((ocr.warnings or []) or ocr.status == OCRStatus.FAILED
                           for document in documents for ocr in document.ocr_results)
            if warnings and body.get("acknowledge_ocr_warnings") is not True:
                db.session.rollback()
                return error("OCR_WARNINGS_UNACKNOWLEDGED", "Review and acknowledge the OCR warnings.", 409)
        if item.category == ResidentCategory.TENANT:
            if item.requested_valid_from is None or item.requested_valid_until is None:
                db.session.rollback()
                return error("TENANCY_DATES_REQUIRED", "Tenant start and end dates are required for approval.", 409)
            valid_from, valid_until = item.requested_valid_from, item.requested_valid_until
            if valid_until < _today():
                db.session.rollback()
                return error("TENANCY_EXPIRED", "Cannot approve already-expired tenancy.", 409)
        else:
            valid_from, valid_until = _today(), None
        if item.category == ResidentCategory.FAMILY_MEMBER:
            # A declared relationship is not evidence of a true family tie,
            # but any recorded value must still belong to the allowed set.
            if (item.relationship_to_sponsor is not None
                    and item.relationship_to_sponsor not in RELATIONSHIPS_TO_SPONSOR):
                db.session.rollback()
                return error("INVALID_FAMILY_RELATIONSHIP", "The recorded family relationship is invalid.", 409)
            # PostgreSQL FOR UPDATE serializes approval with concurrent
            # suspension/revocation of the explicitly linked sponsor. Always
            # re-evaluate eligibility here; GET context may be stale.
            sponsor = _linked_sponsor(item, lock=True)
            if (item.household_id is None or not eligible_family_sponsor(
                sponsor, household_id=item.household_id, flat_id=item.flat_id,
            )):
                db.session.rollback()
                return error("SPONSOR_INELIGIBLE", "A currently eligible sponsor in the exact household and flat is required.", 409)
            household = sponsor.household
        else:
            household = db.session.get(Household, item.household_id) if item.household_id else None
            if household is not None and household.flat_id != item.flat_id:
                db.session.rollback()
                return error("HOUSEHOLD_MISMATCH", "Application household does not match the flat.", 409)
            if household is None:
                household = Household(flat_id=item.flat_id,
                                      label=f"{item.category.value.title()} household - {item.user.display_name}"[:100])
                db.session.add(household)
                db.session.flush()
        # One user can have different categories, but cannot duplicate a live
        # membership of the same category at one flat (across households).
        members = db.session.scalars(select(Membership).join(Household).where(
            Membership.user_id == item.user_id, Household.flat_id == item.flat_id,
            Membership.category == item.category,
            Membership.status == MembershipStatus.ACTIVE,
        )).all()
        if any(_access_state(member) in ("ACTIVE", "NOT_STARTED") for member in members):
            db.session.rollback()
            return error("ALREADY_A_RESIDENT", "Applicant already has an active membership for this flat.", 409)

    new_status = {
        ReviewDecision.APPROVED: ApplicationStatus.APPROVED,
        ReviewDecision.REJECTED: ApplicationStatus.REJECTED,
        ReviewDecision.NEEDS_CORRECTION: ApplicationStatus.NEEDS_CORRECTION,
    }[decision]
    now = utc_now()
    updated = db.session.execute(update(MembershipApplication).where(
        MembershipApplication.id == application_id,
        MembershipApplication.status.in_([ApplicationStatus.PENDING, ApplicationStatus.IN_REVIEW]),
    ).values(status=new_status,
             decided_at=now if decision != ReviewDecision.NEEDS_CORRECTION else None,
             updated_at=now).execution_options(synchronize_session=False))
    if updated.rowcount != 1:
        db.session.rollback()
        return error("APPLICATION_ALREADY_DECIDED", "The application was already reviewed.", 409)

    try:
        # SQLAlchemy identity map may contain a previous instance, ensure it
        # observes the conditional update before response serialization.
        db.session.expire(item, ["status", "decided_at", "updated_at"])
        membership = None
        if decision == ReviewDecision.APPROVED:
            membership = Membership(
                user_id=item.user_id, household_id=household.id,
                sponsor_membership_id=item.sponsor_membership_id if item.category == ResidentCategory.FAMILY_MEMBER else None,
                category=item.category, status=MembershipStatus.ACTIVE,
                relationship_to_sponsor=item.relationship_to_sponsor if item.category == ResidentCategory.FAMILY_MEMBER else None,
                # Self-declared occupancy is pending until a separate admin confirmation.
                is_current_occupant=None,
                valid_from=valid_from, valid_until=valid_until,
            )
            db.session.add(membership)
            db.session.flush()
            item.resulting_membership_id = membership.id
            item.household_id = household.id
            _resident_role(item.user_id)
        db.session.add(ApplicationReview(
            application_id=item.id, reviewer_user_id=current_user.id,
            decision=decision, reason=reason,
        ))
        _audit("APPLICATION_" + decision.value, "MEMBERSHIP_APPLICATION", item.id,
               {"decision": decision.value, "membership_id": str(membership.id) if membership else None})
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("APPROVAL_CONFLICT", "A conflicting membership or review already exists.", 409)
    refreshed = _load_application(application_id)
    return jsonify({"application": _application_detail(refreshed)}), 200


@admin_bp.get("/memberships")
@admin_required
def list_memberships():
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    status_str = request.args.get("status")
    try:
        status = MembershipStatus(status_str) if status_str else None
    except ValueError:
        return error("VALIDATION_ERROR", "Unknown membership status.", 400)
    conditions = [Membership.status == status] if status else []
    count = db.session.scalar(select(func.count()).select_from(Membership).where(*conditions))
    members = db.session.scalars(select(Membership).options(
        selectinload(Membership.user), selectinload(Membership.household)
        .selectinload(Household.flat).selectinload(Flat.tower),
        selectinload(Membership.sponsor).selectinload(Membership.user),
    ).where(*conditions).order_by(Membership.created_at.desc(), Membership.id.desc())
        .limit(limit).offset(offset)).all()
    return jsonify({"memberships": [dict(_membership_summary(m), user={
        "id": str(m.user_id), "display_name": m.user.display_name, "email": m.user.email})
        for m in members], "pagination": {"limit": limit, "offset": offset, "total": count}}), 200


@admin_bp.patch("/memberships/<uuid:membership_id>/status")
@admin_required
def change_membership_status(membership_id):
    body, failure = json_object({"status", "reason"})
    if failure:
        return failure
    try:
        status = MembershipStatus(body.get("status"))
    except (ValueError, TypeError):
        return error("VALIDATION_ERROR", "Invalid membership status.", 400)
    reason = body.get("reason")
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 1200:
        return error("VALIDATION_ERROR", "A reason of 3–1200 characters is required.", 400)
    db.session.execute(select(Membership.id).where(Membership.id == membership_id).with_for_update()).first()
    member = db.session.get(Membership, membership_id)
    if member is None:
        db.session.rollback()
        return error("MEMBERSHIP_NOT_FOUND", "Membership not found.", 404)
    allowed = {
        MembershipStatus.ACTIVE: {MembershipStatus.SUSPENDED, MembershipStatus.REVOKED},
        MembershipStatus.SUSPENDED: {MembershipStatus.ACTIVE, MembershipStatus.REVOKED},
    }
    if status not in allowed.get(member.status, set()):
        db.session.rollback()
        return error("INVALID_MEMBERSHIP_TRANSITION", "Membership status transition is not allowed.", 409)
    if status == MembershipStatus.ACTIVE:
        if member.user.email_verified_at is None or not member.user.is_active:
            db.session.rollback()
            return error("APPLICANT_INELIGIBLE", "Account is not eligible for reinstatement.", 409)
        if member.valid_until is not None and member.valid_until < _today():
            db.session.rollback()
            return error("MEMBERSHIP_EXPIRED", "Expired membership requires renewal.", 409)
        if member.category == ResidentCategory.FAMILY_MEMBER:
            sponsor = member.sponsor
            if sponsor is None or _access_state(sponsor) != "ACTIVE" or sponsor.household_id != member.household_id:
                db.session.rollback()
                return error("SPONSOR_INELIGIBLE", "Sponsor must be active before reinstatement.", 409)

    prior = member.status
    changed = db.session.execute(update(Membership).where(
        Membership.id == membership_id, Membership.status == prior,
    ).values(status=status, updated_at=utc_now()).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        db.session.rollback()
        return error("MEMBERSHIP_CONFLICT", "Membership changed during this request.", 409)
    db.session.expire(member, ["status", "updated_at"])
    # Dependent family memberships become ineligible automatically through
    # _access_state; they are not silently deleted or changed.
    _sync_resident_role(member.user_id)
    _audit("MEMBERSHIP_STATUS_CHANGED", "MEMBERSHIP", member.id,
           {"from": prior.value, "to": status.value, "reason": reason.strip()})
    db.session.commit()
    return jsonify({"membership": _membership_summary(member)}), 200


@admin_bp.get("/audit-logs")
@admin_required
def audit_logs():
    pagination = _pagination()
    if pagination is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = pagination
    rows = db.session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
                              .limit(limit).offset(offset)).all()
    return jsonify({"logs": [{"id": str(r.id), "actor_user_id": str(r.actor_user_id) if r.actor_user_id else None,
                              "action": r.action, "entity_type": r.entity_type,
                              "entity_id": str(r.entity_id) if r.entity_id else None,
                              "details": r.details or {}, "created_at": r.created_at.isoformat()}
                             for r in rows]}), 200


@admin_bp.patch("/memberships/<uuid:membership_id>/occupancy")
@admin_required
def confirm_membership_occupancy(membership_id):
    """Confirm occupancy with an audit trail; never accept self-declaration as proof."""
    body, failure = json_object({"is_current_occupant", "reason"})
    if failure:
        return failure
    occupied = body.get("is_current_occupant")
    reason = body.get("reason")
    if not isinstance(occupied, bool):
        return error("VALIDATION_ERROR", "is_current_occupant must be true or false.", 400)
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 1200:
        return error("VALIDATION_ERROR", "A reason of 3–1200 characters is required.", 400)
    db.session.execute(select(Membership.id).where(Membership.id == membership_id).with_for_update()).first()
    membership = db.session.get(Membership, membership_id)
    if membership is None:
        db.session.rollback()
        return error("MEMBERSHIP_NOT_FOUND", "Membership not found.", 404)
    if membership.status != MembershipStatus.ACTIVE:
        db.session.rollback()
        return error("INVALID_MEMBERSHIP_STATE", "Only active memberships can have occupancy confirmed.", 409)
    previous = membership.is_current_occupant
    membership.is_current_occupant = occupied
    membership.occupancy_confirmed_at = utc_now()
    membership.occupancy_confirmed_by_user_id = current_user.id
    _audit("MEMBERSHIP_OCCUPANCY_CONFIRMED", "MEMBERSHIP", membership.id, {
        "previous": previous, "current": occupied, "reason": reason.strip(),
    })
    db.session.commit()
    return jsonify({"membership": _membership_summary(membership)}), 200


@admin_bp.patch("/memberships/<uuid:membership_id>/relationship")
@admin_required
def correct_family_relationship(membership_id):
    """Correct an approved family member's relationship to their sponsor."""
    body, failure = json_object({"relationship_to_sponsor", "reason"})
    if failure:
        return failure
    if "relationship_to_sponsor" not in body:
        return error("VALIDATION_ERROR", "relationship_to_sponsor must be provided (null to clear).", 400)
    relation = body["relationship_to_sponsor"]
    reason = body.get("reason")
    if relation is not None and (not isinstance(relation, str) or relation not in RELATIONSHIPS_TO_SPONSOR):
        return error("VALIDATION_ERROR", "Invalid relationship_to_sponsor.", 400)
    if not isinstance(reason, str) or not 3 <= len(reason.strip()) <= 1200:
        return error("VALIDATION_ERROR", "A reason of 3–1200 characters is required.", 400)
    db.session.execute(select(Membership.id).where(Membership.id == membership_id).with_for_update()).first()
    member = db.session.get(Membership, membership_id)
    if member is None:
        db.session.rollback()
        return error("MEMBERSHIP_NOT_FOUND", "Membership not found.", 404)
    if member.category != ResidentCategory.FAMILY_MEMBER or member.sponsor_membership_id is None:
        db.session.rollback()
        return error("NOT_FAMILY_MEMBERSHIP", "Only sponsored family memberships have this relationship.", 409)
    previous = member.relationship_to_sponsor
    member.relationship_to_sponsor = relation
    _audit("FAMILY_RELATIONSHIP_CORRECTED", "MEMBERSHIP", member.id, {
        "previous": previous, "current": relation, "reason": reason.strip(),
    })
    db.session.commit()
    return jsonify({"membership": _membership_summary(member)}), 200
