"""Resident directory corrections and the coordinator review workflow.

PENDING -> APPROVED | REJECTED | CLARIFICATION_REQUESTED
CLARIFICATION_REQUESTED -> PENDING (reporter responds) | REJECTED
Residents never write to a place. Approval applies one validated field change
inside a transaction and refuses if the published value changed after the
correction was submitted, so conflicting proposals cannot overwrite each other.
"""
from flask import request
from flask_login import current_user
from sqlalchemy import func, select

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now

from .common import (
    coordinates, enum_value, history_for, history_json, iso, locality_bp, locality_scope, manage_locality,
    names, pagination, phone, record, store, suggest_locality, text, web_url, within_coverage,
)
from .models import (
    CorrectionIssue, CorrectionStatus, ListingCorrection, Place, PlaceCategory, PlaceVerification,
    PublicationStatus, VerificationMethod,
)

ISSUE_FIELD = {
    CorrectionIssue.WRONG_PHONE: "phone",
    CorrectionIssue.WRONG_ADDRESS: "address",
    CorrectionIssue.WRONG_COORDINATES: "coordinates",
    CorrectionIssue.WRONG_NAME: "name",
    CorrectionIssue.WRONG_CATEGORY: "category",
    CorrectionIssue.WRONG_WEBSITE: "website_url",
}
ARCHIVE_ON_APPROVE = (CorrectionIssue.MOVED_OR_CLOSED, CorrectionIssue.DUPLICATE)
OPEN = (CorrectionStatus.PENDING, CorrectionStatus.CLARIFICATION_REQUESTED)
MAX_OPEN_PER_REPORTER = 10
PROPOSAL_KEYS = {"proposed_value", "proposed_latitude", "proposed_longitude", "proposed_category", "source_url"}


def _current_value(place: Place, field: str | None) -> str | None:
    if place is None or field is None:
        return None
    if field == "coordinates":
        return None if place.latitude is None else f"{place.latitude:.6f},{place.longitude:.6f}"
    if field == "category":
        category = db.session.get(PlaceCategory, place.category_id)
        return category.key if category else None
    return getattr(place, field)


def _proposal(issue, body, locality, place, problems) -> dict:
    """Validate the proposed change for this issue type. Never accepts arbitrary fields."""
    field = ISSUE_FIELD.get(issue)
    values = {"proposed_value": None, "proposed_latitude": None, "proposed_longitude": None,
              "proposed_category_id": None}
    if field == "phone":
        values["proposed_value"] = phone(body.get("proposed_value"), "proposed_value", problems, required=True)
    elif field == "address":
        values["proposed_value"] = text(body.get("proposed_value"), "proposed_value", 5, 300, problems)
    elif field == "name":
        values["proposed_value"] = text(body.get("proposed_value"), "proposed_value", 2, 160, problems)
    elif field == "website_url":
        values["proposed_value"] = web_url(body.get("proposed_value"), "proposed_value", problems, required=True)
    elif field == "coordinates":
        lat, lng = coordinates(body, locality, problems, "proposed_latitude", "proposed_longitude")
        if lat is None and "proposed_latitude" not in problems:
            problems["proposed_latitude"] = "Give the corrected latitude and longitude."
        values["proposed_latitude"], values["proposed_longitude"] = lat, lng
        if lat is not None:
            values["proposed_value"] = f"{lat:.6f},{lng:.6f}"
    elif field == "category" or issue == CorrectionIssue.MISSING_SERVICE:
        key = body.get("proposed_category")
        category = db.session.scalar(select(PlaceCategory).where(PlaceCategory.key == key, PlaceCategory.active.is_(True))) \
            if isinstance(key, str) else None
        if category is None:
            problems["proposed_category"] = "Choose a valid category."
        else:
            values["proposed_category_id"] = category.id
            if field == "category":
                values["proposed_value"] = category.key
        if issue == CorrectionIssue.MISSING_SERVICE:
            values["proposed_value"] = text(body.get("proposed_value"), "proposed_value", 2, 160, problems)
    else:
        values["proposed_value"] = text(body.get("proposed_value"), "proposed_value", 2, 500, problems, required=False)
    if field and values["proposed_value"] is not None and values["proposed_value"] == _current_value(place, field):
        problems["proposed_value"] = "This already matches the published listing."
    return values


