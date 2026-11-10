"""Repeat-safe Module 6 demo seed. Run from backend/: python -m scripts.seed_authority_demo [--with-sample-case]

Requires, in order: the Module 1 seed (scripts.seed_green_valley), the Module 5 seed
(scripts.seed_civic_demo) and the Module 6 migration. Set KNOWALL_SEED_OFFICER_PASSWORD
(12+ characters) in the untracked backend/.env.

Creates SIMULATED departments, jurisdiction rules, demo SLA rules and one demo official per
department. Everything is fictional and labelled "(Demo)". No real government body is involved.

--with-sample-case additionally routes Priya's seeded streetlight issue through Module 5
(adds Maya's support and a generated placeholder photo) and opens an authority case for it,
accepted by the lighting cell, so the dashboards have data. Existing rows are never changed.
"""
import io
import os
import sys
from datetime import datetime, timedelta, timezone

from PIL import Image
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.authority.models import (
    ActorKind, AuthorityCase, AuthorityOfficer, CaseStatus, Department, EscalationRule, JurisdictionRule,
)
from app.modules.authority.service import record, sla_hours
from app.modules.civic.handoff import acknowledge_handoff, build_payload
from app.modules.civic.models import (
    ActorRole, CivicIssue, CivicLocality, EvidenceVisibility, IssueEvidence, IssueHandoff, IssueState, IssueSupport,
)
from app.modules.civic.service import readiness, supporter_sets, transition
from app.modules.identity.documents import storage
from app.modules.identity.models import AccountStatus, User

SUFFIX = "@greenvalley.test"

# code, name, description, categories, priority, SLA hours, escalation target label
DEPARTMENTS = (
    ("ROADS", "Roads & Footpaths Division (Demo)", "Simulated division for road surface, footpath and traffic issues.",
     ["ROAD_DAMAGE", "FOOTPATH", "TRAFFIC"], 10, 72, "Ward Office (Demo)"),
    ("LIGHTS", "Street Lighting Cell (Demo)", "Simulated cell for public street lights.",
     ["STREETLIGHT"], 10, 48, "Ward Office (Demo)"),
    ("SANITATION", "Sanitation & Drainage Unit (Demo)", "Simulated unit for garbage collection and drains.",
     ["GARBAGE", "DRAINAGE"], 10, 72, "Ward Office (Demo)"),
    ("WATER", "Water Supply Board (Demo)", "Simulated board for public water supply lines.",
     ["WATER_SUPPLY"], 10, 48, "Ward Office (Demo)"),
    ("WARD", "Ward Office (Demo)", "Simulated ward office. Takes general issues and receives escalations.",
     ["PUBLIC_SPACE", "OTHER", "ROAD_DAMAGE", "STREETLIGHT"], 200, 120, "Society coordinator"),
)
OFFICERS = (  # email local part, display name, department code, title
    ("officer.roads", "Demo Officer - Roads", "ROADS", "Assistant Engineer (Demo)"),
    ("officer.lights", "Demo Officer - Lighting", "LIGHTS", "Lighting Supervisor (Demo)"),
    ("officer.sanitation", "Demo Officer - Sanitation", "SANITATION", "Sanitation Inspector (Demo)"),
    ("officer.water", "Demo Officer - Water", "WATER", "Junior Engineer (Demo)"),
    ("officer.ward", "Demo Officer - Ward", "WARD", "Ward Officer (Demo)"),
)


def _password() -> str:
    value = os.getenv("KNOWALL_SEED_OFFICER_PASSWORD", "")
    if len(value) < 12:
        raise RuntimeError("Set KNOWALL_SEED_OFFICER_PASSWORD (12+ characters) in the untracked backend/.env.")
    return value


def _user(name: str) -> User:
    user = db.session.scalar(select(User).where(User.email == name + SUFFIX))
    if user is None:
        raise RuntimeError(f"Demo user {name}{SUFFIX} is missing. Run scripts.seed_green_valley first.")
    return user


def _locality() -> CivicLocality:
    loc = db.session.scalar(select(CivicLocality).where(CivicLocality.society_id == 1, CivicLocality.is_active.is_(True)))
    if loc is None:
        raise RuntimeError("Civic coverage area is missing. Run scripts.seed_civic_demo first.")
    return loc


def seed_departments() -> dict:
    loc = _locality()
    created = {}
    for code, name, description, categories, priority, hours, target in DEPARTMENTS:
        row = db.session.scalar(select(Department).where(Department.society_id == 1, Department.code == code))
        if row is None:
            row = Department(society_id=1, code=code, name=name, description=description,
                             contact_label=f"{name} - fictional routing desk", is_demo=True, is_active=True)
            db.session.add(row)
            db.session.flush()
            for category in categories:
                db.session.add(JurisdictionRule(department_id=row.id, locality_id=loc.id, category=category,
                                                priority=priority))
            db.session.add(EscalationRule(department_id=row.id, threshold_hours=hours, target_label=target))
        created[code] = row
    ward = created["WARD"]
    for code, row in created.items():
        if code != "WARD" and row.escalation_department_id is None:
            row.escalation_department_id = ward.id
    return created


