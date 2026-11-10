"""Module 5 domain rules: scope, lifecycle, support counting, visibility, serialization."""
import importlib
from datetime import datetime, timezone

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.modules.governance.scope import SINGLETON_SOCIETY_ID

from . import priority
from .common import display_names, iso, haversine_m
from .models import (
    ActorRole, CivicIssue, CivicLocality, DuplicateLink, EvidenceVisibility, IssueEvidence, IssueHandoff,
    IssuePrivacy, IssueState, IssueSupport, IssueTransition,
)

S = IssueState

# Which states other residents may see and support.
COMMUNITY_STATES = frozenset({S.SUBMITTED, S.UNDER_REVIEW, S.VALIDATED, S.READY_FOR_ROUTING})
# States that count as "open" for duplicate suggestions.
OPEN_STATES = COMMUNITY_STATES
SUPPORTABLE_STATES = frozenset({S.VALIDATED, S.READY_FOR_ROUTING})
REPORTER_EDITABLE = frozenset({S.DRAFT, S.NEEDS_INFO})
REPORTER_WITHDRAWABLE = frozenset({S.DRAFT, S.SUBMITTED, S.NEEDS_INFO})
EVIDENCE_EDITABLE = frozenset({S.DRAFT, S.SUBMITTED, S.NEEDS_INFO, S.UNDER_REVIEW, S.VALIDATED})

ALLOWED_TRANSITIONS = {
    S.DRAFT: {S.SUBMITTED, S.WITHDRAWN},
    S.SUBMITTED: {S.UNDER_REVIEW, S.VALIDATED, S.NEEDS_INFO, S.REJECTED, S.MERGED, S.WITHDRAWN},
    S.UNDER_REVIEW: {S.VALIDATED, S.NEEDS_INFO, S.REJECTED, S.MERGED},
    S.NEEDS_INFO: {S.SUBMITTED, S.REJECTED, S.WITHDRAWN},
    S.VALIDATED: {S.READY_FOR_ROUTING, S.NEEDS_INFO, S.REJECTED, S.MERGED},
    S.READY_FOR_ROUTING: set(),  # handed to Module 6; this module no longer changes it
    S.REJECTED: set(),
    S.MERGED: set(),
    S.WITHDRAWN: set(),
}

MIN_SUPPORTERS_DEFAULT = 3
MERGE_MAX_DISTANCE_M = 150.0
MAX_ISSUES_PER_DAY = 10
MAX_EVIDENCE_PER_ISSUE = 5


class InvalidTransition(Exception):
    def __init__(self, from_state, to_state):
        super().__init__(f"{from_state.value} -> {to_state.value}")
        self.from_state, self.to_state = from_state, to_state


def min_supporters() -> int:
    return int(current_app.config.get("CIVIC_MIN_SUPPORTERS", MIN_SUPPORTERS_DEFAULT))


def locality() -> CivicLocality | None:
    return db.session.scalar(
        select(CivicLocality).where(CivicLocality.society_id == SINGLETON_SOCIETY_ID, CivicLocality.is_active.is_(True))
        .order_by(CivicLocality.id)
    )


def within_locality(loc: CivicLocality, latitude: float, longitude: float) -> bool:
    return haversine_m(loc.center_lat, loc.center_lon, latitude, longitude) <= loc.radius_m


def transition(issue: CivicIssue, to_state: IssueState, *, actor_id, role: ActorRole, reason: str = ""):
    """Apply a legal lifecycle move and append the history row. Caller commits."""
    if to_state not in ALLOWED_TRANSITIONS[issue.state]:
        raise InvalidTransition(issue.state, to_state)
    now = datetime.now(timezone.utc)
    db.session.add(IssueTransition(
        issue_id=issue.id, actor_user_id=actor_id, actor_role=role,
        from_state=issue.state.value, to_state=to_state.value, reason=reason, created_at=now,
    ))
    issue.state = to_state
    issue.updated_at = now
    if to_state == S.SUBMITTED:
        issue.submitted_at = issue.submitted_at or now
    if to_state == S.VALIDATED:
        issue.validated_at = now


