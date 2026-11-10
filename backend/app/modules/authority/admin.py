"""Department directory, simulated officials, oversight analytics and the periodic sweep."""
import statistics
from datetime import datetime, timezone

import click
from flask import Blueprint
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.civic.common import aware, display_names
from app.modules.civic.models import CivicLocality, IssueCategory, IssueHandoff, RoutingStatus
from app.modules.governance.scope import SINGLETON_SOCIETY_ID
from app.modules.identity.auth.routes import error
from app.modules.identity.models import AccountStatus, User

from .common import (
    SIMULATION_NOTICE, audit, coordinator, current_officer, is_coordinator, iso, json_body, no_store, safe_text,
    schema_missing, staff, validation_error,
)
from .models import (
    AuthorityCase, AuthorityOfficer, CaseEvent, CaseMetricSnapshot, CaseStatus, CaseTransfer, ClosureBasis,
    Department, EscalationEvent, EscalationKind, EscalationOutcome, EscalationRule, JurisdictionRule,
    ResolutionVerification, Verdict,
)
from .service import OPEN_STATUSES, department_json, is_overdue, sweep

admin_bp = Blueprint("authority_admin", __name__)
C = CaseStatus


# --------------------------------------------------------------- who am I

@admin_bp.get("/api/authority/me")
@login_required
def me():
    missing = schema_missing()
    if missing:
        return missing
    officer = current_officer()
    department = db.session.get(Department, officer.department_id) if officer else None
    return no_store({
        "officer": {"id": str(officer.id), "title": officer.title, "department": department_json(department)}
        if officer else None,
        "is_coordinator": is_coordinator(),
        "simulation_notice": SIMULATION_NOTICE,
    })


# --------------------------------------------------------------- departments

def _rules_json(department_id: int) -> list[dict]:
    return [{"id": row.id, "locality_id": row.locality_id, "category": row.category, "priority": row.priority}
            for row in db.session.scalars(select(JurisdictionRule).where(
                JurisdictionRule.department_id == department_id).order_by(JurisdictionRule.category))]


def _escalation_json(department_id: int) -> dict | None:
    row = db.session.scalar(select(EscalationRule).where(EscalationRule.department_id == department_id))
    return {"threshold_hours": row.threshold_hours, "target_label": row.target_label} if row else None


@admin_bp.get("/api/authority/departments")
@staff
def list_departments():
    missing = schema_missing()
    if missing:
        return missing
    rows = db.session.scalars(select(Department).where(Department.society_id == SINGLETON_SOCIETY_ID)
                              .order_by(Department.name)).all()
    officers = {}
    if is_coordinator():
        for row in db.session.scalars(select(AuthorityOfficer).where(AuthorityOfficer.revoked_at.is_(None))):
            officers.setdefault(row.department_id, []).append(row)
    names = display_names(row.user_id for group in officers.values() for row in group)
    return no_store({"departments": [{
        **department_json(row), "jurisdiction": _rules_json(row.id), "escalation_rule": _escalation_json(row.id),
        **({"officers": [{"id": str(item.id), "user_id": str(item.user_id), "title": item.title,
                          "display_name": names.get(item.user_id, "")} for item in officers.get(row.id, [])]}
           if is_coordinator() else {}),
    } for row in rows], "simulation_notice": SIMULATION_NOTICE})


def _department_fields(body: dict, problems: dict, *, partial: bool) -> dict:
    values = {}
    for name, minimum, maximum in (("name", 3, 120), ("description", 0, 1000), ("contact_label", 0, 160)):
        if name in body or not partial:
            required = name == "name" and not partial
            value = safe_text(body.get(name, "" if not required else None), name, minimum, maximum, problems,
                              required=required)
            if value is not None:
                values[name] = value
    if "code" in body or not partial:
        code = body.get("code")
        if not isinstance(code, str) or not code.isascii() or not code.replace("_", "").isalnum() \
                or not 2 <= len(code) <= 30:
            problems["code"] = "Use 2-30 letters, digits or underscores."
        else:
            values["code"] = code.upper()
    for name in ("requires_resolution_proof", "is_active"):
        if name in body:
            if not isinstance(body[name], bool):
                problems[name] = "Must be true or false."
            else:
                values[name] = body[name]
    if "escalation_department_id" in body:
        target = body["escalation_department_id"]
        if target is not None and (isinstance(target, bool) or not isinstance(target, int)
                                   or db.session.get(Department, target) is None):
            problems["escalation_department_id"] = "Choose an existing department or null."
        else:
            values["escalation_department_id"] = target
    return values


