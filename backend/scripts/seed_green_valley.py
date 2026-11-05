"""Repeat-safe, fictional local demo seed. Run from backend/: python -m scripts.seed_green_valley.

No destructive resets. Creates four towers, 240 flats, demo households and users.
Requires separate passwords from untracked environment variables; never prints secrets.
"""
import os
from datetime import date, timedelta

from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, ApplicationStatus, AuditLog, Flat, Household, Membership,
    MembershipApplication, MembershipStatus, PermissionRole, ResidentCategory,
    RoleAssignment, SocietyProfile, Tower, User,
)
from app.modules.identity.models.user import utc_now


SOCIETY_NAME = "Green Valley Residency"
DEMO_SUFFIX = "@greenvalley.test"  # Reserved .test domain; all identities fictional.


def _require_password(name: str) -> str:
    value = os.getenv(name, "")
    if len(value) < 12:
        raise RuntimeError(f"Set {name} to a unique value of at least 12 characters in untracked .env.")
    return value


def _get_or_create_tower(name: str) -> Tower:
    tower = db.session.scalar(select(Tower).where(Tower.name == name))
    if tower is None:
        tower = Tower(name=name)
        db.session.add(tower)
        db.session.flush()
    return tower


def _get_or_create_flat(tower: Tower, number: str, floor: int) -> Flat:
    flat = db.session.scalar(
        select(Flat).where(Flat.tower_id == tower.id, Flat.flat_number == number)
    )
    if flat is None:
        flat = Flat(tower=tower, flat_number=number, floor_number=floor)
        db.session.add(flat)
        db.session.flush()
    elif flat.floor_number != floor:
        raise RuntimeError(f"Existing Tower {tower.name} flat {number} has a different floor; seed stopped.")
    return flat


def _get_or_create_household(flat: Flat, label: str) -> Household:
    home = db.session.scalar(
        select(Household).where(Household.flat_id == flat.id, Household.label == label)
    )
    if home is None:
        home = Household(flat=flat, label=label)
        db.session.add(home)
        db.session.flush()
    return home


def _get_or_create_user(name: str, email: str, raw_password: str) -> User:
    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        # This verification flag is ONLY for fictional demo identities, not actual email proof.
        user = User(
            display_name=name, email=email,
            password_hash=generate_password_hash(raw_password),
            email_verified_at=utc_now(), account_status=AccountStatus.ACTIVE,
        )
        db.session.add(user)
        db.session.flush()
    elif user.account_status != AccountStatus.ACTIVE:
        raise RuntimeError(f"Demo account {email} is disabled/suspended; refusing to reactivate it.")
    # Never reset existing passwords or verification flags on repeated seed.
    return user


def _get_or_create_membership(
    user: User, household: Household, category: ResidentCategory,
    sponsor: Membership | None = None,
) -> Membership:
    previous = db.session.scalar(
        select(Membership).where(
            Membership.user_id == user.id,
            Membership.household_id == household.id,
            Membership.category == category,
        ).order_by(Membership.created_at.desc())
    )
    if previous is not None:
        if previous.status != MembershipStatus.ACTIVE:
            raise RuntimeError(f"Membership for {user.email} is not active; seed will not reinstate it.")
        return previous

    membership = Membership(
        user=user, household=household, category=category,
        status=MembershipStatus.ACTIVE, sponsor=sponsor,
        valid_from=date.today(),
        valid_until=(date.today() + timedelta(days=365) if category == ResidentCategory.TENANT else None),
    )
    db.session.add(membership)
    db.session.flush()
    return membership


def _ensure_role(user: User, role: PermissionRole, admin: User | None = None) -> None:
    assignments = db.session.scalars(
        select(RoleAssignment).where(RoleAssignment.user_id == user.id, RoleAssignment.role == role)
    ).all()
    if any(row.revoked_at is None for row in assignments):
        return
    if assignments:
        raise RuntimeError(f"Role {role.value} for {user.email} was revoked; seed will not restore it.")
    db.session.add(RoleAssignment(user=user, role=role, granted_by=admin))
    db.session.flush()