def _reporter_json(row: ListingCorrection, place: Place | None) -> dict:
    history = history_for("CORRECTION", row.id)
    return {
        "id": str(row.id),
        "place": {"id": str(place.id), "name": place.name, "publication_status": place.publication_status.value}
        if place else None,
        "issue_type": row.issue_type.value,
        "field": row.field,
        "current_value": row.current_value,
        "proposed_value": row.proposed_value,
        "reason": row.reason,
        "source_url": row.source_url,
        "status": row.status.value,
        "decision_reason": row.decision_reason,
        "reviewed_at": iso(row.reviewed_at),
        "submitted_at": iso(row.submitted_at),
        "updated_at": iso(row.updated_at),
        # The reporter sees decisions and reasons, not reviewer identities.
        "history": history_json(history, {}, include_actor=False),
    }


def _staff_json(row: ListingCorrection, place: Place | None, people: dict, *, detail=False) -> dict:
    payload = _reporter_json(row, place) if detail else {
        "id": str(row.id),
        "place": {"id": str(place.id), "name": place.name, "publication_status": place.publication_status.value}
        if place else None,
        "issue_type": row.issue_type.value, "field": row.field, "current_value": row.current_value,
        "proposed_value": row.proposed_value, "reason": row.reason, "source_url": row.source_url,
        "status": row.status.value, "decision_reason": row.decision_reason,
        "reviewed_at": iso(row.reviewed_at), "submitted_at": iso(row.submitted_at),
    }
    published = _current_value(place, row.field) if place else None
    payload.update({
        "reporter_display_name": people.get(row.reporter_user_id, ""),
        "reviewer_display_name": people.get(row.reviewer_user_id),
        "published_value": published,
        "published_changed_since_submission": bool(row.field) and place is not None and published != row.current_value,
    })
    return payload


def _create(locality, place, body):
    problems: dict = {}
    issue = enum_value(CorrectionIssue, body.get("issue_type"), "issue_type", problems)
    if issue is None:
        return error("VALIDATION_ERROR", "Choose what is wrong.", 400, fields=problems)
    if (place is None) != (issue == CorrectionIssue.MISSING_SERVICE):
        return error("VALIDATION_ERROR", "Report a missing service separately from an existing listing.", 400,
                     fields={"issue_type": "Not valid here."})
    values = _proposal(issue, body, locality, place, problems)
    reason = text(body.get("reason"), "reason", 10, 1000, problems)
    source_url = web_url(body.get("source_url"), "source_url", problems)
    if problems:
        return error("VALIDATION_ERROR", "Check the correction and try again.", 400, fields=problems)
    open_mine = db.session.scalar(select(func.count()).where(
        ListingCorrection.reporter_user_id == current_user.id, ListingCorrection.status.in_(OPEN)
    ))
    if open_mine >= MAX_OPEN_PER_REPORTER:
        return error("TOO_MANY_OPEN_CORRECTIONS",
                     f"You already have {MAX_OPEN_PER_REPORTER} corrections awaiting review.", 429)
    if place is not None and db.session.scalar(select(ListingCorrection.id).where(
        ListingCorrection.reporter_user_id == current_user.id, ListingCorrection.place_id == place.id,
        ListingCorrection.issue_type == issue, ListingCorrection.status.in_(OPEN),
    )) is not None:
        return error("DUPLICATE_OPEN_CORRECTION",
                     "You already reported this problem; it is awaiting review in My corrections.", 409)
    now = utc_now()
    field = ISSUE_FIELD.get(issue)
    correction = ListingCorrection(
        locality_id=locality.id, place_id=place.id if place else None, reporter_user_id=current_user.id,
        issue_type=issue, field=field, current_value=_current_value(place, field),
        reason=reason, source_url=source_url, place_version=place.version if place else None,
        status=CorrectionStatus.PENDING, submitted_at=now, updated_at=now, **values,
    )
    db.session.add(correction)
    db.session.flush()
    record(locality, "CORRECTION", correction.id, "SUBMITTED",
           changes={"proposed_value": [correction.current_value, correction.proposed_value]},
           reason=reason, audit_details={"issue_type": issue.value, "place_id": str(place.id) if place else None})
    db.session.commit()
    return store({"correction": _reporter_json(correction, place)}, 201)


