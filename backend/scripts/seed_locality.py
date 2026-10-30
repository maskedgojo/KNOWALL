"""Repeat-safe, fictional Module 4 locality seed. Run from backend/: python -m scripts.seed_locality.

Run scripts.seed_green_valley first (it creates the society and demo users).
Every place, event and alert here is invented, labelled "(demo)" and marked
FICTIONAL_DEMO. Phone numbers use the reserved-looking 00000 pattern and are not
real; seeded verifications use the DEMO_SEED method. Nothing is deleted or reset.
"""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func, inspect, select

from app import create_app
from app.extensions import db
from app.modules.identity.models import AuditLog, PermissionRole, SocietyProfile, User
from app.modules.identity.models.user import utc_now
from app.modules.locality.common import TABLES
from app.modules.locality.models import (
    AlertSeverity, AlertSourceType, AlertStatus, DataOrigin, LocalAlert, LocalEvent, LocalEventCategory,
    LocalEventStatus, LocalityHistory, LocalityProfile, Place, PlaceCategory, PlaceVerification,
    PublicationStatus, VerificationMethod, VerificationStatus,
)

from scripts.seed_green_valley import DEMO_SUFFIX, _ensure_role, _get_or_create_user, _require_password

# Fictional centre point for the schematic map. Not a survey of any real neighbourhood.
CENTER = (20.3000, 85.8200)
SOURCE = "KNOWALL fictional demo data (not a real business)"
EMERGENCY_NOTE = " In a real emergency, dial 112."

CATEGORIES = (
    ("pharmacy", "Pharmacy", "Chemists and medical stores.", False),
    ("hospital_clinic", "Hospital & clinic", "Hospitals, clinics and diagnostic centres.", False),
    ("police", "Police", "Police stations and outposts.", True),
    ("emergency", "Emergency services", "Fire, ambulance and disaster response.", True),
    ("public_service", "Public services", "Post office, ward office, utilities.", False),
    ("other_service", "Other essential services", "Banks, ATMs, groceries and similar.", False),
)

# name, category, (dlat, dlng) offset from the centre or None, phone, address, verified_days_ago or state
PLACES = (
    ("Meadow Care Pharmacy (demo)", "pharmacy", (0.0040, 0.0030), "+91 00000 10001",
     "Shop 3, Meadow Market Road (fictional)", 20,
     "Open 8 am to 10 pm. Phone number in this seed is deliberately outdated for the corrections demo."),
    ("Evergreen Medicals (demo)", "pharmacy", (-0.0060, 0.0050), "+91 00000 10002",
     "12 Lakeview Street (fictional)", 400, "Last checked more than a year ago."),
    ("NightOwl 24x7 Chemist (demo)", "pharmacy", (0.0090, -0.0070), "+91 00000 10003",
     "Bus Stand Corner (fictional)", None, "Claims to be open all night; not yet verified."),
    ("Meadow Park Community Clinic (demo)", "hospital_clinic", (0.0020, -0.0040), "+91 00000 20001",
     "Ward 4 Health Lane (fictional)", 45, "General OPD, weekdays 9 am to 5 pm."),
    ("Sunrise Multispeciality Hospital (demo)", "hospital_clinic", (-0.0110, -0.0090), "+91 00000 20002",
     "Ring Road Exit 2 (fictional)", 10, "24-hour casualty ward."),
    ("Little Steps Child Clinic (demo)", "hospital_clinic", (0.0130, 0.0080), "+91 00000 20003",
     "Park Avenue Block C (fictional)", "NEEDS_RECHECK", "A resident said the clinic may have moved."),
    ("Meadow Park Police Station (demo)", "police", (-0.0030, 0.0100), "+91 00000 30001",
     "Station Road (fictional)", 60, "Front desk open 24 hours." + EMERGENCY_NOTE),
    ("Lakeview Police Outpost (demo)", "police", (0.0150, -0.0120), "+91 00000 30002",
     "Lakeview Junction (fictional)", 250, "Outpost staffed during daytime." + EMERGENCY_NOTE),
    ("Meadow Fire Station (demo)", "emergency", (-0.0080, -0.0020), "+91 00000 40001",
     "Industrial Estate Gate 1 (fictional)", 30, "Fire and rescue." + EMERGENCY_NOTE),
    ("Community Ambulance Point (demo)", "emergency", (0.0050, 0.0120), "+91 00000 40002",
     "Opposite Ward Office (fictional)", 5, "Volunteer-run ambulance base." + EMERGENCY_NOTE),
    ("Meadow Park Post Office (demo)", "public_service", (-0.0010, -0.0080), "+91 00000 50001",
     "Market Square (fictional)", 90, "Speed post and savings counter."),
    ("Ward 4 Municipal Office (demo)", "public_service", (0.0070, 0.0110), "+91 00000 50002",
     "Opposite Ambulance Point (fictional)", 200, "Property tax and certificates."),
    ("Electricity Complaint Centre (demo)", "public_service", None, "+91 00000 50003",
     "Location not confirmed (fictional)", None, "Coordinates not yet recorded."),
    ("Meadow Co-op Bank ATM (demo)", "other_service", (0.0030, 0.0010), "+91 00000 60001",
     "Gate 2, Green Valley Residency (fictional)", 15, "Cash withdrawal only."),
    ("FreshBasket Grocery (demo)", "other_service", (-0.0050, 0.0020), "+91 00000 60002",
     "Meadow Market Road (fictional)", 120, "Groceries and home delivery."),
    ("Lakeview Gas Agency (demo)", "other_service", (0.0100, 0.0040), "+91 00000 60003",
     "Lakeview Street (fictional)", None, "LPG booking counter."),
)


