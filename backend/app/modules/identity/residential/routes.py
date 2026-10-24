"""KNOWALL Phase 5: society directory and current-user residence APIs.

Only non-personal unit reference data is public. No endpoint accepts a user_id
or household_id from the caller to bypass authenticated ownership checks.
"""
from datetime import date, datetime, timezone
from uuid import UUID

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.modules.identity.access import effective_permissions
from app.modules.identity.auth.routes import error, json_object, PHONE_PATTERN, public_user
from app.modules.identity.models import (
    AuditLog, Flat, Household, Membership, MembershipStatus, PermissionRole,
    ResidentCategory, RoleAssignment, SocietyProfile, Tower,
)

residential_bp = Blueprint("residential", __name__, url_prefix="/api/residential")
profile_bp = Blueprint("current_resident", __name__, url_prefix="/api/me")


def _today():
    """Use a consistent calendar date when evaluating membership validity."""
    return datetime.now(timezone.utc).date()


def _unit(flat: Flat) -> dict:
    return {
        "id": str(flat.id),
        "tower_id": str(flat.tower_id),
        "tower_name": flat.tower.name,
        "flat_number": flat.flat_number,
        "floor_number": flat.floor_number,
    }


def _active_roles(user_id) -> list[str]:
    roles = db.session.scalars(
        select(RoleAssignment.role)
        .where(RoleAssignment.user_id == user_id, RoleAssignment.revoked_at.is_(None))
        .order_by(RoleAssignment.role)
    ).all()
    return sorted({role.value for role in roles})


def _access_state(membership: Membership) -> str:
    """Computed access state; never alters the stored membership lifecycle."""
    if membership.status != MembershipStatus.ACTIVE:
        return membership.status.value
    today = _today()
    if membership.valid_from > today:
        return "NOT_STARTED"
    if membership.valid_until is not None and membership.valid_until < today:
        return "EXPIRED"
    if membership.category == ResidentCategory.FAMILY_MEMBER:
        sponsor = membership.sponsor
        if sponsor is None or sponsor.id == membership.id:
            return "SPONSOR_INELIGIBLE"
        if sponsor.household_id != membership.household_id:
            return "SPONSOR_INELIGIBLE"
        if sponsor.category not in (ResidentCategory.OWNER, ResidentCategory.TENANT):
            return "SPONSOR_INELIGIBLE"
        if sponsor.status != MembershipStatus.ACTIVE:
            return "SPONSOR_INELIGIBLE"
        if sponsor.user is None or not sponsor.user.is_active or sponsor.user.email_verified_at is None:
            return "SPONSOR_INELIGIBLE"
        if not _verified_resident_roles(_active_roles(sponsor.user_id)):
            return "SPONSOR_INELIGIBLE"
        if sponsor.valid_from > today or (sponsor.valid_until and sponsor.valid_until < today):
            return "SPONSOR_INELIGIBLE"
    return "ACTIVE"


def _my_memberships():
    return db.session.scalars(
        select(Membership)
        .options(
            selectinload(Membership.household)
            .selectinload(Household.flat)
            .selectinload(Flat.tower),
            selectinload(Membership.sponsor).selectinload(Membership.user),
        )
        .where(Membership.user_id == current_user.id)
        .order_by(Membership.created_at.desc())
    ).all()


def _membership_summary(row: Membership) -> dict:
    return {
        "id": str(row.id),
        "household_id": str(row.household_id),
        "household_label": row.household.label,
        "flat": _unit(row.household.flat),
        "category": row.category.value,
        "status": row.status.value,
        "access_state": _access_state(row),
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "sponsor_membership_id": str(row.sponsor_membership_id) if row.sponsor_membership_id else None,
        "relationship_to_sponsor": row.relationship_to_sponsor,
        "is_current_occupant": row.is_current_occupant,
        "declared_current_occupant": row.declared_current_occupant,
        "occupancy_confirmed_at": row.occupancy_confirmed_at.isoformat() if row.occupancy_confirmed_at else None,
    }


def _verified_resident_roles(roles: list[str]) -> bool:
    return bool(set(roles) & {
        PermissionRole.RESIDENT.value, PermissionRole.COMMITTEE_MEMBER.value,
        PermissionRole.SOCIETY_ADMIN.value, PermissionRole.PLATFORM_ADMIN.value,
    })


