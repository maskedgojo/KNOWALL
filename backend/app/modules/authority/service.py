"""Module 6 domain rules: case lifecycle, history, jurisdiction, verification, escalation sweep."""
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.modules.civic.common import aware, display_names, iso
from app.modules.civic.models import CivicIssue, IssueHandoff
from app.modules.civic.service import supporter_sets
from app.modules.identity.models import RoleAssignment

from .models import (
    ActorKind, AuthorityCase, AuthorityOfficer, CaseEvent, CaseMetricSnapshot, CaseNotification, CaseStatus,
    CaseTransfer, ClosureBasis, Department, EscalationEvent, EscalationKind, EscalationOutcome, EscalationRule,
    JurisdictionRule, ResolutionEvidence, ResolutionVerification, Verdict,
)

C = CaseStatus

ALLOWED = {
    C.ROUTED: {C.ACKNOWLEDGED, C.ROUTED},                     # ROUTED -> ROUTED is a transfer
    C.ACKNOWLEDGED: {C.IN_PROGRESS, C.CLARIFICATION_REQUESTED, C.ROUTED},
    C.IN_PROGRESS: {C.IN_PROGRESS, C.CLARIFICATION_REQUESTED, C.RESOLVED},
    C.CLARIFICATION_REQUESTED: {C.ACKNOWLEDGED, C.IN_PROGRESS},
    C.RESOLVED: {C.CLOSED, C.REOPENED},
    C.REOPENED: {C.IN_PROGRESS, C.CLARIFICATION_REQUESTED},
    C.CLOSED: set(),
}
OPEN_STATUSES = frozenset({C.ROUTED, C.ACKNOWLEDGED, C.CLARIFICATION_REQUESTED, C.IN_PROGRESS, C.REOPENED})
TRANSFERABLE = frozenset({C.ROUTED, C.ACKNOWLEDGED})
WORKABLE = frozenset({C.ACKNOWLEDGED, C.IN_PROGRESS, C.REOPENED})  # progress / evidence / clarification
ESCALATABLE = OPEN_STATUSES

STATUS_LABELS = {
    C.ROUTED: "Sent to department",
    C.ACKNOWLEDGED: "Accepted by department",
    C.CLARIFICATION_REQUESTED: "Department needs more details",
    C.IN_PROGRESS: "Work in progress",
    C.RESOLVED: "Marked fixed - awaiting resident verification",
    C.REOPENED: "Reopened after residents disputed the fix",
    C.CLOSED: "Closed after verification",
}

DEFAULTS = {
    "AUTHORITY_DEFAULT_SLA_HOURS": 168,
    "AUTHORITY_VERIFY_WINDOW_HOURS": 72,
    "AUTHORITY_CLOSE_CONFIRMATIONS": 2,
    "AUTHORITY_REOPEN_DISPUTES": 2,
    "AUTHORITY_MAX_TRANSFERS": 3,
}
MAX_EVIDENCE_PER_ROUND = 5


def setting(name: str) -> int:
    return int(current_app.config.get(name, DEFAULTS[name]))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InvalidCaseTransition(Exception):
    def __init__(self, from_status: CaseStatus, to_status: CaseStatus):
        super().__init__(f"{from_status.value} -> {to_status.value}")
        self.from_status, self.to_status = from_status, to_status


class AppendOnlyViolation(RuntimeError):
    pass


APPEND_ONLY = (CaseEvent, CaseTransfer, ResolutionEvidence, ResolutionVerification)


@event.listens_for(Session, "before_flush")
def _guard_append_only(session, _context, _instances):
    """Case history, transfers, official evidence and verdicts can never be edited or deleted."""
    for obj in session.deleted:
        if isinstance(obj, APPEND_ONLY):
            raise AppendOnlyViolation(f"{type(obj).__name__} rows are append-only and cannot be deleted.")
    for obj in session.dirty:
        if isinstance(obj, APPEND_ONLY) and session.is_modified(obj, include_collections=False):
            raise AppendOnlyViolation(f"{type(obj).__name__} rows are append-only and cannot be changed.")


# --------------------------------------------------------------- lookups

def fetch_case_locked(case_id) -> AuthorityCase | None:
    return db.session.scalar(select(AuthorityCase).where(AuthorityCase.id == case_id).with_for_update())


def case_for_issue(issue_id) -> AuthorityCase | None:
    return db.session.scalar(select(AuthorityCase).where(AuthorityCase.civic_issue_id == issue_id))


