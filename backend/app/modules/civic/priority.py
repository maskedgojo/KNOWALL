"""Transparent community-priority indicator.

No ML, no hidden weighting. The score is a plain sum of three visible inputs and
the response always lists them. It is a signal for coordinators and neighbours,
not a ranking authorities are obliged to follow.
"""
from datetime import datetime, timezone

from app.extensions import db

from .common import aware
from .models import IssueSeverity, PrioritySnapshot

SEVERITY_POINTS = {
    IssueSeverity.LOW: 0, IssueSeverity.MEDIUM: 5, IssueSeverity.HIGH: 10, IssueSeverity.CRITICAL: 20,
}
POINTS_PER_SUPPORTER = 2
SUPPORTER_CAP = 20          # supporters beyond this add nothing
POINTS_PER_DAY = 0.5
AGE_CAP_DAYS = 30           # days beyond this add nothing
BANDS = ((35, "HIGH"), (15, "MEDIUM"), (0, "LOW"))

FORMULA = (
    "score = 2 x supporters (max 20 counted) + 0.5 x days open (max 30 counted) + severity points "
    "(LOW 0, MEDIUM 5, HIGH 10, CRITICAL 20). Bands: LOW below 15, MEDIUM 15-34, HIGH 35 and above."
)
DISCLAIMER = (
    "This indicator summarises community support, age and reported severity. "
    "It does not guarantee any authority action or timeline."
)


def compute(issue, support_count: int, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    reference = issue.submitted_at or issue.created_at
    days_open = max((now - aware(reference)).total_seconds() / 86400, 0.0)
    counted_supporters = min(support_count, SUPPORTER_CAP)
    counted_days = min(days_open, AGE_CAP_DAYS)
    severity_points = SEVERITY_POINTS[issue.severity]
    score = round(
        counted_supporters * POINTS_PER_SUPPORTER + counted_days * POINTS_PER_DAY + severity_points, 1
    )
    band = next(name for floor, name in BANDS if score >= floor)
    return {
        "score": score,
        "band": band,
        "inputs": {
            "supporters": support_count,
            "supporter_points": counted_supporters * POINTS_PER_SUPPORTER,
            "days_open": round(days_open, 1),
            "age_points": round(counted_days * POINTS_PER_DAY, 1),
            "severity": issue.severity.value,
            "severity_points": severity_points,
        },
        "formula": FORMULA,
        "disclaimer": DISCLAIMER,
    }


def record_snapshot(issue, support_count: int, trigger: str) -> PrioritySnapshot:
    """Persist the inputs at a lifecycle moment (validation, routing). Caller commits."""
    result = compute(issue, support_count)
    snapshot = PrioritySnapshot(
        issue_id=issue.id, trigger=trigger, score=result["score"], band=result["band"], inputs=result["inputs"],
    )
    db.session.add(snapshot)
    return snapshot