def _seed_operations(admin: User) -> None:
    """Module 3 demo amenities, event, maintenance and project. Skipped until migrated."""
    from datetime import datetime, time, timezone
    from sqlalchemy import inspect
    from app.modules.operations.common import OPERATIONS_TABLES, SOCIETY_TZ
    from app.modules.operations.models import (
        DevelopmentProject, EventStatus, Facility, MaintenanceItem, MaintenanceStatus, ProjectMilestone,
        ProjectStatus, SocietyEvent,
    )

    # Inspect through the session's connection: a separate engine checkout can
    # reset a shared pooled connection and discard this seed's uncommitted rows.
    if not set(OPERATIONS_TABLES) <= set(inspect(db.session.connection()).get_table_names()):
        print("Module 3 tables not migrated yet; skipping operations demo data.")
        return
    for name, values in (
        ("Clubhouse", dict(description="Party hall with kitchenette (fictional).", location="Tower A ground floor",
                           capacity=60, open_minute=8 * 60, close_minute=22 * 60, slot_minutes=60,
                           max_minutes_per_booking=240, requires_approval=True)),
        ("Badminton Court", dict(description="Indoor court (fictional).", location="Sports block",
                                 capacity=4, open_minute=6 * 60, close_minute=21 * 60, slot_minutes=60,
                                 max_minutes_per_booking=60, requires_approval=False)),
    ):
        if db.session.scalar(select(Facility.id).where(Facility.society_id == 1, Facility.name == name)) is None:
            db.session.add(Facility(society_id=1, name=name, booking_window_days=14, **values))

    def local(days: int, hour: int) -> datetime:
        when = date.today() + timedelta(days=days)
        return datetime.combine(when, time(hour), tzinfo=SOCIETY_TZ).astimezone(timezone.utc)

    if db.session.scalar(select(SocietyEvent.id).where(SocietyEvent.title == "Diwali Evening (demo)")) is None:
        db.session.add(SocietyEvent(
            society_id=1, organizer_user_id=admin.id, title="Diwali Evening (demo)",
            description="Lights, sweets and music on the central lawn.", venue="Central lawn",
            starts_at=local(10, 18), ends_at=local(10, 21), capacity=3, status=EventStatus.PUBLISHED,
        ))
    if db.session.scalar(select(MaintenanceItem.id).where(MaintenanceItem.title == "Lift B1 servicing (demo)")) is None:
        db.session.add(MaintenanceItem(
            society_id=1, asset="Lift B1", title="Lift B1 servicing (demo)",
            description="Annual safety servicing. Please use Lift B2.", scheduled_start=local(3, 10),
            scheduled_end=local(3, 14), status=MaintenanceStatus.PLANNED, created_by_user_id=admin.id,
        ))
    project = db.session.scalar(select(DevelopmentProject).where(DevelopmentProject.title == "Lobby renovation (demo)"))
    if project is None:
        project = DevelopmentProject(
            society_id=1, title="Lobby renovation (demo)", description="New flooring and lighting for Tower B lobby.",
            status=ProjectStatus.IN_PROGRESS, budget_note="Approved in AGM (fictional).",
            expected_completion=date.today() + timedelta(days=60), created_by_user_id=admin.id,
        )
        db.session.add(project)
        db.session.flush()
        for title, status, percent, due in (
            ("Remove old flooring", ProjectStatus.COMPLETED, 100, 10),
            ("Lay new tiles", ProjectStatus.IN_PROGRESS, 40, 30),
            ("Install lighting", ProjectStatus.PLANNED, 0, 55),
        ):
            db.session.add(ProjectMilestone(
                project_id=project.id, title=title, status=status, percent=percent,
                due_date=date.today() + timedelta(days=due), updated_by_user_id=admin.id,
            ))