def handoff_for(issue_id) -> IssueHandoff | None:
    return db.session.scalar(select(IssueHandoff).where(IssueHandoff.canonical_issue_id == issue_id))


def department_officer_ids(department_id: int) -> list:
    return list(db.session.scalars(select(AuthorityOfficer.user_id).where(
        AuthorityOfficer.department_id == department_id, AuthorityOfficer.revoked_at.is_(None))))


def coordinator_ids() -> list:
    return list(db.session.scalars(select(RoleAssignment.user_id).where(
        RoleAssignment.revoked_at.is_(None),
        RoleAssignment.role.in_(["SOCIETY_ADMIN", "PLATFORM_ADMIN"]),
    ).distinct()))


def affected_user_ids(case: AuthorityCase) -> set:
    """Reporter plus everyone counted as a supporter by Module 5 (including merged duplicates)."""
    issue = db.session.get(CivicIssue, case.civic_issue_id)
    people = set(supporter_sets([case.civic_issue_id]).get(case.civic_issue_id, set()))
    if issue is not None:
        people.add(issue.creator_id)
    return people


def covers(department: Department, locality_id: int, category: str) -> bool:
    return db.session.scalar(select(JurisdictionRule.id).where(
        JurisdictionRule.department_id == department.id, JurisdictionRule.locality_id == locality_id,
        JurisdictionRule.category == category)) is not None


def pick_department(locality_id: int, category: str) -> Department | None:
    return db.session.scalar(
        select(Department).join(JurisdictionRule, JurisdictionRule.department_id == Department.id)
        .where(JurisdictionRule.locality_id == locality_id, JurisdictionRule.category == category,
               Department.is_active.is_(True))
        .order_by(JurisdictionRule.priority, Department.id)
    )


def sla_hours(department_id: int) -> int:
    rule = db.session.scalar(select(EscalationRule).where(EscalationRule.department_id == department_id))
    return rule.threshold_hours if rule else setting("AUTHORITY_DEFAULT_SLA_HOURS")


def escalation_target(department: Department) -> str:
    rule = db.session.scalar(select(EscalationRule).where(EscalationRule.department_id == department.id))
    if rule:
        return rule.target_label
    if department.escalation_department_id:
        target = db.session.get(Department, department.escalation_department_id)
        if target:
            return target.name
    return "Society coordinator"


def is_overdue(case: AuthorityCase, at: datetime | None = None) -> bool:
    return case.status in OPEN_STATUSES and aware(case.due_at) < (at or now_utc())


# --------------------------------------------------------------- history and notifications

def record(case: AuthorityCase, *, action: str, to_status: CaseStatus, actor_id, actor_kind: ActorKind,
           reason: str = "", public_summary: str = "", details: dict | None = None, at: datetime | None = None,
           check: bool = True, initial: bool = False) -> CaseEvent:
    """Append one history event and apply the status. Caller commits.

    `check=False` is only for the first (intake) event and for non-status events that keep the status.
    """
    if check and to_status not in ALLOWED[case.status]:
        raise InvalidCaseTransition(case.status, to_status)
    when = at or now_utc()
    case.event_count = (case.event_count or 0) + 1
    row = CaseEvent(
        case_id=case.id, sequence=case.event_count, actor_user_id=actor_id, actor_kind=actor_kind, action=action,
        from_status=None if initial else case.status.value, to_status=to_status.value, reason=reason,
        public_summary=public_summary, department_id=case.department_id, details=details, created_at=when,
    )
    db.session.add(row)
    case.status = to_status
    case.updated_at = when
    return row


def notify(case: AuthorityCase, recipients, event_type: str, message: str):
    for user_id in {item for item in recipients if item is not None}:
        db.session.add(CaseNotification(
            case_id=case.id, recipient_user_id=user_id, event_type=event_type, message=message[:300]))


def notify_residents(case: AuthorityCase, event_type: str, message: str):
    notify(case, affected_user_ids(case), event_type, message)


def notify_department(case: AuthorityCase, event_type: str, message: str):
    notify(case, department_officer_ids(case.department_id), event_type, message)


def close_open_escalations(case: AuthorityCase, outcome: EscalationOutcome, at: datetime):
    for row in db.session.scalars(select(EscalationEvent).where(
            EscalationEvent.case_id == case.id, EscalationEvent.outcome == EscalationOutcome.OPEN)):
        row.outcome = outcome
        row.outcome_at = at


# --------------------------------------------------------------- verification

