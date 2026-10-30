"""Locality profile, coverage lookup, directory search and coordinator listing stewardship."""
from datetime import timedelta

from flask import request
from flask_login import current_user
from sqlalchemy import and_, func, or_, select

from app.extensions import db
from app.modules.identity.auth.routes import error, json_object
from app.modules.identity.models.user import utc_now

from .common import (
    active_categories, coordinates, coordinate, enum_value, history_for, history_json, locality_bp,
    locality_json, locality_scope, manage_locality, names, pagination, phone, place_json, read_locality,
    record, store, text, verification_state, web_url, within_coverage, distance_m, category_json,
)
from .models import (
    CorrectionStatus, DataOrigin, LocalAlert, AlertStatus, ListingCorrection, LocalEvent, LocalEventStatus,
    LocalityContentReport, Place, PlaceCategory, PlaceVerification, PublicationStatus, ReportStatus,
    VerificationMethod, VerificationStatus,
)

OPEN_CORRECTIONS = (CorrectionStatus.PENDING, CorrectionStatus.CLARIFICATION_REQUESTED)
EDITABLE = ("name", "category", "description", "address", "latitude", "longitude", "phone", "website_url",
            "source_label", "source_url", "data_origin")
STAFF_METHODS = (VerificationMethod.PHONE_CALL, VerificationMethod.SITE_VISIT,
                 VerificationMethod.OFFICIAL_SOURCE, VerificationMethod.DOCUMENT)


def _category(key) -> PlaceCategory | None:
    if not isinstance(key, str):
        return None
    return db.session.scalar(select(PlaceCategory).where(PlaceCategory.key == key, PlaceCategory.active.is_(True)))


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _search(locality, *, include_archived: bool):
    """Server-side keyword + category filter. Returns (query, problem_response)."""
    query = (select(Place, PlaceCategory).join(PlaceCategory, PlaceCategory.id == Place.category_id)
             .where(Place.locality_id == locality.id))
    if not include_archived:
        query = query.where(Place.publication_status == PublicationStatus.ACTIVE)
    keyword = (request.args.get("q") or "").strip()
    if len(keyword) > 100:
        return None, error("VALIDATION_ERROR", "Search text must be at most 100 characters.", 400)
    if keyword:
        pattern = f"%{_escape_like(keyword.lower())}%"
        query = query.where(or_(*(
            func.lower(column).like(pattern, escape="\\")
            for column in (Place.name, Place.address, Place.description, PlaceCategory.label, PlaceCategory.key)
        )))
    category_key = request.args.get("category")
    if category_key:
        category = _category(category_key)
        if category is None:
            return None, error("VALIDATION_ERROR", "Unknown category.", 400)
        query = query.where(Place.category_id == category.id)
    return query, None


def _get_place(place_id, locality, *, include_archived=False, lock=False):
    query = select(Place).where(Place.id == place_id, Place.locality_id == locality.id)
    if not include_archived:
        query = query.where(Place.publication_status == PublicationStatus.ACTIVE)
    if lock:
        query = query.with_for_update()
    return db.session.scalar(query)


# ------------------------------------------------------------------ resident reads

@locality_bp.get("/api/locality/profile")
@read_locality
def get_profile():
    locality, failure = locality_scope()
    if failure:
        return failure
    categories = active_categories()
    counts = dict(db.session.execute(
        select(Place.category_id, func.count()).where(
            Place.locality_id == locality.id, Place.publication_status == PublicationStatus.ACTIVE
        ).group_by(Place.category_id)
    ).all())
    payload = locality_json(locality, categories)
    for item, category in zip(payload["categories"], categories):
        item["place_count"] = counts.get(category.id, 0)
    return store({"locality": payload})


@locality_bp.get("/api/locality/coverage/check")
@read_locality
def check_coverage():
    """Module 5 contract: is a point inside this locality's coverage?"""
    locality, failure = locality_scope()
    if failure:
        return failure
    problems: dict = {}
    try:
        lat = coordinate(float(request.args.get("latitude", "")), "latitude", -90, 90, problems)
        lng = coordinate(float(request.args.get("longitude", "")), "longitude", -180, 180, problems)
    except ValueError:
        return error("VALIDATION_ERROR", "Give numeric latitude and longitude.", 400)
    if problems:
        return error("VALIDATION_ERROR", "Check the coordinates.", 400, fields=problems)
    distance = distance_m(locality.center_latitude, locality.center_longitude, lat, lng)
    return store({"locality_id": locality.id, "inside": distance <= locality.coverage_radius_m,
                  "distance_m": round(distance), "radius_m": locality.coverage_radius_m})