def initial_transition(issue: CivicIssue, *, actor_id, reason: str = "Issue created."):
    """History row for a freshly created issue (state already set by the caller)."""
    db.session.add(IssueTransition(
        issue_id=issue.id, actor_user_id=actor_id, actor_role=ActorRole.REPORTER,
        from_state=None, to_state=issue.state.value, reason=reason, created_at=datetime.now(timezone.utc),
    ))


# --------------------------------------------------------------- support counting

def supporter_sets(issue_ids) -> dict:
    """Distinct supporting user ids per issue.

    A canonical issue is supported by its own supporters, the supporters of its
    merged duplicates, and the reporters of those duplicates. Each identity
    counts once, so a merge never inflates the count. The canonical reporter is
    never a supporter of their own issue.
    """
    ids = list(issue_ids)
    if not ids:
        return {}
    users = {item: set() for item in ids}
    for issue_id, user_id in db.session.execute(
        select(IssueSupport.issue_id, IssueSupport.user_id).where(IssueSupport.issue_id.in_(ids))
    ):
        users[issue_id].add(user_id)
    duplicate_of = {}
    for canonical_id, duplicate_id, creator_id in db.session.execute(
        select(DuplicateLink.canonical_issue_id, DuplicateLink.duplicate_issue_id, CivicIssue.creator_id)
        .join(CivicIssue, CivicIssue.id == DuplicateLink.duplicate_issue_id)
        .where(DuplicateLink.canonical_issue_id.in_(ids))
    ):
        users[canonical_id].add(creator_id)
        duplicate_of[duplicate_id] = canonical_id
    if duplicate_of:
        for issue_id, user_id in db.session.execute(
            select(IssueSupport.issue_id, IssueSupport.user_id).where(IssueSupport.issue_id.in_(list(duplicate_of)))
        ):
            users[duplicate_of[issue_id]].add(user_id)
    for issue_id, creator_id in db.session.execute(
        select(CivicIssue.id, CivicIssue.creator_id).where(CivicIssue.id.in_(ids))
    ):
        users[issue_id].discard(creator_id)
    return users


def canonical_ids(issue_ids) -> dict:
    """Map duplicate id -> canonical id for any of `issue_ids` that were merged."""
    ids = list(issue_ids)
    if not ids:
        return {}
    return {
        duplicate_id: canonical_id for duplicate_id, canonical_id in db.session.execute(
            select(DuplicateLink.duplicate_issue_id, DuplicateLink.canonical_issue_id)
            .where(DuplicateLink.duplicate_issue_id.in_(ids))
        )
    }


# --------------------------------------------------------------- visibility

def can_view(issue: CivicIssue, viewer_id, moderator: bool) -> bool:
    if moderator or issue.creator_id == viewer_id:
        return True
    return issue.state in COMMUNITY_STATES or issue.state == S.MERGED


def evidence_visible(item: IssueEvidence, issue: CivicIssue, viewer_id, moderator: bool) -> bool:
    if moderator or issue.creator_id == viewer_id or item.uploaded_by_user_id == viewer_id:
        return True
    return item.visibility == EvidenceVisibility.RESIDENTS and can_view(issue, viewer_id, False)


def readiness(issue: CivicIssue, supporter_count: int, evidence_count: int) -> list[str]:
    """Reasons an issue cannot yet be routed; empty means ready."""
    unmet = []
    if issue.state not in (S.VALIDATED, S.READY_FOR_ROUTING):
        unmet.append("The issue must be validated by a coordinator first.")
    needed = min_supporters()
    if supporter_count < needed:
        unmet.append(f"At least {needed} verified residents must support it ({supporter_count} so far).")
    if evidence_count < 1:
        unmet.append("At least one evidence photo is required.")
    return unmet


