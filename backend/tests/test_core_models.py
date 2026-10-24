"""Focused model tests (SQLite is isolated test storage, not the app database)."""
from datetime import date

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.models import (
    Flat, Household, Membership, MembershipStatus,
    ResidentCategory, SocietyProfile, Tower, User,
)


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def create_residence():
    tower = Tower(name="b")
    flat = Flat(tower=tower, flat_number="402", floor_number=4)
    owner_household = Household(flat=flat, label="Owner household")
    tenant_household = Household(flat=flat, label="Tenant household")
    db.session.add_all([tower, flat, owner_household, tenant_household])
    db.session.flush()
    return tower, flat, owner_household, tenant_household


def user(name, email):
    account = User(display_name=name, email=email, password_hash="test-hash-not-a-real-password")
    db.session.add(account)
    db.session.flush()
    return account


def test_two_households_one_flat_and_sponsored_family(app):
    with app.app_context():
        _, flat, owner_home, tenant_home = create_residence()
        owner = user("Rahul", "Rahul@EXAMPLE.com")
        tenant = user("Amit", "amit@example.com")
        relative = user("Priya", "priya@example.com")
        owner_member = Membership(
            user=owner, household=owner_home, category=ResidentCategory.OWNER,
            valid_from=date(2026, 10, 21),
        )
        tenant_member = Membership(
            user=tenant, household=tenant_home, category=ResidentCategory.TENANT,
            valid_from=date(2026, 10, 21), valid_until=date(2027, 10, 20),
        )
        relative_member = Membership(
            user=relative, household=owner_home, category=ResidentCategory.FAMILY_MEMBER,
            sponsor=owner_member, valid_from=date(2026, 10, 21),
        )
        db.session.add_all([owner_member, tenant_member, relative_member])
        db.session.commit()
        assert owner.email == "rahul@example.com"
        assert owner_home.flat_id == tenant_home.flat_id == flat.id
        assert relative_member.sponsor.id == owner_member.id
        assert relative_member.status == MembershipStatus.ACTIVE


def test_unique_flat_number_within_tower(app):
    with app.app_context():
        tower, _, _, _ = create_residence()
        db.session.commit()
        db.session.add(Flat(tower=tower, flat_number="402", floor_number=4))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_family_requires_sponsor(app):
    with app.app_context():
        _, _, household, _ = create_residence()
        person = user("Priya", "priya@example.com")
        db.session.add(Membership(
            user=person, household=household, category=ResidentCategory.FAMILY_MEMBER,
            valid_from=date(2026, 10, 21),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_society_profile_singleton(app):
    with app.app_context():
        db.session.add(SocietyProfile(id=1, name="Green Valley Residency", address="Fictional street",
                                      locality="Demo locality", city="Demo city"))
        db.session.commit()
        db.session.add(SocietyProfile(id=2, name="Other society", address="Fictional street",
                                      locality="Demo locality", city="Demo city"))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_no_duplicate_active_membership(app):
    with app.app_context():
        _, _, home, _ = create_residence()
        person = user("Rahul", "rahul@example.com")
        db.session.add(Membership(
            user=person, household=home, category=ResidentCategory.OWNER,
            valid_from=date(2026, 10, 21),
        ))
        db.session.commit()
        db.session.add(Membership(
            user=person, household=home, category=ResidentCategory.OWNER,
            valid_from=date(2026, 10, 21),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_membership_expiry_cannot_precede_start(app):
    with app.app_context():
        _, _, home, _ = create_residence()
        person = user("Amit", "amit@example.com")
        db.session.add(Membership(
            user=person, household=home, category=ResidentCategory.TENANT,
            valid_from=date(2026, 10, 21), valid_until=date(2026, 10, 20),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
