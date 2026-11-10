"""Case intake and the simulated-official / coordinator case workflow."""
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Blueprint, current_app, request, send_file
from flask_login import current_user
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from app.extensions import db
from app.modules.civic.handoff import acknowledge_handoff
from app.modules.civic.models import CivicIssue, IssueEvidence, IssueHandoff, IssueState, RoutingStatus
from app.modules.identity.auth.routes import error
from app.modules.identity.documents import storage

from .common import (
    SIMULATION_NOTICE, audit, coordinator, current_officer, is_coordinator, iso, json_body, no_store,
    not_assigned, official, pagination, safe_text, schema_missing, staff, validation_error,
)
from .models import (
    ActorKind, AuthorityCase, CaseClarification, CaseStatus, CaseTransfer, ClosureBasis,
    Department, EscalationKind, EscalationOutcome, EvidenceType, ResolutionEvidence,
)
from .service import (
    ESCALATABLE, MAX_EVIDENCE_PER_ROUND, OPEN_STATUSES, TRANSFERABLE, WORKABLE, InvalidCaseTransition,
    case_json, close_case, close_open_escalations, covers, escalate, evidence_json, fetch_case_locked,
    notify, notify_department, notify_residents, pick_department, record, reopen_case, setting,
    sla_hours, tally,
)

cases_bp = Blueprint("authority_cases", __name__)
C = CaseStatus
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def invalid_state(exc: InvalidCaseTransition):
    db.session.rollback()
    return error("INVALID_STATE", f"This case cannot move from {exc.from_status.value} to {exc.to_status.value}.",
                 409)


def _actor() -> tuple[ActorKind, object]:
    """OFFICIAL when the user is an officer of the case department, otherwise COORDINATOR."""
    return (ActorKind.OFFICIAL if current_officer() else ActorKind.COORDINATOR), current_user.id


def _load_for_official(case_id):
    """Lock the case and check that the signed-in official belongs to its department."""
    case = fetch_case_locked(case_id)
    if case is None:
        db.session.rollback()
        return None, error("CASE_NOT_FOUND", "Case not found.", 404)
    officer = current_officer()
    if officer is None or officer.department_id != case.department_id:
        db.session.rollback()
        return None, not_assigned()
    return case, None


def _load_for_staff(case_id, *, lock=True):
    """Coordinator: any case. Official: only cases of their department."""
    case = fetch_case_locked(case_id) if lock else db.session.get(AuthorityCase, case_id)
    if case is None:
        db.session.rollback()
        return None, error("CASE_NOT_FOUND", "Case not found.", 404)
    if is_coordinator():
        return case, None
    officer = current_officer()
    if officer is None or officer.department_id != case.department_id:
        db.session.rollback()
        return None, not_assigned()
    return case, None


def _reference() -> str:
    return "AC-" + uuid.uuid4().hex[:8].upper()


def _respond(case: AuthorityCase, status: int = 200):
    return no_store({"case": case_json(case, detail=True), "simulation_notice": SIMULATION_NOTICE}, status)


# --------------------------------------------------------------- intake

@cases_bp.get("/api/authority/intake-queue")
@coordinator
def intake_queue():
    """Module 5 handoffs that do not yet have an authority case."""
    missing = schema_missing()
    if missing:
        return missing
    taken = select(AuthorityCase.civic_issue_id)
    rows = db.session.scalars(select(IssueHandoff).where(
        IssueHandoff.routing_status == RoutingStatus.PENDING_INTAKE,
        IssueHandoff.canonical_issue_id.not_in(taken)).order_by(IssueHandoff.routed_at)).all()
    output = []
    for row in rows:
        issue = db.session.get(CivicIssue, row.canonical_issue_id)
        suggestion = pick_department(issue.locality_id, issue.category.value) if issue else None
        output.append({
            "canonical_issue_id": str(row.canonical_issue_id), "routed_at": iso(row.routed_at),
            "title": row.payload.get("title", ""), "category": row.payload.get("category", ""),
            "severity": row.payload.get("severity", ""), "community_support": row.payload.get("community_support", 0),
            "suggested_department": {"id": suggestion.id, "name": suggestion.name} if suggestion else None,
        })
    return no_store({"handoffs": output, "simulation_notice": SIMULATION_NOTICE})