@admin_bp.post("/api/authority/admin/departments")
@coordinator
def create_department():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"code", "name", "description", "contact_label", "requires_resolution_proof",
                               "escalation_department_id"})
    if failure:
        return failure
    problems: dict = {}
    values = _department_fields(body, problems, partial=False)
    if problems:
        return validation_error(problems)
    row = Department(society_id=SINGLETON_SOCIETY_ID, is_demo=True, is_active=True, **values)
    db.session.add(row)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        return error("DEPARTMENT_EXISTS", "A department with this code already exists.", 409)
    audit("AUTHORITY_DEPARTMENT_CREATED", "authority_department", None, {"department_id": row.id, "code": row.code})
    db.session.commit()
    return no_store({"department": department_json(row)}, 201)


@admin_bp.patch("/api/authority/admin/departments/<int:department_id>")
@coordinator
def update_department(department_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"name", "description", "contact_label", "requires_resolution_proof", "is_active",
                               "escalation_department_id"})
    if failure:
        return failure
    row = db.session.get(Department, department_id)
    if row is None:
        return error("DEPARTMENT_NOT_FOUND", "Department not found.", 404)
    problems: dict = {}
    values = _department_fields(body, problems, partial=True)
    if values.get("escalation_department_id") == department_id:
        problems["escalation_department_id"] = "A department cannot escalate to itself."
    if problems:
        return validation_error(problems)
    for key, value in values.items():
        setattr(row, key, value)
    audit("AUTHORITY_DEPARTMENT_UPDATED", "authority_department", None,
          {"department_id": row.id, "fields": sorted(values)})
    db.session.commit()
    return no_store({"department": department_json(row)})


