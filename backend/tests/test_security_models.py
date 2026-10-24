"""Phase 2C focused database checks, run with the complete existing tests."""
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash

from app.extensions import db
from app.modules.identity.models import (
    AuditLog, AuthToken, AuthTokenPurpose, Flat, Household, Membership,
    PermissionRole, ResidentCategory, RoleAssignment, SocietyProfile, Tower, User,
)
from scripts.seed_green_valley import seed_green_valley


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def new_user(email="person@example.test"):
    user = User(display_name="Example", email=email, password_hash="non-real-test-hash")
    db.session.add(user)
    db.session.flush()
    return user


def test_role_assignment_unique_while_active_and_history_retained(app):
    with app.app_context():
        person = new_user()
        first = RoleAssignment(user=person, role=PermissionRole.RESIDENT)
        db.session.add(first)
        db.session.commit()
        db.session.add(RoleAssignment(user=person, role=PermissionRole.RESIDENT))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        first.revoked_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        db.session.commit()
        db.session.add(RoleAssignment(user=person, role=PermissionRole.RESIDENT))
        db.session.commit()
        assert db.session.scalar(select(func.count()).select_from(RoleAssignment)) == 2


def test_auth_token_hash_stored_and_single_use_record_state(app):
    with app.app_context():
        person = new_user()
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(b"random-example-only-token").hexdigest()
        token = AuthToken(
            user=person, purpose=AuthTokenPurpose.PASSWORD_RESET,
            token_hash=digest, created_at=now, expires_at=now + timedelta(minutes=30),
        )
        db.session.add(token)
        db.session.commit()
        assert token.token_hash == digest
        assert token.purpose == AuthTokenPurpose.PASSWORD_RESET
        token.used_at = now + timedelta(minutes=3)
        db.session.commit()
        assert token.used_at is not None


def test_duplicate_auth_token_hash_disallowed(app):
    with app.app_context():
        person = new_user()
        now = datetime.now(timezone.utc)
        values = dict(user=person, purpose=AuthTokenPurpose.EMAIL_VERIFICATION,
                      token_hash="c" * 64, created_at=now,
                      expires_at=now + timedelta(hours=1))
        db.session.add(AuthToken(**values))
        db.session.commit()
        db.session.add(AuthToken(**values))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_token_expiry_must_follow_creation(app):
    with app.app_context():
        person = new_user()
        now = datetime.now(timezone.utc)
        db.session.add(AuthToken(
            user=person, purpose=AuthTokenPurpose.EMAIL_VERIFICATION,
            token_hash="d" * 64, created_at=now,
            expires_at=now - timedelta(seconds=1),
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_token_cannot_be_used_and_revoked(app):
    with app.app_context():
        person = new_user()
        now = datetime.now(timezone.utc)
        db.session.add(AuthToken(
            user=person, purpose=AuthTokenPurpose.PASSWORD_RESET,
            token_hash="e" * 64, created_at=now,
            expires_at=now + timedelta(hours=1), used_at=now, revoked_at=now,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_audit_log_supports_admin_actor_or_system_event(app):
    with app.app_context():
        admin = new_user()
        subject = uuid.uuid4()
        db.session.add_all([
            AuditLog(actor=admin, action="MEMBERSHIP_APPROVED", entity_type="MEMBERSHIP",
                     entity_id=subject, details={"decision": "approved"}),
            AuditLog(action="DEMO_SEED_INITIALIZED", entity_type="SOCIETY_PROFILE"),
        ])
        db.session.commit()
        events = db.session.scalars(select(AuditLog).order_by(AuditLog.action)).all()
        assert len(events) == 2
        assert next(e for e in events if e.action == "MEMBERSHIP_APPROVED").actor.id == admin.id
        assert next(e for e in events if e.action == "DEMO_SEED_INITIALIZED").actor is None


def test_demo_seed_fictional_data_and_idempotence(app, monkeypatch):
    monkeypatch.setenv("KNOWALL_SEED_ADMIN_PASSWORD", "DemoAdminPassword!123")
    monkeypatch.setenv("KNOWALL_SEED_RESIDENT_PASSWORD", "DemoResidentPassword!456")
    with app.app_context():
        first = seed_green_valley()
        assert first["society_profiles"] == 1
        assert first["towers"] == 4
        assert first["flats"] == 240
        admin = db.session.scalar(select(User).where(User.email == "admin@greenvalley.test"))
        assert check_password_hash(admin.password_hash, "DemoAdminPassword!123")
        assert admin.password_hash != "DemoAdminPassword!123"
        assignments = db.session.scalars(
            select(RoleAssignment).where(RoleAssignment.user_id == admin.id)
        ).all()
        assert len(assignments) == 1 and assignments[0].role == PermissionRole.SOCIETY_ADMIN

        flat = db.session.scalar(select(Flat).join(Tower).where(
            Tower.name == "B", Flat.flat_number == "402"
        ))
        homes = db.session.scalars(select(Household).where(Household.flat_id == flat.id)).all()
        assert len(homes) == 2
        membership_types = db.session.scalars(
            select(Membership.category).join(Household).where(Household.flat_id == flat.id)
        ).all()
        assert membership_types.count(ResidentCategory.OWNER) == 1
        assert membership_types.count(ResidentCategory.TENANT) == 1
        assert membership_types.count(ResidentCategory.FAMILY_MEMBER) == 2

        roles_before = db.session.scalar(select(func.count()).select_from(RoleAssignment))
        members_before = db.session.scalar(select(func.count()).select_from(Membership))
        audit_before = db.session.scalar(select(func.count()).select_from(AuditLog))
        again = seed_green_valley()
        assert again["flats"] == 240
        assert db.session.scalar(select(func.count()).select_from(RoleAssignment)) == roles_before
        assert db.session.scalar(select(func.count()).select_from(Membership)) == members_before
        assert db.session.scalar(select(func.count()).select_from(AuditLog)) == audit_before


def test_demo_seed_rejects_unrelated_existing_society(app, monkeypatch):
    monkeypatch.setenv("KNOWALL_SEED_ADMIN_PASSWORD", "DemoAdminPassword!123")
    monkeypatch.setenv("KNOWALL_SEED_RESIDENT_PASSWORD", "DemoResidentPassword!456")
    with app.app_context():
        db.session.add(SocietyProfile(
            id=1, name="Different Society", address="Other", locality="Other", city="Other"
        ))
        db.session.commit()
        with pytest.raises(RuntimeError, match="different society"):
            seed_green_valley()
        assert db.session.scalar(select(func.count()).select_from(Flat)) == 0


def test_demo_seed_requires_secure_input_passwords(app, monkeypatch):
    monkeypatch.delenv("KNOWALL_SEED_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("KNOWALL_SEED_RESIDENT_PASSWORD", raising=False)
    with app.app_context():
        with pytest.raises(RuntimeError, match="KNOWALL_SEED_ADMIN_PASSWORD"):
            seed_green_valley()
        assert db.session.scalar(select(func.count()).select_from(SocietyProfile)) == 0