@cases_bp.post("/api/authority/cases/intake")
@coordinator
def intake():
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"canonical_issue_id", "department_id", "note"})
    if failure:
        return failure
    problems: dict = {}
    try:
        issue_id = uuid.UUID(str(body.get("canonical_issue_id")))
    except ValueError:
        issue_id = None
        problems["canonical_issue_id"] = "Send the canonical civic issue id."
    department_id = body.get("department_id")
    if department_id is not None and (isinstance(department_id, bool) or not isinstance(department_id, int)):
        problems["department_id"] = "Must be a department id."
    note = safe_text(body.get("note", ""), "note", 0, 500, problems, required=False) or ""
    if problems:
        return validation_error(problems)

    issue = db.session.scalar(select(CivicIssue).where(CivicIssue.id == issue_id).with_for_update())
    handoff = db.session.scalar(select(IssueHandoff).where(IssueHandoff.canonical_issue_id == issue_id))
    if issue is None or handoff is None:
        db.session.rollback()
        return error("HANDOFF_NOT_FOUND", "Module 5 has not handed this issue off for routing.", 404)
    existing = db.session.scalar(select(AuthorityCase).where(AuthorityCase.civic_issue_id == issue.id))
    if existing is not None:
        db.session.rollback()
        return no_store({"case": case_json(existing, detail=True), "created": False,
                         "simulation_notice": SIMULATION_NOTICE})
    if issue.state != IssueState.READY_FOR_ROUTING:
        db.session.rollback()
        return error("ISSUE_NOT_READY", "Only issues Module 5 marked ready for routing can be taken in.", 409)

    category, locality_id = issue.category.value, issue.locality_id
    if department_id is not None:
        department = db.session.get(Department, department_id)
        if department is None or not department.is_active:
            db.session.rollback()
            return validation_error({"department_id": "Choose an active department."})
        if not covers(department, locality_id, category):
            db.session.rollback()
            return error("OUT_OF_JURISDICTION", f"{department.name} does not cover {category} in this locality.", 409)
    else:
        department = pick_department(locality_id, category)
        if department is None:
            db.session.rollback()
            return error("NO_DEPARTMENT", "No simulated department covers this category. Add a jurisdiction rule.",
                         409)

    now = datetime.now(timezone.utc)
    case = AuthorityCase(
        id=uuid.uuid4(), reference=_reference(), civic_issue_id=issue.id, department_id=department.id,
        status=C.ROUTED, created_by_user_id=current_user.id, due_at=now + timedelta(hours=sla_hours(department.id)),
        round=1, reopen_count=0, event_count=0, created_at=now, updated_at=now,
    )
    db.session.add(case)
    record(case, action="INTAKE", to_status=C.ROUTED, actor_id=current_user.id, actor_kind=ActorKind.COORDINATOR,
           reason=note or "Validated civic issue taken in from Module 5.", check=False, initial=True, at=now,
           public_summary=f"Case opened and sent to {department.name} (simulated).",
           details={"handoff_id": str(handoff.id), "department_id": department.id,
                    "manual_department": department_id is not None})
    try:
        acknowledge_handoff(issue.id, case.reference)
    except LookupError:
        db.session.rollback()
        return error("HANDOFF_NOT_FOUND", "Module 5 has not handed this issue off for routing.", 404)
    except ValueError:
        db.session.rollback()
        return error("CASE_ALREADY_LINKED", "Module 5 already links this issue to a different case id.", 409)
    notify_department(case, "CASE_ASSIGNED", f"New case {case.reference}: {handoff.payload.get('title', '')}")
    notify_residents(case, "CASE_ASSIGNED", f"Your civic issue is now case {case.reference} with {department.name}.")
    audit("AUTHORITY_CASE_CREATED", "authority_case", case.id,
          {"civic_issue_id": str(issue.id), "department_id": department.id, "reference": case.reference})
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = db.session.scalar(select(AuthorityCase).where(AuthorityCase.civic_issue_id == issue_id))
        if existing is None:
            raise
        return no_store({"case": case_json(existing, detail=True), "created": False,
                         "simulation_notice": SIMULATION_NOTICE})
    return no_store({"case": case_json(case, detail=True), "created": True, "simulation_notice": SIMULATION_NOTICE},
                    201)


# --------------------------------------------------------------- reading