@locality_bp.post("/api/locality/places/<uuid:place_id>/corrections")
@suggest_locality
def create_correction(place_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"issue_type", "reason", *PROPOSAL_KEYS})
    if failure:
        return failure
    place = db.session.scalar(select(Place).where(
        Place.id == place_id, Place.locality_id == locality.id, Place.publication_status == PublicationStatus.ACTIVE
    ))
    if place is None:
        return error("PLACE_NOT_FOUND", "Place not found.", 404)
    return _create(locality, place, body)


@locality_bp.post("/api/locality/corrections")
@suggest_locality
def report_missing_service():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"issue_type", "reason", *PROPOSAL_KEYS})
    if failure:
        return failure
    return _create(locality, None, body)


@locality_bp.get("/api/locality/corrections/me")
@suggest_locality
def my_corrections():
    locality, failure = locality_scope()
    if failure:
        return failure
    rows = db.session.scalars(
        select(ListingCorrection).where(ListingCorrection.locality_id == locality.id,
                                        ListingCorrection.reporter_user_id == current_user.id)
        .order_by(ListingCorrection.submitted_at.desc(), ListingCorrection.id.desc())
    ).all()
    places = {row.id: row for row in db.session.scalars(
        select(Place).where(Place.id.in_({row.place_id for row in rows if row.place_id}))
    )} if rows else {}
    return store({"corrections": [_reporter_json(row, places.get(row.place_id)) for row in rows]})


@locality_bp.post("/api/locality/corrections/<uuid:correction_id>/respond")
@suggest_locality
def respond_to_clarification(correction_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"message", *PROPOSAL_KEYS})
    if failure:
        return failure
    correction = db.session.scalar(select(ListingCorrection).where(
        ListingCorrection.id == correction_id, ListingCorrection.locality_id == locality.id,
        ListingCorrection.reporter_user_id == current_user.id,
    ).with_for_update())
    if correction is None:
        return error("CORRECTION_NOT_FOUND", "Correction not found.", 404)
    if correction.status != CorrectionStatus.CLARIFICATION_REQUESTED:
        return error("CLARIFICATION_NOT_REQUESTED", "This correction is not waiting for your reply.", 409)
    place = db.session.get(Place, correction.place_id) if correction.place_id else None
    if place is not None and place.publication_status != PublicationStatus.ACTIVE:
        return error("PLACE_ARCHIVED", "This listing has been archived.", 409)
    problems: dict = {}
    message = text(body.get("message"), "message", 5, 1000, problems)
    changes = {}
    if any(key in body for key in ("proposed_value", "proposed_latitude", "proposed_category")):
        values = _proposal(correction.issue_type, body, locality, place, problems)
        if not problems:
            if values["proposed_value"] != correction.proposed_value:
                changes["proposed_value"] = [correction.proposed_value, values["proposed_value"]]
            for key, value in values.items():
                setattr(correction, key, value)
    if "source_url" in body:
        source_url = web_url(body.get("source_url"), "source_url", problems)
        if not problems and source_url != correction.source_url:
            changes["source_url"] = [correction.source_url, source_url]
            correction.source_url = source_url
    if problems:
        db.session.rollback()
        return error("VALIDATION_ERROR", "Check your reply and try again.", 400, fields=problems)
    # The reply is judged against what is published now.
    if place is not None:
        snapshot = _current_value(place, correction.field)
        if snapshot != correction.current_value:
            changes["current_value"] = [correction.current_value, snapshot]
        correction.current_value = snapshot
        correction.place_version = place.version
    correction.status = CorrectionStatus.PENDING
    correction.updated_at = utc_now()
    record(locality, "CORRECTION", correction.id, "CLARIFIED", changes=changes or None, reason=message)
    db.session.commit()
    return store({"correction": _reporter_json(correction, place)})