def _eligible_memberships(roles=None):
    if current_user.email_verified_at is None:
        return []
    if roles is None:
        roles = _active_roles(current_user.id)
    if not _verified_resident_roles(roles):
        return []
    return [row for row in _my_memberships() if _access_state(row) == "ACTIVE"]


@residential_bp.get("/society")
def get_society():
    profile = db.session.get(SocietyProfile, 1)
    if profile is None:
        return error("SOCIETY_NOT_CONFIGURED", "Society details are unavailable.", 404)
    return jsonify({"society": {
        "name": profile.name, "address": profile.address,
        "locality": profile.locality, "city": profile.city,
    }}), 200


@residential_bp.get("/towers")
def get_towers():
    towers = db.session.scalars(select(Tower).order_by(Tower.name)).all()
    return jsonify({"towers": [{"id": str(t.id), "name": t.name} for t in towers]}), 200


@residential_bp.get("/towers/<uuid:tower_id>/flats")
def get_tower_flats(tower_id: UUID):
    if db.session.get(Tower, tower_id) is None:
        return error("TOWER_NOT_FOUND", "Tower not found.", 404)
    floor = request.args.get("floor")
    if floor is not None and (not floor.isascii() or not floor.isdecimal() or len(floor) > 3):
        return error("VALIDATION_ERROR", "floor must be a nonnegative integer.", 400)
    statement = (
        select(Flat).options(selectinload(Flat.tower))
        .where(Flat.tower_id == tower_id)
        .order_by(Flat.floor_number, Flat.flat_number)
    )
    if floor is not None:
        statement = statement.where(Flat.floor_number == int(floor))
    flats = db.session.scalars(statement).all()
    return jsonify({"flats": [_unit(row) for row in flats]}), 200


@residential_bp.get("/flats/<uuid:flat_id>")
def get_flat(flat_id: UUID):
    flat = db.session.scalar(
        select(Flat).options(selectinload(Flat.tower)).where(Flat.id == flat_id)
    )
    if flat is None:
        return error("FLAT_NOT_FOUND", "Flat not found.", 404)
    # No occupants, household labels, membership counts, or contact details.
    return jsonify({"flat": _unit(flat)}), 200


@profile_bp.get("/profile")
@login_required
def get_profile():
    return jsonify({"user": public_user(current_user)}), 200


@profile_bp.patch("/profile")
@login_required
def update_profile():
    body, failure = json_object({"display_name", "phone", "date_of_birth", "occupation"})
    if failure:
        return failure
    if not body:
        return error("VALIDATION_ERROR", "Provide at least one field to update.", 400)
    problems = {}
    name = body.get("display_name")
    if "display_name" in body and (not isinstance(name, str) or not 2 <= len(name.strip()) <= 120):
        problems["display_name"] = "Must contain 2 to 120 characters."
    phone = body.get("phone")
    if "phone" in body and phone is not None and (
        not isinstance(phone, str) or not PHONE_PATTERN.fullmatch(phone.strip())
    ):
        problems["phone"] = "Use 7 to 15 digits, optionally starting with +, or null."
    birth_value = body.get("date_of_birth")
    birth_date = None
    if "date_of_birth" in body and birth_value is not None:
        try:
            if not isinstance(birth_value, str) or len(birth_value) != 10:
                raise ValueError("Invalid date format")
            birth_date = date.fromisoformat(birth_value)
            if birth_date > _today() or birth_date.year < 1900:
                raise ValueError("Invalid birth date")
        except (ValueError, TypeError):
            problems["date_of_birth"] = "Use a real date in YYYY-MM-DD (1900 through today), or null."
    occupation = body.get("occupation")
    if "occupation" in body and occupation is not None and (
        not isinstance(occupation, str) or len(occupation.strip()) > 100
    ):
        problems["occupation"] = "Must be text up to 100 characters, or null."
    if problems:
        return error("VALIDATION_ERROR", "Check the submitted fields.", 400, fields=problems)

    changes = {}
    if "display_name" in body and name.strip() != current_user.display_name:
        current_user.display_name = name.strip()
        changes["display_name"] = True
    if "phone" in body:
        updated_phone = phone.strip() if phone is not None else None
        if updated_phone != current_user.phone:
            current_user.phone = updated_phone
            changes["phone"] = True
    if "date_of_birth" in body and birth_date != current_user.date_of_birth:
        current_user.date_of_birth = birth_date
        changes["date_of_birth"] = True
    if "occupation" in body:
        updated_occupation = occupation.strip() or None if occupation is not None else None
        if updated_occupation != current_user.occupation:
            current_user.occupation = updated_occupation
            changes["occupation"] = True
    if changes:
        db.session.add(AuditLog(
            actor=current_user, action="PROFILE_UPDATED", entity_type="USER",
            entity_id=current_user.id, details={"changed_fields": sorted(changes)},
        ))
        db.session.commit()
    return jsonify({"user": public_user(current_user)}), 200


