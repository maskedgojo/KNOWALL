"""KNOWALL V1 single-society, request-scoped permission policy.

Account roles and resident categories are deliberately separate. The role
RESIDENT alone does not confer society access: a valid ACTIVE membership is
required. Admin permission is a verified, currently assigned admin role.

All downstream Flask modules MUST enforce these permissions server-side,
plus their own resource/ownership/eligibility rules; frontend permission
arrays are display hints only.
"""
from functools import wraps

from flask_login import current_user, login_required


ACCOUNT_PERMISSIONS = frozenset({
    "identity.profile.read",
    "identity.profile.update",
    "identity.applications.manage_own",
    "identity.documents.manage_own",
    "identity.invitations.view_own",
})
VERIFIED_ACCOUNT_PERMISSIONS = frozenset({
    "identity.applications.submit",
    "identity.invitations.accept",
})
RESIDENT_PERMISSIONS = frozenset({
    "identity.households.read",
    "identity.invitations.create",
    # Module 2–6 contracts. Owning module must enforce contextual checks.
    "society.notices.read",
    "society.maintenance.create",
    "society.facilities.book",
    "locality.listings.suggest",
    "civic.issues.create",
    "civic.issues.support",
})
ADMIN_PERMISSIONS = frozenset({
    "identity.admin.manage",
    "identity.admin.applications.read",
    "identity.admin.applications.decide",
    "identity.admin.memberships.manage",
    "identity.admin.audit.read",
    "identity.admin.documents.review",
    "identity.invitations.create",
})
# Official notice publishing. SOCIETY_ADMIN only; not part of shared admin or resident grants.
SOCIETY_ADMIN_PERMISSIONS = frozenset({
    "society.notices.manage",
    # Module 3: facilities, booking decisions, events, maintenance, projects.
    "society.operations.manage",
})
KNOWN_PERMISSIONS = (ACCOUNT_PERMISSIONS | VERIFIED_ACCOUNT_PERMISSIONS |
                     RESIDENT_PERMISSIONS | ADMIN_PERMISSIONS | SOCIETY_ADMIN_PERMISSIONS)
ADMIN_ROLES = frozenset({"SOCIETY_ADMIN", "PLATFORM_ADMIN"})


def effective_permissions(*, roles=None, eligible_memberships=None) -> list[str]:
    """Recompute effective permissions from persisted roles and membership state.

    Optional supplied values let /api/me/access reuse its own lookups. This
    function operates on the authenticated current_user, not an arbitrary ID.
    """
    if not current_user.is_authenticated or not current_user.is_active:
        return []

    # Import lazily to avoid cyclic imports with existing residential routes.
    from app.modules.identity.residential.routes import _active_roles, _eligible_memberships

    if roles is None:
        roles = _active_roles(current_user.id)
    role_names = set(roles)

    permissions = set(ACCOUNT_PERMISSIONS)
    if current_user.email_verified_at is None:
        return sorted(permissions)
    permissions.update(VERIFIED_ACCOUNT_PERMISSIONS)

    if eligible_memberships is None:
        eligible_memberships = _eligible_memberships(roles)
    if eligible_memberships:
        permissions.update(RESIDENT_PERMISSIONS)
    if role_names.intersection(ADMIN_ROLES):
        permissions.update(ADMIN_PERMISSIONS)
    if "SOCIETY_ADMIN" in role_names:
        permissions.update(SOCIETY_ADMIN_PERMISSIONS)
    return sorted(permissions)


def has_permission(permission: str) -> bool:
    """Check an explicitly registered permission; unknown names fail closed."""
    return permission in KNOWN_PERMISSIONS and permission in effective_permissions()


def requires_permission(permission: str):
    """Route decorator. Apply to every downstream module's protected routes.

    Does not replace per-object access checks (e.g., owning an application).
    """
    if permission not in KNOWN_PERMISSIONS:
        raise ValueError(f"Unknown KNOWALL permission: {permission}")

    def decorate(view):
        @wraps(view)
        @login_required
        def protected(*args, **kwargs):
            if not has_permission(permission):
                from app.modules.identity.auth.routes import error
                return error("FORBIDDEN", "You do not have permission for this action.", 403)
            return view(*args, **kwargs)
        return protected
    return decorate