@admin_bp.put("/api/authority/admin/departments/<int:department_id>/jurisdiction")
@coordinator
def set_jurisdiction(department_id):
    """Replace the department's category coverage for the active locality."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"categories", "priority"})
    if failure:
        return failure
    row = db.session.get(Department, department_id)
    if row is None:
        return error("DEPARTMENT_NOT_FOUND", "Department not found.", 404)
    problems: dict = {}
    categories = body.get("categories")
    valid = {item.value for item in IssueCategory}
    if not isinstance(categories, list) or not all(isinstance(item, str) and item in valid for item in categories):
        problems["categories"] = "Choose from: " + ", ".join(sorted(valid)) + "."
    priority = body.get("priority", 100)
    if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 1000:
        problems["priority"] = "Must be a number from 1 to 1000."
    locality = db.session.scalar(select(CivicLocality).where(
        CivicLocality.society_id == SINGLETON_SOCIETY_ID, CivicLocality.is_active.is_(True)).order_by(CivicLocality.id))
    if locality is None:
        problems["locality"] = "The civic coverage area is not configured (Module 5 seed)."
    if problems:
        return validation_error(problems)
    for rule in db.session.scalars(select(JurisdictionRule).where(JurisdictionRule.department_id == row.id)):
        db.session.delete(rule)
    db.session.flush()
    for category in sorted(set(categories)):
        db.session.add(JurisdictionRule(department_id=row.id, locality_id=locality.id, category=category,
                                        priority=priority))
    audit("AUTHORITY_JURISDICTION_SET", "authority_department", None,
          {"department_id": row.id, "categories": sorted(set(categories))})
    db.session.commit()
    return no_store({"jurisdiction": _rules_json(row.id)})


@admin_bp.put("/api/authority/admin/departments/<int:department_id>/escalation-rule")
@coordinator
def set_escalation_rule(department_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"threshold_hours", "target_label"})
    if failure:
        return failure
    if db.session.get(Department, department_id) is None:
        return error("DEPARTMENT_NOT_FOUND", "Department not found.", 404)
    problems: dict = {}
    hours = body.get("threshold_hours")
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 2160:
        problems["threshold_hours"] = "Must be 1 to 2160 hours."
    target = safe_text(body.get("target_label"), "target_label", 3, 160, problems)
    if problems:
        return validation_error(problems)
    row = db.session.scalar(select(EscalationRule).where(EscalationRule.department_id == department_id))
    if row is None:
        row = EscalationRule(department_id=department_id, threshold_hours=hours, target_label=target)
        db.session.add(row)
    else:
        row.threshold_hours, row.target_label = hours, target
    audit("AUTHORITY_ESCALATION_RULE_SET", "authority_department", None,
          {"department_id": department_id, "threshold_hours": hours})
    db.session.commit()
    return no_store({"escalation_rule": _escalation_json(department_id)})


# --------------------------------------------------------------- simulated officials

@admin_bp.post("/api/authority/admin/officers")
@coordinator
def assign_officer():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"email", "department_id", "title"})
    if failure:
        return failure
    problems: dict = {}
    email = body.get("email")
    if not isinstance(email, str) or "@" not in email or len(email) > 254:
        problems["email"] = "Enter the account's email address."
    department_id = body.get("department_id")
    department = db.session.get(Department, department_id) \
        if isinstance(department_id, int) and not isinstance(department_id, bool) else None
    if department is None or not department.is_active:
        problems["department_id"] = "Choose an active department."
    title = safe_text(body.get("title", "Demo official"), "title", 3, 120, problems)
    if problems:
        return validation_error(problems)
    user = db.session.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if user is None or user.account_status != AccountStatus.ACTIVE or user.email_verified_at is None:
        return error("USER_NOT_ELIGIBLE", "Only an active, email-verified account can act as a simulated official.",
                     409)
    if user.id == current_user.id:
        return error("SELF_ASSIGNMENT", "Coordinators cannot make themselves department officials.", 409)
    current = db.session.scalar(select(AuthorityOfficer).where(
        AuthorityOfficer.user_id == user.id, AuthorityOfficer.revoked_at.is_(None)))
    if current is not None:
        return error("ALREADY_OFFICER", "This account already acts for a department. Revoke it first.", 409)
    row = AuthorityOfficer(user_id=user.id, department_id=department.id, title=title,
                           granted_by_user_id=current_user.id)
    db.session.add(row)
    db.session.flush()
    audit("AUTHORITY_OFFICER_ASSIGNED", "authority_officer", row.id,
          {"user_id": str(user.id), "department_id": department.id})
    db.session.commit()
    return no_store({"officer": {"id": str(row.id), "user_id": str(user.id), "department_id": department.id,
                                 "title": row.title, "display_name": user.display_name}}, 201)


@admin_bp.delete("/api/authority/admin/officers/<uuid:officer_id>")
@coordinator
def revoke_officer(officer_id):
    missing = schema_missing()
    if missing:
        return missing
    row = db.session.get(AuthorityOfficer, officer_id)
    if row is None or row.revoked_at is not None:
        return error("OFFICER_NOT_FOUND", "Active officer assignment not found.", 404)
    row.revoked_at = datetime.now(timezone.utc)
    audit("AUTHORITY_OFFICER_REVOKED", "authority_officer", row.id, {"user_id": str(row.user_id)})
    db.session.commit()
    return no_store({"revoked": True})


# --------------------------------------------------------------- periodic job

@admin_bp.post("/api/authority/admin/sweep")
@coordinator
def run_sweep():
    """Manual trigger of the periodic job (the same code runs from `flask authority-sweep`)."""
    missing = schema_missing()
    if missing:
        return missing
    report = sweep(trigger="MANUAL_SWEEP")
    audit("AUTHORITY_SWEEP", "authority_case", None, report)
    db.session.commit()
    return no_store({"report": report})


def register_cli(app):
    @app.cli.command("authority-sweep")
    def authority_sweep_command():
        """Escalate overdue cases and settle expired verification windows (safe to re-run)."""
        report = sweep(trigger="CLI_SWEEP")
        db.session.commit()
        click.echo("Authority sweep: " + ", ".join(f"{key}={value}" for key, value in report.items()))


# --------------------------------------------------------------- analytics

def _hours(start, end) -> float:
    return round((aware(end) - aware(start)).total_seconds() / 3600, 2)


def _summary(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "average_hours": None, "median_hours": None, "max_hours": None}
    return {"count": len(values), "average_hours": round(sum(values) / len(values), 2),
            "median_hours": round(statistics.median(values), 2), "max_hours": max(values)}


@admin_bp.get("/api/admin/analytics/civic")
@coordinator
def civic_analytics():
    missing = schema_missing()
    if missing:
        return missing
    now = datetime.now(timezone.utc)
    cases = db.session.scalars(select(AuthorityCase)).all()
    events_by_case: dict = {}
    for row in db.session.scalars(select(CaseEvent).order_by(CaseEvent.case_id, CaseEvent.sequence)):
        events_by_case.setdefault(row.case_id, []).append(row)
    departments = {row.id: row for row in db.session.scalars(select(Department))}

    by_status = {item.value: 0 for item in CaseStatus}
    by_department: dict = {}
    to_ack, to_resolve, to_close = [], [], []
    mismatches = []
    overdue = 0
    for case in cases:
        by_status[case.status.value] += 1
        dept = by_department.setdefault(case.department_id, {
            "department_id": case.department_id,
            "name": departments[case.department_id].name if case.department_id in departments else "",
            "total": 0, "open": 0, "resolved": 0, "closed": 0, "overdue": 0})
        dept["total"] += 1
        if case.status in OPEN_STATUSES:
            dept["open"] += 1
        elif case.status == C.RESOLVED:
            dept["resolved"] += 1
        else:
            dept["closed"] += 1
        if is_overdue(case, now):
            dept["overdue"] += 1
            overdue += 1
        events = events_by_case.get(case.id, [])
        first = {}
        for row in events:
            first.setdefault(row.action, row.created_at)
        if "ACKNOWLEDGED" in first:
            to_ack.append(_hours(case.created_at, first["ACKNOWLEDGED"]))
        if "RESOLVED" in first:
            to_resolve.append(_hours(case.created_at, first["RESOLVED"]))
        if case.closed_at:
            to_close.append(_hours(case.created_at, case.closed_at))
        last = events[-1] if events else None
        problems = []
        if last is None or last.to_status != case.status.value:
            problems.append("Current status differs from the last history event.")
        if len(events) != case.event_count or [row.sequence for row in events] != list(range(1, len(events) + 1)):
            problems.append("History sequence has gaps.")
        if case.status == C.CLOSED and (case.closed_at is None or case.closure_basis is None):
            problems.append("Closed without a closing time or basis.")
        if case.status == C.RESOLVED and case.resolved_at is None:
            problems.append("Resolved without a resolution time.")
        if events and aware(events[0].created_at) > aware(case.updated_at):
            problems.append("Timestamps are out of order.")
        if problems:
            mismatches.append({"case_id": str(case.id), "reference": case.reference, "problems": problems})

    escalations = db.session.scalars(select(EscalationEvent)).all()
    verdicts = dict(db.session.execute(select(ResolutionVerification.verdict, func.count())
                                       .group_by(ResolutionVerification.verdict)).all())
    closure = {item.value: 0 for item in ClosureBasis}
    for case in cases:
        if case.closure_basis:
            closure[case.closure_basis.value] += 1
    pending_intake = db.session.scalar(select(func.count()).select_from(IssueHandoff).where(
        IssueHandoff.routing_status == RoutingStatus.PENDING_INTAKE,
        IssueHandoff.canonical_issue_id.not_in(select(AuthorityCase.civic_issue_id)))) or 0
    recent = db.session.scalars(select(CaseEvent).order_by(CaseEvent.created_at.desc(), CaseEvent.sequence.desc())
                                .limit(50)).all()
    names = display_names(row.actor_user_id for row in recent)
    references = {case.id: case.reference for case in cases}
    last_snapshot = db.session.scalar(select(CaseMetricSnapshot).order_by(CaseMetricSnapshot.created_at.desc()))
    return no_store({
        "generated_at": now.isoformat(),
        "simulation_notice": SIMULATION_NOTICE,
        "totals": {"cases": len(cases), "open": sum(by_status[item.value] for item in OPEN_STATUSES),
                   "overdue": overdue, "pending_intake": pending_intake,
                   "transfers": db.session.scalar(select(func.count()).select_from(CaseTransfer)) or 0,
                   "reopens": sum(case.reopen_count for case in cases),
                   "reopened_cases": sum(1 for case in cases if case.reopen_count)},
        "by_status": by_status,
        "by_department": sorted(by_department.values(), key=lambda item: item["name"]),
        "durations": {"intake_to_acknowledge": _summary(to_ack), "intake_to_first_resolution": _summary(to_resolve),
                      "intake_to_close": _summary(to_close)},
        "escalations": {
            "total": len(escalations),
            "auto_overdue": sum(1 for row in escalations if row.kind == EscalationKind.AUTO_OVERDUE),
            "manual": sum(1 for row in escalations if row.kind == EscalationKind.MANUAL),
            "open": sum(1 for row in escalations if row.outcome == EscalationOutcome.OPEN),
            "responded": sum(1 for row in escalations if row.outcome == EscalationOutcome.RESPONDED),
        },
        "outcomes": {"closed_by_basis": closure,
                     "verifications": {"confirmed": verdicts.get(Verdict.CONFIRMED, 0),
                                       "disputed": verdicts.get(Verdict.DISPUTED, 0)}},
        "reconciliation": {"cases_checked": len(cases), "consistent": not mismatches,
                           "status_sum_matches_total": sum(by_status.values()) == len(cases),
                           "mismatches": mismatches},
        "last_snapshot": {"trigger": last_snapshot.trigger, "at": iso(last_snapshot.created_at),
                          "counts": last_snapshot.counts} if last_snapshot else None,
        "audit": [{"case_id": str(row.case_id), "reference": references.get(row.case_id, ""),
                   "sequence": row.sequence, "action": row.action, "from_status": row.from_status,
                   "to_status": row.to_status, "actor_kind": row.actor_kind.value,
                   "actor_display_name": names.get(row.actor_user_id, ""), "reason": row.reason,
                   "at": iso(row.created_at)} for row in recent],
    })