def seed_officers(departments: dict) -> int:
    password = _password()
    added = 0
    for local, display, code, title in OFFICERS:
        email = local + SUFFIX
        user = db.session.scalar(select(User).where(User.email == email))
        if user is None:
            # Verification flag is ONLY for fictional demo identities.
            user = User(email=email, display_name=display, password_hash=generate_password_hash(password),
                        email_verified_at=datetime.now(timezone.utc), account_status=AccountStatus.ACTIVE)
            db.session.add(user)
            db.session.flush()
        active = db.session.scalar(select(AuthorityOfficer).where(
            AuthorityOfficer.user_id == user.id, AuthorityOfficer.revoked_at.is_(None)))
        if active is None:
            db.session.add(AuthorityOfficer(user_id=user.id, department_id=departments[code].id, title=title))
            added += 1
    return added


def _placeholder_photo() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 200), (40, 40, 60)).save(buffer, "PNG")
    return buffer.getvalue()


def seed_sample_case(app) -> str:
    admin, priya, maya = _user("admin"), _user("priya"), _user("maya")
    issue = db.session.scalar(select(CivicIssue).where(CivicIssue.creator_id == priya.id,
                                                       CivicIssue.title == "Streetlight not working on the park lane"))
    if issue is None:
        raise RuntimeError("Priya's streetlight issue is missing. Run scripts.seed_civic_demo first.")
    existing = db.session.scalar(select(AuthorityCase).where(AuthorityCase.civic_issue_id == issue.id))
    if existing:
        return f"already present ({existing.reference})"
    if not db.session.scalar(select(IssueSupport.id).where(IssueSupport.issue_id == issue.id,
                                                           IssueSupport.user_id == maya.id)):
        db.session.add(IssueSupport(issue_id=issue.id, user_id=maya.id))
    if not db.session.scalar(select(IssueEvidence.id).where(IssueEvidence.issue_id == issue.id)):
        blob = _placeholder_photo()
        key, checksum = storage.write_private(app.config, blob, "image/png")
        db.session.add(IssueEvidence(
            issue_id=issue.id, uploaded_by_user_id=priya.id, visibility=EvidenceVisibility.RESIDENTS,
            caption="Generated placeholder photo (demo seed)", storage_key=key, sha256_checksum=checksum,
            mime_type="image/png", file_size_bytes=len(blob), original_filename="demo-streetlight.png"))
    db.session.flush()
    supporters = len(supporter_sets([issue.id]).get(issue.id, set()))
    evidence = db.session.scalars(select(IssueEvidence).where(IssueEvidence.issue_id == issue.id)).all()
    handoff = db.session.scalar(select(IssueHandoff).where(IssueHandoff.canonical_issue_id == issue.id))
    if handoff is None:
        unmet = readiness(issue, supporters, len(evidence))
        if unmet:
            raise RuntimeError("Streetlight issue is not ready for routing: " + "; ".join(unmet))
        transition(issue, IssueState.READY_FOR_ROUTING, actor_id=admin.id, role=ActorRole.MODERATOR,
                   reason="Readiness criteria met; handed off for routing (demo seed).")
        handoff = IssueHandoff(canonical_issue_id=issue.id, routed_by_user_id=admin.id,
                               payload=build_payload(issue, supporters, evidence))
        db.session.add(handoff)
        db.session.flush()
    lights = db.session.scalar(select(Department).where(Department.code == "LIGHTS"))
    officer = _user("officer.lights")
    now = datetime.now(timezone.utc)
    case = AuthorityCase(reference="AC-DEMO0001", civic_issue_id=issue.id, department_id=lights.id,
                         status=CaseStatus.ROUTED, created_by_user_id=admin.id,
                         due_at=now + timedelta(hours=sla_hours(lights.id)), round=1, reopen_count=0,
                         event_count=0, created_at=now, updated_at=now)
    db.session.add(case)
    db.session.flush()
    record(case, action="INTAKE", to_status=CaseStatus.ROUTED, actor_id=admin.id, actor_kind=ActorKind.COORDINATOR,
           reason="Demo seed intake.", public_summary=f"Case opened and sent to {lights.name} (simulated).",
           check=False, initial=True, at=now)
    record(case, action="ACKNOWLEDGED", to_status=CaseStatus.ACKNOWLEDGED, actor_id=officer.id,
           actor_kind=ActorKind.OFFICIAL, reason="Demo seed acceptance.",
           public_summary=f"{lights.name} (simulated) accepted the case.", at=now)
    case.owner_user_id = officer.id
    acknowledge_handoff(issue.id, case.reference)
    return f"created ({case.reference})"


def main() -> None:
    app = create_app()
    with app.app_context():
        departments = seed_departments()
        officers = seed_officers(departments)
        sample = seed_sample_case(app) if "--with-sample-case" in sys.argv else "skipped"
        db.session.commit()
    print("KNOWALL Module 6 authority demo seed completed (or already present). All departments are SIMULATED.")
    print(f"Departments: {len(departments)} | new officer assignments: {officers} | sample case: {sample}")
    print("Demo official logins: " + ", ".join(local + SUFFIX for local, *_ in OFFICERS))


if __name__ == "__main__":
    main()