@cases_bp.get("/api/authority/cases")
@staff
def list_cases():
    missing = schema_missing()
    if missing:
        return missing
    page = pagination()
    if page is None:
        return validation_error({"limit": "Use limit 1-100 and offset 0-100000."})
    limit, offset = page
    query = select(AuthorityCase)
    officer = current_officer()
    if not is_coordinator():
        query = query.where(AuthorityCase.department_id == officer.department_id)
    elif request.args.get("department_id"):
        try:
            query = query.where(AuthorityCase.department_id == int(request.args["department_id"]))
        except ValueError:
            return validation_error({"department_id": "Must be a number."})
    status = request.args.get("status")
    if status:
        try:
            query = query.where(AuthorityCase.status == CaseStatus(status))
        except ValueError:
            return validation_error({"status": "Unknown case status."})
    if request.args.get("overdue") == "true":
        query = query.where(AuthorityCase.status.in_(list(OPEN_STATUSES)),
                            AuthorityCase.due_at < datetime.now(timezone.utc))
    total = db.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.session.scalars(query.order_by(AuthorityCase.due_at, AuthorityCase.id).limit(limit).offset(offset)).all()
    return no_store({"cases": [case_json(row) for row in rows], "total": total, "limit": limit, "offset": offset,
                     "simulation_notice": SIMULATION_NOTICE})


@cases_bp.get("/api/authority/cases/<uuid:case_id>")
@staff
def get_case(case_id):
    missing = schema_missing()
    if missing:
        return missing
    case, failure = _load_for_staff(case_id, lock=False)
    if failure:
        return failure
    return _respond(case)


# --------------------------------------------------------------- official actions

@cases_bp.post("/api/authority/cases/<uuid:case_id>/acknowledge")
@official
def acknowledge(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"note"})
    if failure:
        return failure
    problems: dict = {}
    note = safe_text(body.get("note", ""), "note", 0, 500, problems, required=False) or ""
    if problems:
        return validation_error(problems)
    case, failure = _load_for_official(case_id)
    if failure:
        return failure
    department = db.session.get(Department, case.department_id)
    try:
        record(case, action="ACKNOWLEDGED", to_status=C.ACKNOWLEDGED, actor_id=current_user.id,
               actor_kind=ActorKind.OFFICIAL, reason=note or "Case accepted.",
               public_summary=f"{department.name} (simulated) accepted the case.")
    except InvalidCaseTransition as exc:
        return invalid_state(exc)
    case.owner_user_id = current_user.id
    notify_residents(case, "CASE_UPDATED", f"Case {case.reference} was accepted by {department.name} (simulated).")
    audit("AUTHORITY_CASE_ACKNOWLEDGED", "authority_case", case.id)
    db.session.commit()
    return _respond(case)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/transfer")
@staff
def transfer(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"to_department_id", "reason"})
    if failure:
        return failure
    problems: dict = {}
    target_id = body.get("to_department_id")
    if isinstance(target_id, bool) or not isinstance(target_id, int):
        problems["to_department_id"] = "Choose the department that should take this case."
    reason = safe_text(body.get("reason"), "reason", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    case, failure = _load_for_staff(case_id)
    if failure:
        return failure
    if case.status not in TRANSFERABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Only cases not yet in progress can be transferred.", 409)
    if target_id == case.department_id:
        db.session.rollback()
        return error("SAME_DEPARTMENT", "The case is already with this department.", 409)
    target = db.session.get(Department, target_id)
    if target is None or not target.is_active:
        db.session.rollback()
        return validation_error({"to_department_id": "Choose an active department."})
    issue = db.session.get(CivicIssue, case.civic_issue_id)
    if not covers(target, issue.locality_id, issue.category.value):
        db.session.rollback()
        return error("OUT_OF_JURISDICTION", f"{target.name} does not cover {issue.category.value} here.", 409)
    history = db.session.scalars(select(CaseTransfer).where(CaseTransfer.case_id == case.id)).all()
    if any(row.from_department_id == target_id for row in history):
        db.session.rollback()
        return error("TRANSFER_LOOP", "This department already passed the case on. Ask a coordinator to decide.", 409)
    if len(history) >= setting("AUTHORITY_MAX_TRANSFERS"):
        db.session.rollback()
        return error("TRANSFER_LIMIT", "This case has been transferred too many times. A coordinator must assign it.",
                     409)
    source = db.session.get(Department, case.department_id)
    kind, actor = _actor()
    db.session.add(CaseTransfer(case_id=case.id, from_department_id=source.id, to_department_id=target.id,
                                reason=reason, requested_by_user_id=actor))
    record(case, action="TRANSFERRED", to_status=C.ROUTED, actor_id=actor, actor_kind=kind, reason=reason,
           public_summary=f"Reassigned from {source.name} to {target.name} (simulated).",
           details={"from_department_id": source.id, "to_department_id": target.id})
    case.department_id = target.id
    case.owner_user_id = None
    notify_department(case, "CASE_ASSIGNED", f"Case {case.reference} was transferred to {target.name}: {reason}")
    notify_residents(case, "CASE_UPDATED", f"Case {case.reference} was reassigned to {target.name} (simulated).")
    audit("AUTHORITY_CASE_TRANSFERRED", "authority_case", case.id,
          {"from_department_id": source.id, "to_department_id": target.id})
    db.session.commit()
    return _respond(case)


def _parse_due(value, problems: dict):
    if value is None:
        return None
    try:
        due = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        problems["revised_due_at"] = "Use an ISO 8601 date-time."
        return None
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if not now < due <= now + timedelta(days=90):
        problems["revised_due_at"] = "Must be in the future and within 90 days."
        return None
    return due


@cases_bp.post("/api/authority/cases/<uuid:case_id>/progress")
@official
def progress(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"message", "public_summary", "revised_due_at"})
    if failure:
        return failure
    problems: dict = {}
    message = safe_text(body.get("message"), "message", 5, 1000, problems)
    summary = safe_text(body.get("public_summary", ""), "public_summary", 0, 300, problems, required=False) or ""
    due = _parse_due(body.get("revised_due_at"), problems)
    if problems:
        return validation_error(problems)
    case, failure = _load_for_official(case_id)
    if failure:
        return failure
    if case.status not in WORKABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Progress can be posted only on accepted, in-progress or reopened cases.", 409)
    now = datetime.now(timezone.utc)
    details = {}
    if due is not None:
        details = {"previous_due_at": iso(case.due_at), "revised_due_at": iso(due)}
        case.due_at = due
    record(case, action="PROGRESS", to_status=C.IN_PROGRESS, actor_id=current_user.id, actor_kind=ActorKind.OFFICIAL,
           reason=message, public_summary=summary or message, details=details or None, at=now)
    close_open_escalations(case, EscalationOutcome.RESPONDED, now)
    notify_residents(case, "CASE_UPDATED", f"Case {case.reference}: {summary or message}"[:300])
    audit("AUTHORITY_CASE_PROGRESS", "authority_case", case.id, details or None)
    db.session.commit()
    return _respond(case)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/evidence")