def tally(case: AuthorityCase, round_number: int | None = None) -> dict:
    target = case.round if round_number is None else round_number
    rows = db.session.execute(
        select(ResolutionVerification.verdict, func.count()).where(
            ResolutionVerification.case_id == case.id, ResolutionVerification.round == target)
        .group_by(ResolutionVerification.verdict)
    ).all()
    counts = {Verdict.CONFIRMED.value: 0, Verdict.DISPUTED.value: 0}
    for verdict, total in rows:
        counts[verdict.value] = total
    return {"round": target, "confirmed": counts["CONFIRMED"], "disputed": counts["DISPUTED"],
            "close_threshold": setting("AUTHORITY_CLOSE_CONFIRMATIONS"),
            "reopen_threshold": setting("AUTHORITY_REOPEN_DISPUTES")}


def close_case(case: AuthorityCase, basis: ClosureBasis, *, actor_id, actor_kind: ActorKind, reason: str,
               at: datetime):
    record(case, action="CLOSED", to_status=C.CLOSED, actor_id=actor_id, actor_kind=actor_kind, reason=reason,
           public_summary="Case closed after residents verified the fix.", details={"basis": basis.value}, at=at)
    case.closed_at = at
    case.closure_basis = basis
    case.verification_closes_at = None
    close_open_escalations(case, EscalationOutcome.CLOSED, at)
    notify_residents(case, "CASE_VERIFIED", f"Case {case.reference} was closed after verification.")
    notify_department(case, "CASE_VERIFIED", f"Case {case.reference} was verified by residents and closed.")


def reopen_case(case: AuthorityCase, *, actor_id, actor_kind: ActorKind, reason: str, at: datetime,
                summary: str = "Residents disputed the fix. The same case was reopened for the department."):
    record(case, action="REOPENED", to_status=C.REOPENED, actor_id=actor_id, actor_kind=actor_kind, reason=reason,
           public_summary=summary, details={"previous_round": case.round}, at=at)
    case.round += 1
    case.reopen_count += 1
    case.resolved_at = None
    case.verification_closes_at = None
    case.due_at = at + timedelta(hours=sla_hours(case.department_id))
    notify_department(case, "CASE_REOPENED", f"Case {case.reference} was reopened: {reason}"[:300])
    notify_residents(case, "CASE_UPDATED", f"Case {case.reference} was reopened for further work.")


def apply_verdict_rules(case: AuthorityCase, at: datetime) -> str | None:
    """After a vote: close or reopen when a threshold is reached. Returns the action taken, if any."""
    counts = tally(case)
    if counts["disputed"] >= counts["reopen_threshold"] and counts["disputed"] >= counts["confirmed"]:
        reopen_case(case, actor_id=None, actor_kind=ActorKind.SYSTEM, at=at,
                    reason=f"{counts['disputed']} affected residents disputed the claimed fix.")
        return "REOPENED"
    if counts["confirmed"] >= counts["close_threshold"] and counts["confirmed"] > counts["disputed"]:
        close_case(case, ClosureBasis.COMMUNITY_VERIFIED, actor_id=None, actor_kind=ActorKind.SYSTEM, at=at,
                   reason=f"{counts['confirmed']} affected residents confirmed the fix.")
        return "CLOSED"
    return None


# --------------------------------------------------------------- periodic job

