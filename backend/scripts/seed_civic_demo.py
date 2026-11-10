"""Repeat-safe Module 5 demo seed. Run from backend/: python -m scripts.seed_civic_demo.

Requires the Module 1 demo seed first (python -m scripts.seed_green_valley) and the Module 5 migration.
Creates the Green Valley civic coverage area and a few fictional issues for the demo storyline:

  * Rahul's pothole (submitted, awaiting coordinator review)
  * Maya's near-duplicate of that pothole (submitted) to demonstrate duplicate suggestions and merging
  * Priya's streetlight (validated, with two supporters, so it is one photo away from routing)

All coordinates, people and text are fictional. No destructive resets; existing rows are never changed.
"""
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.modules.civic.models import (
    ActorRole, CivicIssue, CivicLocality, IssueCategory, IssuePrivacy, IssueSeverity, IssueState, IssueSupport,
)
from app.modules.civic.service import initial_transition, transition
from app.modules.identity.models import SocietyProfile, User

SUFFIX = "@greenvalley.test"
# Fictional centre in Bhubaneswar; radius covers the complex and the surrounding streets.
CENTER_LAT, CENTER_LON, RADIUS_M = 20.2961, 85.8245, 2500


def _user(name: str) -> User:
    user = db.session.scalar(select(User).where(User.email == name + SUFFIX))
    if user is None:
        raise RuntimeError(f"Demo user {name}{SUFFIX} is missing. Run scripts.seed_green_valley first.")
    return user


def _locality() -> CivicLocality:
    if db.session.get(SocietyProfile, 1) is None:
        raise RuntimeError("Society profile is missing. Run scripts.seed_green_valley first.")
    loc = db.session.scalar(select(CivicLocality).where(CivicLocality.society_id == 1))
    if loc is None:
        loc = CivicLocality(
            society_id=1, name="Green Valley and surroundings",
            center_lat=CENTER_LAT, center_lon=CENTER_LON, radius_m=RADIUS_M, is_active=True,
        )
        db.session.add(loc)
        db.session.flush()
    return loc


def _issue(loc, creator, title, description, category, severity, lat, lon, hint, *, validate_by=None):
    existing = db.session.scalar(select(CivicIssue).where(CivicIssue.title == title, CivicIssue.creator_id == creator.id))
    if existing:
        return existing, False
    issue = CivicIssue(
        locality_id=loc.id, creator_id=creator.id, category=category, severity=severity, title=title,
        description=description, latitude=lat, longitude=lon, address_hint=hint,
        privacy=IssuePrivacy.PUBLIC_NAME, state=IssueState.DRAFT,
    )
    db.session.add(issue)
    db.session.flush()
    initial_transition(issue, actor_id=creator.id)
    transition(issue, IssueState.SUBMITTED, actor_id=creator.id, role=ActorRole.REPORTER, reason="Submitted by reporter.")
    if validate_by:
        transition(issue, IssueState.VALIDATED, actor_id=validate_by.id, role=ActorRole.MODERATOR,
                   reason="Validated by coordinator (demo seed).")
    return issue, True


def seed_civic_demo() -> dict:
    admin, rahul, priya = _user("admin"), _user("rahul"), _user("priya")
    amit, sneha, maya = _user("amit"), _user("sneha"), _user("maya")
    loc = _locality()
    created = 0
    for args, kwargs in (
        ((rahul, "Deep pothole outside the main gate road",
          "A deep pothole on the service road just outside the Green Valley main gate. "
          "Two-wheelers swerve into traffic to avoid it, especially after rain.",
          IssueCategory.ROAD_DAMAGE, IssueSeverity.HIGH, 20.29640, 85.82480, "Opposite the main gate"), {}),
        ((maya, "Pothole on service road near main entrance",
          "Large pothole on the road beside the main entrance. Water collects in it and it is hard to see at night.",
          IssueCategory.ROAD_DAMAGE, IssueSeverity.MEDIUM, 20.29645, 85.82485, "Near the entrance bus stop"), {}),
        ((priya, "Streetlight not working on the park lane",
          "The streetlight at the corner of the park lane has been off for over a week, leaving the stretch very dark.",
          IssueCategory.STREETLIGHT, IssueSeverity.MEDIUM, 20.29800, 85.82200, "Corner of the park lane"),
         {"validate_by": admin}),
    ):
        issue, is_new = _issue(loc, *args, **kwargs)
        created += is_new
        if issue.category == IssueCategory.STREETLIGHT:
            for supporter in (amit, sneha):
                exists = db.session.scalar(select(IssueSupport.id).where(
                    IssueSupport.issue_id == issue.id, IssueSupport.user_id == supporter.id))
                if not exists:
                    db.session.add(IssueSupport(issue_id=issue.id, user_id=supporter.id))
    db.session.commit()
    return {"issues_created": created}


def main() -> None:
    app = create_app()
    with app.app_context():
        report = seed_civic_demo()
    print("KNOWALL Module 5 civic demo seed completed (or already present).")
    print("New issues created: {issues_created}".format(**report))


if __name__ == "__main__":
    main()