# --------------------------------------------------------------- authority status (Module 6)

def authority_status(issue_id) -> dict | None:
    """Authoritative case status owned by Module 6, or None until that module is integrated.

    Module 6 should expose `app.modules.authority.public.case_status_for_issue(issue_id) -> dict | None`.
    Module 5 never stores or edits that status.
    """
    try:
        module = importlib.import_module("app.modules.authority.public")
    except ImportError:
        return None
    reader = getattr(module, "case_status_for_issue", None)
    return reader(issue_id) if callable(reader) else None


# --------------------------------------------------------------- serialization

def _handoff_payload(row: IssueHandoff | None) -> dict | None:
    if row is None:
        return None
    return {
        "routing_status": row.routing_status.value, "routed_at": iso(row.routed_at),
        "authority_case_id": row.authority_case_id, "acknowledged_at": iso(row.acknowledged_at),
    }


def serialize_issues(issues, *, viewer_id, moderator: bool, detail: bool = False) -> list[dict]:
    issues = list(issues)
    if not issues:
        return []
    ids = [item.id for item in issues]
    supporters = supporter_sets(ids)
    merged_into = canonical_ids(ids)
    people = display_names(item.creator_id for item in issues)
    evidence_rows = db.session.scalars(
        select(IssueEvidence).where(IssueEvidence.issue_id.in_(ids)).order_by(IssueEvidence.created_at, IssueEvidence.id)
    ).all()
    evidence_by_issue: dict = {}
    for row in evidence_rows:
        evidence_by_issue.setdefault(row.issue_id, []).append(row)
    handoffs = {
        row.canonical_issue_id: row for row in db.session.scalars(
            select(IssueHandoff).where(IssueHandoff.canonical_issue_id.in_(ids))
        )
    }
    output = []
    for issue in issues:
        group = supporters.get(issue.id, set())
        rows = evidence_by_issue.get(issue.id, [])
        shown = [row for row in rows if evidence_visible(row, issue, viewer_id, moderator)]
        reporter_sees_self = issue.creator_id == viewer_id
        shows_name = moderator or reporter_sees_self or issue.privacy == IssuePrivacy.PUBLIC_NAME
        item = {
            "id": str(issue.id),
            "locality_id": issue.locality_id,
            "title": issue.title,
            "description": issue.description,
            "category": issue.category.value,
            "severity": issue.severity.value,
            "state": issue.state.value,
            "latitude": issue.latitude,
            "longitude": issue.longitude,
            "address_hint": issue.address_hint,
            "privacy": issue.privacy.value if (moderator or reporter_sees_self) else None,
            "reporter_display_name": people.get(issue.creator_id, "") if shows_name else "A resident",
            "viewer_is_reporter": reporter_sees_self,
            "support_count": len(group),
            "viewer_has_supported": viewer_id in group,
            "evidence_count": len(shown),
            "evidence": [{
                "id": str(row.id), "caption": row.caption, "visibility": row.visibility.value,
                "mime_type": row.mime_type, "created_at": iso(row.created_at),
            } for row in shown],
            "priority": priority.compute(issue, len(group)),
            "canonical_issue_id": str(merged_into[issue.id]) if issue.id in merged_into else None,
            "handoff": _handoff_payload(handoffs.get(issue.id)),
            "created_at": iso(issue.created_at),
            "submitted_at": iso(issue.submitted_at),
            "validated_at": iso(issue.validated_at),
            "updated_at": iso(issue.updated_at),
        }
        if moderator:
            item["reporter_user_id"] = str(issue.creator_id)
        if detail:
            item["authoritative_status"] = authority_status(issue.id)
            if moderator or reporter_sees_self or issue.state in (S.VALIDATED, S.READY_FOR_ROUTING):
                item["readiness"] = {
                    "unmet": readiness(issue, len(group), len(rows)),
                    "required_supporters": min_supporters(),
                }
        output.append(item)
    return output