def _at(days: int, hour: int) -> datetime:
    when = datetime.now(timezone.utc).date() + timedelta(days=days)
    return datetime.combine(when, time(hour), tzinfo=timezone.utc)


def _history(locality, entity_type, entity_id, action, actor, reason=None):
    db.session.add(LocalityHistory(locality_id=locality.id, entity_type=entity_type, entity_id=str(entity_id),
                                   actor_user_id=actor.id if actor else None, action=action, reason=reason,
                                   changes={"seed": "fictional demo"}))


def seed_locality() -> dict:
    """Call in a Flask app context. One commit; errors roll back everything."""
    coordinator_password = _require_password("KNOWALL_SEED_COORDINATOR_PASSWORD")
    if coordinator_password in (_require_password("KNOWALL_SEED_ADMIN_PASSWORD"),
                                _require_password("KNOWALL_SEED_RESIDENT_PASSWORD")):
        raise RuntimeError("Use a coordinator password different from the admin and resident passwords.")
    if not set(TABLES) <= set(inspect(db.session.connection()).get_table_names()):
        raise RuntimeError("Module 4 tables are missing. Run flask --app wsgi db upgrade first.")

    try:
        society = db.session.get(SocietyProfile, 1)
        admin = db.session.scalar(select(User).where(User.email == "admin" + DEMO_SUFFIX))
        if society is None or admin is None:
            raise RuntimeError("Run python -m scripts.seed_green_valley first.")

        coordinator = _get_or_create_user("Kavya Demo (Locality Coordinator)", "kavya" + DEMO_SUFFIX,
                                          coordinator_password)
        _ensure_role(coordinator, PermissionRole.LOCALITY_COORDINATOR, admin=admin)

        locality = db.session.scalar(select(LocalityProfile).where(LocalityProfile.society_id == society.id))
        if locality is None:
            locality = LocalityProfile(
                society_id=society.id, name="Meadow Park (fictional)",
                description="Fictional neighbourhood around Green Valley Residency, used for the KNOWALL demo. "
                            "Every listing is invented.",
                center_latitude=CENTER[0], center_longitude=CENTER[1], coverage_radius_m=3000,
                stale_after_days=180, is_fictional=True,
            )
            db.session.add(locality)
            db.session.flush()
            _history(locality, "LOCALITY", locality.id, "CREATED", coordinator)

        categories = {}
        for order, (key, label, description, emergency) in enumerate(CATEGORIES):
            category = db.session.scalar(select(PlaceCategory).where(PlaceCategory.key == key))
            if category is None:
                category = PlaceCategory(key=key, label=label, description=description, is_emergency=emergency,
                                         sort_order=order, active=True)
                db.session.add(category)
                db.session.flush()
            categories[key] = category

        created_places = 0
        for name, key, offset, phone, address, verified, description in PLACES:
            if db.session.scalar(select(Place.id).where(Place.locality_id == locality.id, Place.name == name)):
                continue
            place = Place(
                locality_id=locality.id, category_id=categories[key].id, name=name, description=description,
                address=address, phone=phone, source_label=SOURCE, data_origin=DataOrigin.FICTIONAL_DEMO,
                publication_status=PublicationStatus.ACTIVE, created_by_user_id=coordinator.id,
                updated_by_user_id=coordinator.id,
                latitude=CENTER[0] + offset[0] if offset else None,
                longitude=CENTER[1] + offset[1] if offset else None,
            )
            if isinstance(verified, int):
                place.verification_status = VerificationStatus.VERIFIED
                place.last_verified_at = utc_now() - timedelta(days=verified)
                place.last_verified_by_user_id = coordinator.id
                place.last_verification_method = VerificationMethod.DEMO_SEED
            elif verified == "NEEDS_RECHECK":
                place.verification_status = VerificationStatus.NEEDS_RECHECK
                place.last_verified_at = utc_now() - timedelta(days=70)
                place.last_verification_method = VerificationMethod.DEMO_SEED
            db.session.add(place)
            db.session.flush()
            if place.last_verified_at is not None:
                db.session.add(PlaceVerification(
                    place_id=place.id, verifier_user_id=coordinator.id, method=VerificationMethod.DEMO_SEED,
                    scope="LISTING", note="Simulated verification for fictional demo data.",
                    verified_at=place.last_verified_at,
                ))
            _history(locality, "PLACE", place.id, "CREATED", coordinator)
            created_places += 1

        events = (
            ("Meadow Park Health Camp (demo)", LocalEventCategory.HEALTH, 5, 9, 13, LocalEventStatus.PUBLISHED,
             "Free blood-pressure and sugar checks.", "Meadow Park Community Clinic (demo)", "Clinic courtyard"),
            ("Weekend Farmers' Market (demo)", LocalEventCategory.MARKET, 2, 7, 11, LocalEventStatus.PUBLISHED,
             "Local vegetables and handmade goods.", "Meadow Market Traders (fictional)", "Market Square"),
            ("Lake Clean-up Drive (demo)", LocalEventCategory.CIVIC, -6, 7, 10, LocalEventStatus.PUBLISHED,
             "Volunteers cleaned the lake path.", "Lakeview Residents Forum (fictional)", "Lakeview Junction"),
            ("Street Cricket Friendly (demo)", LocalEventCategory.SPORTS, 8, 16, 19, LocalEventStatus.PENDING,
             "A friendly match between neighbouring societies.", "Rahul Demo", "Ward 4 ground"),
        )
        rahul = db.session.scalar(select(User).where(User.email == "rahul" + DEMO_SUFFIX))
        for title, category, day, start, end, status, description, organizer, venue in events:
            if db.session.scalar(select(LocalEvent.id).where(LocalEvent.title == title)):
                continue
            submitter = rahul if status == LocalEventStatus.PENDING and rahul else coordinator
            event = LocalEvent(
                locality_id=locality.id, title=title, description=description, organizer=organizer, venue=venue,
                category=category, starts_at=_at(day, start), ends_at=_at(day, end), status=status,
                submitted_by_user_id=submitter.id,
                reviewer_user_id=coordinator.id if status == LocalEventStatus.PUBLISHED else None,
                published_at=utc_now() if status == LocalEventStatus.PUBLISHED else None,
                decision_reason="Fictional demo event approved." if status == LocalEventStatus.PUBLISHED else None,
            )
            db.session.add(event)
            db.session.flush()
            _history(locality, "EVENT", event.id, "SUBMITTED", submitter)

        alerts = (
            ("Water supply interruption (demo)", AlertSeverity.MEDIUM, AlertSourceType.OFFICIAL_NOTICE,
             "Ward 4 Municipal Office notice (fictional)", "https://example.org/demo-notice", -1, 2,
             AlertStatus.PUBLISHED, "Supply in Meadow Park reduced from 10 am to 4 pm for pipeline repair."),
            ("Road resurfacing on Station Road (demo)", AlertSeverity.LOW, AlertSourceType.COMMUNITY,
             "Reported by residents (fictional)", None, -10, -3, AlertStatus.PUBLISHED,
             "Expect slow traffic near the police station."),
            ("Heavy rain advisory (demo draft)", AlertSeverity.HIGH, AlertSourceType.SOCIETY,
             "Green Valley Residency committee (fictional)", None, 0, 3, AlertStatus.DRAFT,
             "Draft only: keep basement parking clear."),
        )
        for title, severity, source_type, label, url, start, end, status, description in alerts:
            if db.session.scalar(select(LocalAlert.id).where(LocalAlert.title == title)):
                continue
            alert = LocalAlert(
                locality_id=locality.id, title=title, description=description, severity=severity,
                source_type=source_type, source_label=label, source_url=url,
                starts_at=utc_now() + timedelta(days=start), expires_at=utc_now() + timedelta(days=end),
                status=status, created_by_user_id=coordinator.id,
                reviewer_user_id=coordinator.id if status == AlertStatus.PUBLISHED else None,
                published_at=utc_now() + timedelta(days=start) if status == AlertStatus.PUBLISHED else None,
            )
            db.session.add(alert)
            db.session.flush()
            _history(locality, "ALERT", alert.id, "CREATED", coordinator)

        if db.session.scalar(select(AuditLog.id).where(AuditLog.action == "LOCALITY_DEMO_SEED_INITIALIZED")) is None:
            db.session.add(AuditLog(action="LOCALITY_DEMO_SEED_INITIALIZED", entity_type="LOCALITY_PROFILE",
                                    details={"locality_id": locality.id, "purpose": "fictional development demo"}))
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    return {
        "places": db.session.scalar(select(func.count()).select_from(Place)),
        "created_places": created_places,
        "events": db.session.scalar(select(func.count()).select_from(LocalEvent)),
        "alerts": db.session.scalar(select(func.count()).select_from(LocalAlert)),
        "coordinator": "kavya" + DEMO_SUFFIX,
    }


def main() -> None:
    app = create_app()
    with app.app_context():
        report = seed_locality()
    print("KNOWALL Module 4 fictional locality seed completed (or already present).")
    print("Places: {places} (new: {created_places}); events: {events}; alerts: {alerts}".format(**report))
    print("Locality coordinator: " + report["coordinator"] + " (password from KNOWALL_SEED_COORDINATOR_PASSWORD).")


if __name__ == "__main__":
    main()