@locality_bp.get("/api/locality/places")
@read_locality
def list_places():
    locality, failure = locality_scope()
    if failure:
        return failure
    page = pagination(default_limit=50)
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    query, failure = _search(locality, include_archived=False)
    if failure:
        return failure
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(
        query.order_by(PlaceCategory.sort_order, Place.name, Place.id).limit(limit).offset(offset)
    ).all()
    return store({
        "places": [place_json(place, category, locality) for place, category in rows],
        "total": total,
        "pagination": {"limit": limit, "offset": offset},
    })


@locality_bp.get("/api/locality/places/<uuid:place_id>")
@read_locality
def get_place(place_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    place = _get_place(place_id, locality)
    if place is None:
        return error("PLACE_NOT_FOUND", "Place not found.", 404)
    category = db.session.get(PlaceCategory, place.category_id)
    mine = db.session.scalars(
        select(ListingCorrection).where(ListingCorrection.place_id == place.id,
                                        ListingCorrection.reporter_user_id == current_user.id)
        .order_by(ListingCorrection.submitted_at.desc())
    ).all()
    open_count = db.session.scalar(select(func.count()).where(
        ListingCorrection.place_id == place.id, ListingCorrection.status.in_(OPEN_CORRECTIONS)
    ))
    # Public history: what changed and when; no actor identities or correction evidence.
    public_actions = ("CREATED", "UPDATED", "VERIFIED", "CORRECTION_APPLIED", "MARKED_FOR_RECHECK")
    history = [row for row in history_for("PLACE", place.id) if row.action in public_actions]
    return store({
        "place": place_json(place, category, locality),
        "open_corrections": open_count,
        "my_corrections": [{"id": str(row.id), "issue_type": row.issue_type.value, "status": row.status.value,
                            "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None}
                           for row in mine],
        "history": history_json(history[-10:], {}, include_actor=False),
    })


# ------------------------------------------------------------------ coordinator: profile and summary

@locality_bp.get("/api/locality/admin/summary")
@manage_locality
def admin_summary():
    locality, failure = locality_scope()
    if failure:
        return failure
    now = utc_now()
    cutoff = now - timedelta(days=locality.stale_after_days)
    scoped = and_(Place.locality_id == locality.id, Place.publication_status == PublicationStatus.ACTIVE)

    def count(*conditions):
        return db.session.scalar(select(func.count()).where(*conditions))
    return store({"summary": {
        "places_active": count(scoped),
        "places_unverified": count(scoped, Place.verification_status == VerificationStatus.UNVERIFIED),
        "places_needing_recheck": count(scoped, or_(
            Place.verification_status == VerificationStatus.NEEDS_RECHECK,
            and_(Place.verification_status == VerificationStatus.VERIFIED, Place.last_verified_at < cutoff),
        )),
        "corrections_pending": count(ListingCorrection.locality_id == locality.id,
                                     ListingCorrection.status == CorrectionStatus.PENDING),
        "corrections_awaiting_reporter": count(ListingCorrection.locality_id == locality.id,
                                               ListingCorrection.status == CorrectionStatus.CLARIFICATION_REQUESTED),
        "events_pending": count(LocalEvent.locality_id == locality.id, LocalEvent.status == LocalEventStatus.PENDING),
        "alerts_draft": count(LocalAlert.locality_id == locality.id, LocalAlert.status == AlertStatus.DRAFT),
        "alerts_active": count(LocalAlert.locality_id == locality.id, LocalAlert.status == AlertStatus.PUBLISHED,
                               LocalAlert.starts_at <= now, LocalAlert.expires_at > now),
        "reports_open": count(LocalityContentReport.locality_id == locality.id,
                              LocalityContentReport.status == ReportStatus.OPEN),
    }})


@locality_bp.patch("/api/locality/admin/profile")
@manage_locality
def update_profile():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"name", "description", "center_latitude", "center_longitude",
                                 "coverage_radius_m", "stale_after_days"})
    if failure:
        return failure
    problems: dict = {}
    updates = {}
    if "name" in body:
        updates["name"] = text(body["name"], "name", 3, 120, problems)
    if "description" in body:
        updates["description"] = text(body["description"], "description", 10, 2000, problems)
    for key in ("center_latitude", "center_longitude"):
        if key in body:
            low, high = (-90, 90) if key == "center_latitude" else (-180, 180)
            updates[key] = coordinate(body[key], key, low, high, problems)
    for key, low, high in (("coverage_radius_m", 200, 20000), ("stale_after_days", 7, 3650)):
        if key in body:
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                problems[key] = f"Must be a whole number from {low} to {high}."
            else:
                updates[key] = value
    if problems:
        return error("VALIDATION_ERROR", "Check the locality settings.", 400, fields=problems)
    before = {key: getattr(locality, key) for key in updates}
    for key, value in updates.items():
        setattr(locality, key, value)
    # Never silently strand published places outside a shrunken or moved coverage area.
    outside = [place.name for place in db.session.scalars(select(Place).where(
        Place.locality_id == locality.id, Place.publication_status == PublicationStatus.ACTIVE,
        Place.latitude.is_not(None),
    )) if not within_coverage(locality, place.latitude, place.longitude)]
    if outside:
        db.session.rollback()
        return error("PLACES_OUTSIDE_COVERAGE",
                     f"{len(outside)} active listing(s) would fall outside the new coverage: {', '.join(outside[:5])}.",
                     409)
    changes = {key: [before[key], value] for key, value in updates.items() if before[key] != value}
    if changes:
        locality.updated_at = utc_now()
        record(locality, "PROFILE", locality.id, "PROFILE_UPDATED", changes=changes,
               audit_details={"fields": sorted(changes)})
    db.session.commit()
    return store({"locality": locality_json(locality, active_categories())})