@official
def add_evidence(case_id):
    missing = schema_missing()
    if missing:
        return missing
    if request.mimetype != "multipart/form-data":
        return error("UNSUPPORTED_MEDIA_TYPE", "Use multipart/form-data.", 415)
    problems: dict = {}
    caption = safe_text(request.form.get("caption", ""), "caption", 0, 200, problems, required=False) or ""
    try:
        evidence_type = EvidenceType(request.form.get("evidence_type", EvidenceType.RESOLUTION.value))
    except ValueError:
        problems["evidence_type"] = "Choose PROGRESS or RESOLUTION."
        evidence_type = None
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        problems["file"] = "Choose a photo."
    if problems:
        return validation_error(problems)
    if Path(incoming.filename).suffix.lower() not in IMAGE_EXTENSIONS:
        return error("INVALID_DOCUMENT", "Only JPG and PNG photos are allowed.", 400)
    case, failure = _load_for_official(case_id)
    if failure:
        return failure
    if case.status not in WORKABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Evidence can be added only while the department is working on the case.", 409)
    count = db.session.scalar(select(func.count()).select_from(ResolutionEvidence).where(
        ResolutionEvidence.case_id == case.id, ResolutionEvidence.round == case.round)) or 0
    if count >= MAX_EVIDENCE_PER_ROUND:
        db.session.rollback()
        return error("EVIDENCE_LIMIT_REACHED", f"At most {MAX_EVIDENCE_PER_ROUND} photos per round.", 409)
    blob = incoming.stream.read(storage.MAX_FILE_BYTES + 1)
    try:
        mime = storage.validate_document(incoming.filename, blob)
    except (ValueError, RuntimeError) as exc:
        db.session.rollback()
        return error("INVALID_DOCUMENT", str(exc), 400)
    if mime not in ("image/png", "image/jpeg"):
        db.session.rollback()
        return error("INVALID_DOCUMENT", "Only JPG and PNG photos are allowed.", 400)
    key = None
    try:
        key, checksum = storage.write_private(current_app.config, blob, mime)
        row = ResolutionEvidence(
            case_id=case.id, round=case.round, evidence_type=evidence_type, caption=caption, storage_key=key,
            sha256_checksum=checksum, mime_type=mime, file_size_bytes=len(blob),
            original_filename=(secure_filename(incoming.filename) or "photo")[:255],
            submitted_by_user_id=current_user.id,
        )
        db.session.add(row)
        db.session.flush()
        record(case, action="EVIDENCE_ADDED", to_status=case.status, actor_id=current_user.id, check=False,
               actor_kind=ActorKind.OFFICIAL, reason=caption,
               public_summary=f"Department added a {evidence_type.value.lower()} photo.",
               details={"evidence_id": str(row.id), "evidence_type": evidence_type.value, "round": case.round})
        audit("AUTHORITY_EVIDENCE_ADDED", "authority_case", case.id, {"evidence_id": str(row.id)})
        db.session.commit()
    except Exception:
        db.session.rollback()
        if key:
            storage.private_path(current_app.config, key).unlink(missing_ok=True)
        current_app.logger.exception("Authority evidence upload failed")
        return error("UPLOAD_FAILED", "Unable to save the photo.", 503)
    return no_store({"evidence": evidence_json(row)}, 201)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/resolve")