# ------------------------------------------------------------------ coordinator queue

@locality_bp.get("/api/locality/admin/corrections")
@manage_locality
def admin_list_corrections():
    locality, failure = locality_scope()
    if failure:
        return failure
    page = pagination(default_limit=50)
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    query = select(ListingCorrection).where(ListingCorrection.locality_id == locality.id)
    status = request.args.get("status")
    if status:
        try:
            query = query.where(ListingCorrection.status == CorrectionStatus(status))
        except ValueError:
            return error("VALIDATION_ERROR", "Unknown correction status.", 400)
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(
        query.order_by(ListingCorrection.submitted_at.asc(), ListingCorrection.id.asc()).limit(limit).offset(offset)
    ).all()
    places = {row.id: row for row in db.session.scalars(
        select(Place).where(Place.id.in_({row.place_id for row in rows if row.place_id}))
    )} if rows else {}
    people = names([*(row.reporter_user_id for row in rows), *(row.reviewer_user_id for row in rows)])
    open_by_field = {}
    for place_id, field, count in db.session.execute(
        select(ListingCorrection.place_id, ListingCorrection.field, func.count())
        .where(ListingCorrection.locality_id == locality.id, ListingCorrection.status.in_(OPEN))
        .group_by(ListingCorrection.place_id, ListingCorrection.field)
    ).all():
        open_by_field[(place_id, field)] = count
    items = []
    for row in rows:
        item = _staff_json(row, places.get(row.place_id), people)
        item["competing_open_corrections"] = max(open_by_field.get((row.place_id, row.field), 0) - (1 if row.status in OPEN else 0), 0) \
            if row.place_id else 0
        items.append(item)
    return store({"corrections": items, "total": total, "pagination": {"limit": limit, "offset": offset}})