def sweep(at: datetime | None = None, trigger: str = "SWEEP") -> dict:
    """Idempotent catch-up job: overdue escalations and expired verification windows. Caller commits.

    Safe to run any number of times and after downtime: each overdue cycle escalates once
    (unique per case + due time), and an expired window is settled once.
    """
    at = at or now_utc()
    report = {"escalated": 0, "closed": 0, "reopened": 0, "awaiting_coordinator": 0}
    overdue = db.session.scalars(select(AuthorityCase).where(
        AuthorityCase.status.in_(list(OPEN_STATUSES)), AuthorityCase.due_at < at,
    ).with_for_update()).all()
    for case in overdue:
        if escalate(case, EscalationKind.AUTO_OVERDUE, actor_id=None, at=at,
                    reason="Demo SLA deadline passed without resolution."):
            report["escalated"] += 1
    expired = db.session.scalars(select(AuthorityCase).where(
        AuthorityCase.status == C.RESOLVED, AuthorityCase.verification_closes_at.is_not(None),
        AuthorityCase.verification_closes_at < at,
    ).with_for_update()).all()
    for case in expired:
        counts = tally(case)
        if counts["confirmed"] > counts["disputed"]:
            close_case(case, ClosureBasis.WINDOW_MAJORITY, actor_id=None, actor_kind=ActorKind.SYSTEM, at=at,
                       reason=f"Verification window ended: {counts['confirmed']} confirmed, "
                              f"{counts['disputed']} disputed.")
            report["closed"] += 1
        elif counts["disputed"] > 0:
            reopen_case(case, actor_id=None, actor_kind=ActorKind.SYSTEM, at=at,
                        reason=f"Verification window ended: {counts['disputed']} disputed, "
                               f"{counts['confirmed']} confirmed.")
            report["reopened"] += 1
        else:
            already = any((row.details or {}).get("round") == case.round for row in db.session.scalars(
                select(CaseEvent).where(CaseEvent.case_id == case.id, CaseEvent.action == "VERIFICATION_EXPIRED")))
            if not already:
                record(case, action="VERIFICATION_EXPIRED", to_status=C.RESOLVED, actor_id=None,
                       actor_kind=ActorKind.SYSTEM, at=at, check=False, details={"round": case.round},
                       reason="Verification window ended with no resident votes; awaiting coordinator.")
                notify(case, coordinator_ids(), "VERIFICATION_EXPIRED",
                       f"Case {case.reference}: no resident verified the fix. A coordinator must decide.")
                report["awaiting_coordinator"] += 1
    db.session.add(CaseMetricSnapshot(trigger=trigger, counts={**status_counts(), **report}, created_at=at))
    return report


def escalate(case: AuthorityCase, kind: EscalationKind, *, actor_id, at: datetime, reason: str) -> EscalationEvent | None:
    """Create the escalation for the current due cycle. Returns None if it already exists."""
    due = aware(case.due_at)
    exists = db.session.scalar(select(EscalationEvent.id).where(
        EscalationEvent.case_id == case.id, EscalationEvent.kind == kind, EscalationEvent.due_at_snapshot == due))
    if exists:
        return None
    department = db.session.get(Department, case.department_id)
    target = escalation_target(department)
    row = EscalationEvent(case_id=case.id, kind=kind, due_at_snapshot=due, target_label=target, reason=reason,
                          triggered_by_user_id=actor_id, triggered_at=at)
    db.session.add(row)
    record(case, action="ESCALATED", to_status=case.status, actor_id=actor_id, check=False, at=at,
           actor_kind=ActorKind.SYSTEM if actor_id is None else ActorKind.COORDINATOR, reason=reason,
           public_summary=f"Escalated to {target} (simulated).",
           details={"kind": kind.value, "target": target, "due_at": iso(due)})
    notify(case, coordinator_ids(), "CASE_ESCALATED", f"Case {case.reference} escalated: {reason}"[:300])
    notify_department(case, "CASE_ESCALATED", f"Case {case.reference} was escalated to {target}.")
    return row


def status_counts() -> dict:
    counts = {item.value: 0 for item in CaseStatus}
    for status, total in db.session.execute(
            select(AuthorityCase.status, func.count()).group_by(AuthorityCase.status)):
        counts[status.value] = total
    return {"by_status": counts}


# --------------------------------------------------------------- serialization

def department_json(department: Department | None) -> dict | None:
    if department is None:
        return None
    return {"id": department.id, "code": department.code, "name": department.name,
            "description": department.description, "contact_label": department.contact_label,
            "requires_resolution_proof": department.requires_resolution_proof,
            "escalation_department_id": department.escalation_department_id,
            "is_demo": department.is_demo, "is_active": department.is_active,
            "label": "Simulated demo department"}


def evidence_json(row: ResolutionEvidence) -> dict:
    return {"id": str(row.id), "round": row.round, "evidence_type": row.evidence_type.value, "caption": row.caption,
            "mime_type": row.mime_type, "created_at": iso(row.created_at)}


def event_json(row: CaseEvent, names: dict, *, staff_view: bool) -> dict:
    item = {"sequence": row.sequence, "action": row.action, "from_status": row.from_status,
            "to_status": row.to_status, "public_summary": row.public_summary, "actor_kind": row.actor_kind.value,
            "at": iso(row.created_at)}
    if staff_view:
        item.update({"reason": row.reason, "actor_display_name": names.get(row.actor_user_id, ""),
                     "department_id": row.department_id, "details": row.details})
    return item


def events_for(case: AuthorityCase) -> list[CaseEvent]:
    return list(db.session.scalars(
        select(CaseEvent).where(CaseEvent.case_id == case.id).order_by(CaseEvent.sequence)))


