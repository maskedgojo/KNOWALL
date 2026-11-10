"""Shared helpers for Module 6 routes: who may act, request parsing, audit.

Identity and permissions come from Module 1. Coordinators hold the shared admin
grant (the same one Module 5 uses for civic moderation). Simulated officials are
verified accounts with an active row in `authority_officers`.
"""
from functools import wraps

from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.modules.civic.common import (  # noqa: F401  (re-exported for Module 6 routes)
    audit, iso, json_body, no_store, pagination, safe_text, validation_error,
)
from app.modules.governance.schema import schema_required
from app.modules.identity.access import has_permission
from app.modules.identity.auth.routes import error

from .models import AuthorityOfficer, Department

AUTHORITY_TABLES = (
    "authority_departments", "authority_jurisdiction_rules", "authority_escalation_rules", "authority_officers",
    "authority_cases", "authority_case_events", "authority_case_transfers", "authority_escalation_events",
    "authority_resolution_evidence", "authority_resolution_verifications", "authority_case_clarifications",
    "authority_case_notifications", "authority_metric_snapshots",
    # Module 5 tables this module reads.
    "civic_issues", "civic_issue_handoffs",
)

COORDINATOR_PERMISSION = "identity.admin.manage"
RESIDENT_PERMISSION = "civic.issues.support"

SIMULATION_NOTICE = (
    "Simulated authority workflow for demonstration. These departments and officials are not real "
    "government bodies, and nothing is sent to any government system."
)


def schema_missing():
    return schema_required(*AUTHORITY_TABLES)


def is_coordinator() -> bool:
    return has_permission(COORDINATOR_PERMISSION)


def current_officer() -> AuthorityOfficer | None:
    """Active officer assignment of the signed-in user, only if its department is active."""
    if not current_user.is_authenticated or current_user.email_verified_at is None:
        return None
    return db.session.scalar(
        select(AuthorityOfficer)
        .join(Department, Department.id == AuthorityOfficer.department_id)
        .where(AuthorityOfficer.user_id == current_user.id, AuthorityOfficer.revoked_at.is_(None),
               Department.is_active.is_(True))
    )


def coordinator(view):
    @wraps(view)
    @login_required
    def protected(*args, **kwargs):
        if not is_coordinator():
            return error("FORBIDDEN", "You do not have permission for this action.", 403)
        return view(*args, **kwargs)
    return protected


def staff(view):
    """Simulated officials and coordinators."""
    @wraps(view)
    @login_required
    def protected(*args, **kwargs):
        if current_officer() is None and not is_coordinator():
            return error("FORBIDDEN", "Only simulated department officials and coordinators can do this.", 403)
        return view(*args, **kwargs)
    return protected


def official(view):
    """Simulated officials only. Per-case department scope is checked by the route."""
    @wraps(view)
    @login_required
    def protected(*args, **kwargs):
        if current_officer() is None:
            return error("FORBIDDEN", "Only a simulated department official can do this.", 403)
        return view(*args, **kwargs)
    return protected


def not_assigned():
    return error("NOT_ASSIGNED", "This case is not assigned to your department.", 403)