# ------------------------------------------------------------------ coordinator: listings

def _place_fields(body, locality, problems, *, partial: bool) -> dict:
    values = {}

    def present(key):
        return key in body or not partial
    if present("name"):
        values["name"] = text(body.get("name"), "name", 2, 160, problems)
    if present("category"):
        category = _category(body.get("category"))
        if category is None:
            problems["category"] = "Choose a valid category."
        else:
            values["category_id"] = category.id
    if present("description"):
        values["description"] = text(body.get("description"), "description", 3, 2000, problems, required=False)
    if present("address"):
        values["address"] = text(body.get("address"), "address", 5, 300, problems, required=False)
    if "latitude" in body or "longitude" in body or not partial:
        lat, lng = coordinates(body, locality, problems)
        values["latitude"], values["longitude"] = lat, lng
    if present("phone"):
        values["phone"] = phone(body.get("phone"), "phone", problems)
    if present("website_url"):
        values["website_url"] = web_url(body.get("website_url"), "website_url", problems)
    if present("source_label"):
        values["source_label"] = text(body.get("source_label"), "source_label", 3, 200, problems)
    if present("source_url"):
        values["source_url"] = web_url(body.get("source_url"), "source_url", problems)
    if present("data_origin"):
        values["data_origin"] = enum_value(DataOrigin, body.get("data_origin"), "data_origin", problems)
    # Partial edits re-check this against the stored record in admin_update_place.
    if not partial and values.get("data_origin") == DataOrigin.REAL_WORLD and not values.get("source_url"):
        problems.setdefault("source_url", "A real-world listing needs a source link.")
    return values


def _duplicate(locality, name, address, exclude_id=None) -> bool:
    query = select(Place.id).where(
        Place.locality_id == locality.id, Place.publication_status == PublicationStatus.ACTIVE,
        func.lower(Place.name) == name.lower(),
        func.lower(func.coalesce(Place.address, "")) == (address or "").lower(),
    )
    if exclude_id is not None:
        query = query.where(Place.id != exclude_id)
    return db.session.scalar(query) is not None