def seed_green_valley() -> dict:
    """Call in a Flask app context. Commit once; errors roll back all changes."""
    admin_password = _require_password("KNOWALL_SEED_ADMIN_PASSWORD")
    resident_password = _require_password("KNOWALL_SEED_RESIDENT_PASSWORD")
    if admin_password == resident_password:
        raise RuntimeError("Use different demo admin and resident passwords.")

    try:
        profile = db.session.get(SocietyProfile, 1)
        if profile is None:
            profile = SocietyProfile(
                id=1, name=SOCIETY_NAME,
                address="42 Evergreen Lane (fictional)",
                locality="Meadow Park (fictional)", city="Demo City",
            )
            db.session.add(profile)
            db.session.flush()
        elif profile.name != SOCIETY_NAME:
            raise RuntimeError("Database has a different society profile; refusing to overwrite it.")

        towers = {}
        flats = {}
        for tower_name in ("A", "B", "C", "D"):
            tower = towers[tower_name] = _get_or_create_tower(tower_name)
            # 10 floors x 6 flats = 60/tower, total 240. B-402 exists as flat_number '402'.
            for floor in range(1, 11):
                for unit in range(1, 7):
                    flat_number = f"{floor}{unit:02d}"
                    flats[(tower_name, flat_number)] = _get_or_create_flat(tower, flat_number, floor)

        admin = _get_or_create_user(
            "Green Valley Demo Administrator", "admin" + DEMO_SUFFIX, admin_password
        )
        _ensure_role(admin, PermissionRole.SOCIETY_ADMIN)

        owner_household = _get_or_create_household(flats[("B", "402")], "Demo Owner Household")
        tenant_household = _get_or_create_household(flats[("B", "402")], "Demo Tenant Household")

        rahul = _get_or_create_user("Rahul Demo", "rahul" + DEMO_SUFFIX, resident_password)
        priya = _get_or_create_user("Priya Demo", "priya" + DEMO_SUFFIX, resident_password)
        amit = _get_or_create_user("Amit Demo", "amit" + DEMO_SUFFIX, resident_password)
        sneha = _get_or_create_user("Sneha Demo", "sneha" + DEMO_SUFFIX, resident_password)
        owner = _get_or_create_membership(rahul, owner_household, ResidentCategory.OWNER)
        _get_or_create_membership(priya, owner_household, ResidentCategory.FAMILY_MEMBER, sponsor=owner)
        tenant = _get_or_create_membership(amit, tenant_household, ResidentCategory.TENANT)
        _get_or_create_membership(sneha, tenant_household, ResidentCategory.FAMILY_MEMBER, sponsor=tenant)
        for user in (rahul, priya, amit, sneha):
            _ensure_role(user, PermissionRole.RESIDENT, admin=admin)

        maya = _get_or_create_user("Maya Demo", "maya" + DEMO_SUFFIX, resident_password)
        _ensure_role(maya, PermissionRole.APPLICANT, admin=admin)
        flat_c301 = flats[("C", "301")]
        existing_application = db.session.scalar(
            select(MembershipApplication).where(
                MembershipApplication.user_id == maya.id,
                MembershipApplication.flat_id == flat_c301.id,
                MembershipApplication.category == ResidentCategory.TENANT,
            )
        )
        if existing_application is None:
            db.session.add(MembershipApplication(
                user=maya, flat=flat_c301,
                category=ResidentCategory.TENANT, status=ApplicationStatus.DRAFT,
                applicant_notes="Fictional example; document upload pending.",
            ))

        _seed_operations(admin)

        already_logged = db.session.scalar(
            select(AuditLog.id).where(
                AuditLog.action == "DEMO_SEED_INITIALIZED",
                AuditLog.entity_type == "SOCIETY_PROFILE",
            )
        )
        if already_logged is None:
            db.session.add(AuditLog(
                action="DEMO_SEED_INITIALIZED", entity_type="SOCIETY_PROFILE",
                details={"society": SOCIETY_NAME, "purpose": "fictional development demo"},
            ))

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "society_profiles": db.session.scalar(select(func.count()).select_from(SocietyProfile)),
        "towers": db.session.scalar(select(func.count()).select_from(Tower)),
        "flats": db.session.scalar(select(func.count()).select_from(Flat)),
        "demo_user_emails": [
            "admin" + DEMO_SUFFIX, "rahul" + DEMO_SUFFIX, "priya" + DEMO_SUFFIX,
            "amit" + DEMO_SUFFIX, "sneha" + DEMO_SUFFIX, "maya" + DEMO_SUFFIX,
        ],
    }


def main() -> None:
    app = create_app()
    with app.app_context():
        report = seed_green_valley()
    print("KNOWALL fictional demo seed completed (or already present).")
    print("Society profiles: {society_profiles}; towers: {towers}; flats: {flats}".format(**report))
    print("Demo emails: " + ", ".join(report["demo_user_emails"]))
    print("Passwords are not printed or reset on repeat runs.")


if __name__ == "__main__":
    main()