@official
def resolve(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"summary"})
    if failure:
        return failure
    problems: dict = {}
    summary = safe_text(body.get("summary"), "summary", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    case, failure = _load_for_official(case_id)
    if failure:
        return failure
    if case.status != C.IN_PROGRESS:
        db.session.rollback()
        return error("INVALID_STATE", "Only an in-progress case can be marked resolved.", 409)
    department = db.session.get(Department, case.department_id)
    proof = db.session.scalar(select(func.count()).select_from(ResolutionEvidence).where(
        ResolutionEvidence.case_id == case.id, ResolutionEvidence.round == case.round,
        ResolutionEvidence.evidence_type == EvidenceType.RESOLUTION)) or 0
    if department.requires_resolution_proof and proof < 1:
        db.session.rollback()
        return error("PROOF_REQUIRED", "Upload at least one RESOLUTION photo before marking the case resolved.", 409)
    now = datetime.now(timezone.utc)
    record(case, action="RESOLVED", to_status=C.RESOLVED, actor_id=current_user.id, actor_kind=ActorKind.OFFICIAL,
           reason=summary, public_summary=f"Department reports the problem fixed: {summary}"[:300], at=now,
           details={"round": case.round, "proof_count": proof})
    case.resolved_at = now
    case.verification_closes_at = now + timedelta(hours=setting("AUTHORITY_VERIFY_WINDOW_HOURS"))
    close_open_escalations(case, EscalationOutcome.CLOSED, now)
    notify_residents(case, "VERIFICATION_REQUESTED",
                     f"Case {case.reference} is marked fixed. Please confirm whether it is solved.")
    audit("AUTHORITY_CASE_RESOLVED", "authority_case", case.id, {"round": case.round})
    db.session.commit()
    return _respond(case)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/request-clarification")
@official
def request_clarification(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"question"})
    if failure:
        return failure
    problems: dict = {}
    question = safe_text(body.get("question"), "question", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    case, failure = _load_for_official(case_id)
    if failure:
        return failure
    if case.status not in WORKABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Clarification can be requested only on accepted or active cases.", 409)
    resume = C.IN_PROGRESS if case.status == C.REOPENED else case.status
    row = CaseClarification(case_id=case.id, asked_by_user_id=current_user.id, question=question,
                            resume_status=resume.value)
    db.session.add(row)
    record(case, action="CLARIFICATION_REQUESTED", to_status=C.CLARIFICATION_REQUESTED, actor_id=current_user.id,
           actor_kind=ActorKind.OFFICIAL, reason=question,
           public_summary="The department asked the reporter for more details.")
    issue = db.session.get(CivicIssue, case.civic_issue_id)
    notify(case, [issue.creator_id], "CLARIFICATION_REQUESTED",
           f"Case {case.reference}: the department asks: {question}"[:300])
    audit("AUTHORITY_CLARIFICATION_REQUESTED", "authority_case", case.id)
    db.session.commit()
    return _respond(case)


# --------------------------------------------------------------- coordinator actions

@cases_bp.post("/api/authority/cases/<uuid:case_id>/escalate")
@coordinator
def manual_escalate(case_id):
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"reason", "acknowledge_simulated"})
    if failure:
        return failure
    problems: dict = {}
    reason = safe_text(body.get("reason"), "reason", 10, 1000, problems)
    if body.get("acknowledge_simulated") is not True:
        problems["acknowledge_simulated"] = (
            "Confirm that this escalation is simulated and is not sent to any real government body.")
    if problems:
        return validation_error(problems)
    case = fetch_case_locked(case_id)
    if case is None:
        db.session.rollback()
        return error("CASE_NOT_FOUND", "Case not found.", 404)
    if case.status not in ESCALATABLE:
        db.session.rollback()
        return error("INVALID_STATE", "Only open cases can be escalated.", 409)
    row = escalate(case, EscalationKind.MANUAL, actor_id=current_user.id, at=datetime.now(timezone.utc),
                   reason=reason)
    if row is None:
        db.session.rollback()
        return error("ALREADY_ESCALATED", "This case was already escalated manually for the current deadline.", 409)
    audit("AUTHORITY_CASE_ESCALATED", "authority_case", case.id, {"kind": "MANUAL"})
    db.session.commit()
    return _respond(case)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/reopen")