def _staff_place(place, locality):
    category = db.session.get(PlaceCategory, place.category_id)
    people = names([place.last_verified_by_user_id])
    return place_json(place, category, locality, people=people, staff=True)


@locality_bp.get("/api/locality/admin/places")
@manage_locality
def admin_list_places():
    locality, failure = locality_scope()
    if failure:
        return failure
    page = pagination(default_limit=50)
    if page is None:
        return error("VALIDATION_ERROR", "Invalid limit or offset.", 400)
    limit, offset = page
    query, failure = _search(locality, include_archived=True)
    if failure:
        return failure
    state = request.args.get("state")
    cutoff = utc_now() - timedelta(days=locality.stale_after_days)
    active = Place.publication_status == PublicationStatus.ACTIVE
    filters = {
        "ARCHIVED": Place.publication_status == PublicationStatus.ARCHIVED,
        "NEEDS_RECHECK": and_(active, Place.verification_status == VerificationStatus.NEEDS_RECHECK),
        "UNVERIFIED": and_(active, Place.verification_status == VerificationStatus.UNVERIFIED),
        "STALE": and_(active, Place.verification_status == VerificationStatus.VERIFIED, Place.last_verified_at < cutoff),
        "VERIFIED": and_(active, Place.verification_status == VerificationStatus.VERIFIED, Place.last_verified_at >= cutoff),
        "ACTIVE": active,
    }
    if state:
        if state not in filters:
            return error("VALIDATION_ERROR", "Unknown state filter.", 400)
        query = query.where(filters[state])
    total = db.session.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.session.execute(query.order_by(Place.name, Place.id).limit(limit).offset(offset)).all()
    open_counts = dict(db.session.execute(
        select(ListingCorrection.place_id, func.count()).where(
            ListingCorrection.place_id.in_([place.id for place, _ in rows]),
            ListingCorrection.status.in_(OPEN_CORRECTIONS),
        ).group_by(ListingCorrection.place_id)
    ).all()) if rows else {}
    people = names(place.last_verified_by_user_id for place, _ in rows)
    places = []
    for place, category in rows:
        item = place_json(place, category, locality, people=people, staff=True)
        item["open_corrections"] = open_counts.get(place.id, 0)
        places.append(item)
    return store({"places": places, "total": total, "pagination": {"limit": limit, "offset": offset}})


@locality_bp.post("/api/locality/admin/places")
@manage_locality
def admin_create_place():
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object(set(EDITABLE))
    if failure:
        return failure
    problems: dict = {}
    values = _place_fields(body, locality, problems, partial=False)
    if problems:
        return error("VALIDATION_ERROR", "Check the listing and try again.", 400, fields=problems)
    if _duplicate(locality, values["name"], values.get("address")):
        return error("DUPLICATE_PLACE", "An active listing with this name and address already exists.", 409)
    now = utc_now()
    place = Place(locality_id=locality.id, created_by_user_id=current_user.id, created_at=now, updated_at=now,
                  verification_status=VerificationStatus.UNVERIFIED, publication_status=PublicationStatus.ACTIVE,
                  version=1, **values)
    db.session.add(place)
    db.session.flush()
    record(locality, "PLACE", place.id, "CREATED", changes={"name": [None, place.name]},
           audit_details={"name": place.name})
    db.session.commit()
    return store({"place": _staff_place(place, locality)}, 201)