@profile_bp.get("/memberships")
@login_required
def get_my_memberships():
    # The account owner can view their own inactive/historical memberships.
    return jsonify({"memberships": [_membership_summary(m) for m in _my_memberships()]}), 200


@profile_bp.get("/access")
@login_required
def get_my_access():
    roles = _active_roles(current_user.id)
    eligible = _eligible_memberships(roles)
    return jsonify({
        "user_id": str(current_user.id),
        "email_verified": current_user.email_verified_at is not None,
        "roles": roles,
        "verified_resident": bool(eligible),
        "active_memberships": [_membership_summary(m) for m in eligible],
        "permissions": effective_permissions(roles=roles, eligible_memberships=eligible),
    }), 200


@profile_bp.get("/households")
@login_required
def get_my_households():
    eligible = _eligible_memberships()
    if not eligible:
        return error("RESIDENT_ACCESS_REQUIRED", "Active, verified resident access is required.", 403)

    ids = {m.household_id for m in eligible}
    households = db.session.scalars(
        select(Household)
        .options(
            selectinload(Household.flat).selectinload(Flat.tower),
            selectinload(Household.memberships).selectinload(Membership.user),
            selectinload(Household.memberships).selectinload(Membership.sponsor).selectinload(Membership.user),
        )
        .where(Household.id.in_(ids))
        .order_by(Household.label)
    ).all()
    results = []
    for home in households:
        # Only share names/categories of CURRENT members in the same household.
        residents = sorted(({
            "user_id": str(member.user_id),
            "display_name": member.user.display_name,
            "category": member.category.value,
            "membership_id": str(member.id),
            "sponsor_membership_id": str(member.sponsor_membership_id) if member.sponsor_membership_id else None,
            "relationship_to_sponsor": member.relationship_to_sponsor,
            "is_current_occupant": member.is_current_occupant,
        } for member in home.memberships if _access_state(member) == "ACTIVE"),
            key=lambda member: (member["display_name"], member["user_id"]))
        results.append({
            "id": str(home.id),
            "label": home.label,
            "flat": _unit(home.flat),
            "members": residents,
        })
    return jsonify({"households": results}), 200


@profile_bp.get("/family-tree")
@login_required
def get_my_family_tree():
    """Household-scoped sponsor graph, not inferred genealogy.

    Only active and sponsor-eligible members are shown, and never contact
    details, birth dates, occupation, unrelated households or tenant/owner
    households that the viewer is not authorized to see.
    """
    response = get_my_households()
    if isinstance(response, tuple):
        # Preserve the same authorization failure as /api/me/households.
        if response[1] != 200:
            return response
        payload = response[0].get_json()
    else:
        payload = response.get_json()
    trees = []
    for household in payload["households"]:
        members = household["members"]
        ids = {member["membership_id"] for member in members}
        edges = [{
            "sponsor_membership_id": member["sponsor_membership_id"],
            "family_membership_id": member["membership_id"],
            "relationship_to_sponsor": member["relationship_to_sponsor"],
        } for member in members if member["sponsor_membership_id"] in ids]
        trees.append({
            "household_id": household["id"],
            "household_label": household["label"],
            "flat": household["flat"],
            "members": members,
            "relationships": edges,
        })
    return jsonify({"households": trees}), 200