def public_status(case: AuthorityCase) -> dict:
    """What Module 5 shows on the civic issue. Module 6 is the owner of record for this status."""
    department = db.session.get(Department, case.department_id)
    return {
        "authority_case_id": case.reference,
        "case_id": str(case.id),
        "status": case.status.value,
        "status_label": STATUS_LABELS[case.status],
        "department": {"id": department.id, "name": department.name, "is_demo": department.is_demo}
        if department else None,
        "is_overdue": is_overdue(case),
        "due_at": iso(case.due_at),
        "round": case.round,
        "reopen_count": case.reopen_count,
        "resolved_at": iso(case.resolved_at),
        "verification_closes_at": iso(case.verification_closes_at),
        "closed_at": iso(case.closed_at),
        "closure_basis": case.closure_basis.value if case.closure_basis else None,
        "updated_at": iso(case.updated_at),
        "simulated": True,
    }


def case_json(case: AuthorityCase, *, detail: bool = False) -> dict:
    """Staff (official / coordinator) view of a case."""
    handoff = handoff_for(case.civic_issue_id)
    payload = handoff.payload if handoff else {}
    item = {
        **public_status(case),
        "civic_issue_id": str(case.civic_issue_id),
        "department": department_json(db.session.get(Department, case.department_id)),
        "owner_user_id": str(case.owner_user_id) if case.owner_user_id else None,
        "owner_display_name": display_names([case.owner_user_id]).get(case.owner_user_id, "")
        if case.owner_user_id else "",
        "title": payload.get("title", ""),
        "category": payload.get("category", ""),
        "severity": payload.get("severity", ""),
        "community_support": payload.get("community_support", 0),
        "created_at": iso(case.created_at),
    }
    if not detail:
        return item
    events = events_for(case)
    names = display_names([row.actor_user_id for row in events])
    transfers = db.session.scalars(
        select(CaseTransfer).where(CaseTransfer.case_id == case.id).order_by(CaseTransfer.created_at)).all()
    escalations = db.session.scalars(
        select(EscalationEvent).where(EscalationEvent.case_id == case.id).order_by(EscalationEvent.triggered_at)).all()
    evidence = db.session.scalars(select(ResolutionEvidence).where(ResolutionEvidence.case_id == case.id)
                                  .order_by(ResolutionEvidence.created_at, ResolutionEvidence.id)).all()
    verifications = db.session.scalars(select(ResolutionVerification).where(
        ResolutionVerification.case_id == case.id).order_by(ResolutionVerification.created_at)).all()
    voter_names = display_names([row.user_id for row in verifications])
    from .models import CaseClarification  # local import keeps the top import list short
    clarifications = db.session.scalars(select(CaseClarification).where(
        CaseClarification.case_id == case.id).order_by(CaseClarification.asked_at)).all()
    item.update({
        "issue": {
            "summary": payload.get("summary", ""), "location": payload.get("location", {}),
            "evidence": payload.get("evidence", []), "priority": payload.get("priority"),
            "merged_duplicate_issue_ids": payload.get("merged_duplicate_issue_ids", []),
            "validated_at": payload.get("validated_at"),
        },
        "events": [event_json(row, names, staff_view=True) for row in events],
        "transfers": [{"from_department_id": row.from_department_id, "to_department_id": row.to_department_id,
                       "reason": row.reason, "at": iso(row.created_at)} for row in transfers],
        "escalations": [{"id": str(row.id), "kind": row.kind.value, "target_label": row.target_label,
                         "reason": row.reason, "due_at_snapshot": iso(row.due_at_snapshot),
                         "triggered_at": iso(row.triggered_at), "outcome": row.outcome.value,
                         "outcome_at": iso(row.outcome_at)} for row in escalations],
        "evidence": [evidence_json(row) for row in evidence],
        "verifications": [{"id": str(row.id), "round": row.round, "verdict": row.verdict.value, "reason": row.reason,
                           "has_photo": row.photo_storage_key is not None,
                           "resident_display_name": voter_names.get(row.user_id, ""),
                           "at": iso(row.created_at)} for row in verifications],
        "clarifications": [{"id": str(row.id), "question": row.question, "status": row.status.value,
                            "response": row.response, "asked_at": iso(row.asked_at),
                            "responded_at": iso(row.responded_at)} for row in clarifications],
        "tally": tally(case),
    })
    return item