@locality_bp.get("/api/locality/admin/places/<uuid:place_id>")
@manage_locality
def admin_get_place(place_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    place = _get_place(place_id, locality, include_archived=True)
    if place is None:
        return error("PLACE_NOT_FOUND", "Place not found.", 404)
    verifications = db.session.scalars(
        select(PlaceVerification).where(PlaceVerification.place_id == place.id)
        .order_by(PlaceVerification.verified_at.desc())
    ).all()
    corrections = db.session.scalars(
        select(ListingCorrection).where(ListingCorrection.place_id == place.id)
        .order_by(ListingCorrection.submitted_at.desc())
    ).all()
    history = history_for("PLACE", place.id)
    people = names([*(row.verifier_user_id for row in verifications), *(row.actor_user_id for row in history),
                    *(row.reporter_user_id for row in corrections), place.last_verified_by_user_id])
    return store({
        "place": _staff_place(place, locality),
        "verifications": [{"id": str(row.id), "method": row.method.value, "scope": row.scope,
                           "source_url": row.source_url, "note": row.note,
                           "verified_at": row.verified_at.isoformat() if row.verified_at else None,
                           "verifier_display_name": people.get(row.verifier_user_id)} for row in verifications],
        "corrections": [{"id": str(row.id), "issue_type": row.issue_type.value, "field": row.field,
                         "status": row.status.value, "proposed_value": row.proposed_value,
                         "reporter_display_name": people.get(row.reporter_user_id),
                         "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None}
                        for row in corrections],
        "history": history_json(history, people, include_actor=True),
    })


@locality_bp.patch("/api/locality/admin/places/<uuid:place_id>")
@manage_locality
def admin_update_place(place_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({*EDITABLE, "expected_version", "note"})
    if failure:
        return failure
    expected = body.pop("expected_version", None)
    note = body.pop("note", None)
    problems: dict = {}
    if isinstance(expected, bool) or not isinstance(expected, int):
        problems["expected_version"] = "Send the version you edited."
    note = text(note, "note", 3, 500, problems, required=False)
    values = _place_fields(body, locality, problems, partial=True)
    if problems:
        return error("VALIDATION_ERROR", "Check the listing and try again.", 400, fields=problems)
    place = _get_place(place_id, locality, include_archived=True, lock=True)
    if place is None:
        return error("PLACE_NOT_FOUND", "Place not found.", 404)
    if place.version != expected:
        return error("PLACE_VERSION_CONFLICT",
                     "This listing changed after you opened it. Reload it and apply your edit again.", 409)
    if values.get("data_origin", place.data_origin) == DataOrigin.REAL_WORLD and not values.get("source_url", place.source_url):
        return error("VALIDATION_ERROR", "A real-world listing needs a source link.", 400,
                     fields={"source_url": "A real-world listing needs a source link."})
    name = values.get("name", place.name)
    address = values["address"] if "address" in values else place.address
    if _duplicate(locality, name, address, exclude_id=place.id):
        return error("DUPLICATE_PLACE", "An active listing with this name and address already exists.", 409)
    changes = {}
    for key, value in values.items():
        old = getattr(place, key)
        old_plain, new_plain = (old.value if hasattr(old, "value") else old), (value.value if hasattr(value, "value") else value)
        if old_plain != new_plain:
            changes[key] = [old_plain, new_plain]
            setattr(place, key, value)
    if not changes:
        return store({"place": _staff_place(place, locality)})
    place.version += 1
    place.updated_by_user_id = current_user.id
    place.updated_at = utc_now()
    record(locality, "PLACE", place.id, "UPDATED", changes=changes, reason=note,
           audit_details={"fields": sorted(changes)})
    db.session.commit()
    return store({"place": _staff_place(place, locality)})


@locality_bp.post("/api/locality/admin/places/<uuid:place_id>/verify")
@manage_locality
def admin_verify_place(place_id):
    locality, failure = locality_scope()
    if failure:
        return failure
    body, failure = json_object({"method", "source_url", "note"})
    if failure:
        return failure
    problems: dict = {}
    method = enum_value(VerificationMethod, body.get("method"), "method", problems)
    if method is not None and method not in STAFF_METHODS:
        problems["method"] = "Use PHONE_CALL, SITE_VISIT, OFFICIAL_SOURCE or DOCUMENT."
    source_url = web_url(body.get("source_url"), "source_url", problems,
                         required=method == VerificationMethod.OFFICIAL_SOURCE)
    note = text(body.get("note"), "note", 3, 500, problems)
    if problems:
        return error("VALIDATION_ERROR", "Describe how the listing was verified.", 400, fields=problems)
    place = _get_place(place_id, locality, lock=True)
    if place is None:
        return error("PLACE_NOT_FOUND", "Active place not found.", 404)
    now = utc_now()
    previous = verification_state(place, locality, now)
    place.verification_status = VerificationStatus.VERIFIED
    place.last_verified_at = now
    place.last_verified_by_user_id = current_user.id
    place.last_verification_method = method
    place.version += 1
    place.updated_at = now
    db.session.add(PlaceVerification(place_id=place.id, verifier_user_id=current_user.id, method=method,
                                     scope="LISTING", source_url=source_url, note=note, verified_at=now))
    record(locality, "PLACE", place.id, "VERIFIED", changes={"verification_state": [previous, "VERIFIED"]},
           reason=note, audit_details={"method": method.value})
    db.session.commit()
    return store({"place": _staff_place(place, locality)})


def _status_change(place_id, *, action, reason_label):
    locality, failure = locality_scope()
    if failure:
        return None, None, None, failure
    body, failure = json_object({"reason"})
    if failure:
        return None, None, None, failure
    problems: dict = {}
    reason = text(body.get("reason"), "reason", 3, 500, problems)
    if problems:
        return None, None, None, error("VALIDATION_ERROR", f"Give a reason for {reason_label}.", 400, fields=problems)
    place = _get_place(place_id, locality, include_archived=True, lock=True)
    if place is None:
        return None, None, None, error("PLACE_NOT_FOUND", "Place not found.", 404)
    return locality, place, reason, None


@locality_bp.post("/api/locality/admin/places/<uuid:place_id>/mark-stale")
@manage_locality
def admin_mark_stale(place_id):
    locality, place, reason, failure = _status_change(place_id, action="recheck", reason_label="the recheck")
    if failure:
        return failure
    if place.publication_status == PublicationStatus.ARCHIVED:
        return error("PLACE_ARCHIVED", "Restore the listing before flagging it.", 409)
    if place.verification_status == VerificationStatus.NEEDS_RECHECK:
        return error("ALREADY_FLAGGED", "This listing is already flagged for recheck.", 409)
    previous = verification_state(place, locality)
    place.verification_status = VerificationStatus.NEEDS_RECHECK
    place.version += 1
    place.updated_at = utc_now()
    record(locality, "PLACE", place.id, "MARKED_FOR_RECHECK", changes={"verification_state": [previous, "NEEDS_RECHECK"]},
           reason=reason)
    db.session.commit()
    return store({"place": _staff_place(place, locality)})


@locality_bp.post("/api/locality/admin/places/<uuid:place_id>/archive")
@manage_locality
def admin_archive_place(place_id):
    locality, place, reason, failure = _status_change(place_id, action="archive", reason_label="archiving")
    if failure:
        return failure
    if place.publication_status == PublicationStatus.ARCHIVED:
        return error("PLACE_ARCHIVED", "This listing is already archived.", 409)
    place.publication_status = PublicationStatus.ARCHIVED
    place.archived_reason = reason
    place.version += 1
    place.updated_at = utc_now()
    record(locality, "PLACE", place.id, "ARCHIVED", changes={"publication_status": ["ACTIVE", "ARCHIVED"]}, reason=reason)
    db.session.commit()
    return store({"place": _staff_place(place, locality)})


@locality_bp.post("/api/locality/admin/places/<uuid:place_id>/restore")
@manage_locality
def admin_restore_place(place_id):
    locality, place, reason, failure = _status_change(place_id, action="restore", reason_label="restoring")
    if failure:
        return failure
    if place.publication_status == PublicationStatus.ACTIVE:
        return error("PLACE_ACTIVE", "This listing is already active.", 409)
    if _duplicate(locality, place.name, place.address, exclude_id=place.id):
        return error("DUPLICATE_PLACE", "Another active listing has this name and address.", 409)
    if place.latitude is not None and not within_coverage(locality, place.latitude, place.longitude):
        return error("OUTSIDE_COVERAGE", "This listing is outside the current coverage area.", 409)
    place.publication_status = PublicationStatus.ACTIVE
    place.archived_reason = None
    place.version += 1
    place.updated_at = utc_now()
    record(locality, "PLACE", place.id, "RESTORED", changes={"publication_status": ["ARCHIVED", "ACTIVE"]}, reason=reason)
    db.session.commit()
    return store({"place": _staff_place(place, locality)})


@locality_bp.get("/api/locality/categories")
@read_locality
def list_categories():
    locality, failure = locality_scope()
    if failure:
        return failure
    return store({"categories": [category_json(item) for item in active_categories()]})
