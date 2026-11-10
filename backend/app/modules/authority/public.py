"""Read contract Module 5 consumes (see civic.service.authority_status).

Module 6 is the owner of record for case status; Module 5 only displays this.
"""
from app.modules.governance.schema import tables_present

from .service import case_for_issue, public_status


def case_status_for_issue(issue_id) -> dict | None:
    if not tables_present("authority_cases", "authority_case_events", "authority_departments"):
        return None
    case = case_for_issue(issue_id)
    return public_status(case) if case else None