@coordinator
def manual_reopen(case_id):
    """Controlled reopen: a coordinator reopens a resolved or closed case with a reason."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"reason"})
    if failure:
        return failure
    problems: dict = {}
    reason = safe_text(body.get("reason"), "reason", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    case = fetch_case_locked(case_id)
    if case is None:
        db.session.rollback()
        return error("CASE_NOT_FOUND", "Case not found.", 404)
    if case.status != C.RESOLVED:
        db.session.rollback()
        return error("INVALID_STATE", "Only a case marked resolved can be reopened.", 409)
    reopen_case(case, actor_id=current_user.id, actor_kind=ActorKind.COORDINATOR, reason=reason,
                at=datetime.now(timezone.utc),
                summary="A coordinator reopened the case after reviewing residents' feedback.")
    audit("AUTHORITY_CASE_REOPENED", "authority_case", case.id, {"by": "COORDINATOR"})
    db.session.commit()
    return _respond(case)


@cases_bp.post("/api/authority/cases/<uuid:case_id>/close")
@coordinator
def coordinator_close(case_id):
    """Only after the verification window ended with no votes at all."""
    missing = schema_missing()
    if missing:
        return missing
    body, failure = json_body({"reason"})
    if failure:
        return failure
    problems: dict = {}
    reason = safe_text(body.get("reason"), "reason", 10, 1000, problems)
    if problems:
        return validation_error(problems)
    case = fetch_case_locked(case_id)
    if case is None:
        db.session.rollback()
        return error("CASE_NOT_FOUND", "Case not found.", 404)
    now = datetime.now(timezone.utc)
    window_open = case.verification_closes_at is not None and \
        case.verification_closes_at.replace(tzinfo=case.verification_closes_at.tzinfo or timezone.utc) > now
    counts = tally(case)
    if case.status != C.RESOLVED or window_open or counts["confirmed"] or counts["disputed"]:
        db.session.rollback()
        return error("CLOSE_NOT_ALLOWED",
                     "A coordinator can close only a resolved case whose verification window ended with no votes.",
                     409)
    close_case(case, ClosureBasis.COORDINATOR_AFTER_WINDOW, actor_id=current_user.id,
               actor_kind=ActorKind.COORDINATOR, reason=reason, at=now)
    audit("AUTHORITY_CASE_CLOSED", "authority_case", case.id, {"basis": "COORDINATOR_AFTER_WINDOW"})
    db.session.commit()
    return _respond(case)


# --------------------------------------------------------------- files

def _send_private(key: str, filename: str):
    try:
        path = storage.private_path(current_app.config, key)
    except ValueError:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    if not path.is_file():
        return error("EVIDENCE_NOT_FOUND", "Photo is unavailable.", 404)
    response = send_file(path, mimetype="application/octet-stream", as_attachment=True, download_name=filename,
                         max_age=0)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@cases_bp.get("/api/authority/cases/<uuid:case_id>/issue-evidence/<uuid:evidence_id>/file")
@staff
def issue_evidence_file(case_id, evidence_id):
    """Reporter photos that Module 5 included in the routing payload, for the assigned department."""
    missing = schema_missing()
    if missing:
        return missing
    case, failure = _load_for_staff(case_id, lock=False)
    if failure:
        return failure
    handoff = db.session.scalar(select(IssueHandoff).where(IssueHandoff.canonical_issue_id == case.civic_issue_id))
    listed = {item.get("evidence_id") for item in (handoff.payload.get("evidence", []) if handoff else [])}
    row = db.session.get(IssueEvidence, evidence_id)
    if row is None or str(evidence_id) not in listed or row.issue_id != case.civic_issue_id:
        return error("EVIDENCE_NOT_FOUND", "Photo not found.", 404)
    return _send_private(row.storage_key, row.original_filename)