@locality_bp.get("/api/locality/admin/corrections/<uuid:correction_id>")
@manage_locality
def admin_get_correction(correction_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    row = db.session.scalar(select(ListingCorrection).where(
        ListingCorrection.id == correction_id, ListingCorrection.locality_id == locality.id
    ))
    if row is None:
        return error("CORRECTION_NOT_FOUND", "Correction not found.", 404)
    place = db.session.get(Place, row.place_id) if row.place_id else None
    related = db.session.scalars(select(ListingCorrection).where(
        ListingCorrection.place_id == row.place_id, ListingCorrection.id != row.id,
        ListingCorrection.field.is_(row.field) if row.field is None else ListingCorrection.field == row.field,
    ).order_by(ListingCorrection.submitted_at.asc())).all() if row.place_id else []
    history = history_for("CORRECTION", row.id)
    people = names([row.reporter_user_id, row.reviewer_user_id, *(item.reporter_user_id for item in related),
                    *(item.actor_user_id for item in history)])
    payload = _staff_json(row, place, people, detail=True)
    payload["history"] = history_json(history, people, include_actor=True)
    payload["related_corrections"] = [{
        "id": str(item.id), "status": item.status.value, "proposed_value": item.proposed_value,
        "reporter_display_name": people.get(item.reporter_user_id, ""), "submitted_at": iso(item.submitted_at),
    } for item in related]
    if place is not None:
        category = db.session.get(PlaceCategory, place.category_id)
        payload["place_detail"] = {
            "id": str(place.id), "name": place.name, "category": category.label if category else None,
            "address": place.address, "phone": place.phone, "website_url": place.website_url,
            "source_label": place.source_label, "data_origin": place.data_origin.value, "version": place.version,
        }
    return store({"correction": payload})


@locality_bp.post("/api/locality/admin/corrections/<uuid:correction_id>/decision")
@manage_locality
def admin_decide_correction(correction_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"decision", "reason"})
    if failure:
        return failure
    problems: dict = {}
    decision = body.get("decision")
    if decision not in ("APPROVE", "REJECT", "REQUEST_CLARIFICATION"):
        problems["decision"] = "Use APPROVE, REJECT or REQUEST_CLARIFICATION."
    reason = text(body.get("reason"), "reason", 5, 1000, problems)
    if problems:
        return error("VALIDATION_ERROR", "Give a decision and the reason for it.", 400, fields=problems)
    correction = db.session.scalar(select(ListingCorrection).where(
        ListingCorrection.id == correction_id, ListingCorrection.locality_id == locality.id
    ).with_for_update())
    if correction is None:
        return error("CORRECTION_NOT_FOUND", "Correction not found.", 404)
    if correction.reporter_user_id == current_user.id:
        return error("SELF_REVIEW_FORBIDDEN", "Another coordinator must review your own correction.", 403)
    allowed = {
        "APPROVE": (CorrectionStatus.PENDING,),
        "REQUEST_CLARIFICATION": (CorrectionStatus.PENDING,),
        "REJECT": OPEN,
    }[decision]
    if correction.status not in allowed:
        return error("INVALID_STATUS_TRANSITION",
                     f"A {correction.status.value.lower().replace('_', ' ')} correction cannot be "
                     f"{'approved' if decision == 'APPROVE' else 'rejected' if decision == 'REJECT' else 'sent back'}.", 409)
    now = utc_now()
    place = None
    if correction.place_id:
        place = db.session.scalar(select(Place).where(Place.id == correction.place_id).with_for_update())

    if decision == "APPROVE" and place is not None:
        if place.publication_status != PublicationStatus.ACTIVE:
            return error("PLACE_ARCHIVED", "The listing is archived; reject or restore it first.", 409)
        field = correction.field
        if field:
            published = _current_value(place, field)
            if published != correction.current_value:
                return error("PLACE_CHANGED_SINCE_SUBMISSION",
                             f"The published {field.replace('_', ' ')} changed after this correction was submitted "
                             f"(now: {published or 'empty'}). Request clarification or reject it.", 409)
            if field == "coordinates":
                if not within_coverage(locality, correction.proposed_latitude, correction.proposed_longitude):
                    return error("OUTSIDE_COVERAGE", "The proposed point is outside the current coverage area.", 409)
                place.latitude, place.longitude = correction.proposed_latitude, correction.proposed_longitude
            elif field == "category":
                place.category_id = correction.proposed_category_id
            else:
                setattr(place, field, correction.proposed_value)
            change = {field: [published, correction.proposed_value]}
            action = "CORRECTION_APPLIED"
            db.session.add(PlaceVerification(
                place_id=place.id, verifier_user_id=current_user.id, method=VerificationMethod.CORRECTION_REVIEW,
                scope=field, source_url=correction.source_url, note=reason[:500], verified_at=now,
            ))
        elif correction.issue_type in ARCHIVE_ON_APPROVE:
            place.publication_status = PublicationStatus.ARCHIVED
            place.archived_reason = f"Correction approved ({correction.issue_type.value.lower().replace('_', ' ')}): {reason}"[:500]
            change = {"publication_status": ["ACTIVE", "ARCHIVED"]}
            action = "ARCHIVED"
        else:
            change, action = None, None
        if action:
            place.version += 1
            place.updated_by_user_id = current_user.id
            place.updated_at = now
            record(locality, "PLACE", place.id, action, changes={**change, "correction_id": str(correction.id)},
                   reason=reason, audit_details={"correction_id": str(correction.id)})

    correction.status = {"APPROVE": CorrectionStatus.APPROVED, "REJECT": CorrectionStatus.REJECTED,
                         "REQUEST_CLARIFICATION": CorrectionStatus.CLARIFICATION_REQUESTED}[decision]
    correction.reviewer_user_id = current_user.id
    correction.decision_reason = reason
    correction.reviewed_at = now
    correction.updated_at = now
    record(locality, "CORRECTION", correction.id, correction.status.value,
           changes={"proposed_value": [correction.current_value, correction.proposed_value]},
           reason=reason, audit_details={"decision": decision})
    db.session.commit()
    people = names([correction.reporter_user_id, correction.reviewer_user_id])
    return store({"correction": _staff_json(correction, place, people, detail=True)})
