"""Shared, live eligibility policy for sponsorship of family memberships.

Never resolve a sponsor by flat or household alone: only the explicit
sponsor_membership_id is authoritative. The membership must belong to the
specified household AND flat; owner and tenant households can coexist.
"""
from app.modules.identity.models import Membership, ResidentCategory


def eligible_family_sponsor(
    sponsor: Membership | None,
    *,
    household_id=None,
    flat_id=None,
) -> bool:
    """Evaluate current database state; not a previous UI eligibility snapshot.

    This intentionally shares the resident role/date checks already used to
    compute live residential access, plus account and resource binding checks.
    A non-occupant OWNER may sponsor; occupancy is distinct from eligibility.
    """
    if sponsor is None or sponsor.category not in (ResidentCategory.OWNER, ResidentCategory.TENANT):
        return False
    if household_id is not None and sponsor.household_id != household_id:
        return False
    if sponsor.household is None or sponsor.household.flat_id is None:
        return False
    if flat_id is not None and sponsor.household.flat_id != flat_id:
        return False
    if sponsor.user is None or not sponsor.user.is_active or sponsor.user.email_verified_at is None:
        return False

    # Lazy import avoids circular imports between authorization and residential
    # routes, where `_access_state` is also used for family member validity.
    from app.modules.identity.residential.routes import (
        _access_state, _active_roles, _verified_resident_roles,
    )
    return (_access_state(sponsor) == "ACTIVE"
            and _verified_resident_roles(_active_roles(sponsor.user_id)))
