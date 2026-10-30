"""Phase 4A HTTP contract tests on an isolated DB; never touch knowall_dev."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import AccountStatus, PermissionRole, RoleAssignment, User



@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "non-production-test-key-for-phase-4a-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
    })

    # Create tables in a temporary application context.
    with application.app_context():
        db.create_all()

    # Do not keep the same application context active
    # across separate HTTP requests.
    try:
        yield application
    finally:
        # Clean up using a new application context.
        with application.app_context():
            db.session.remove()
            db.drop_all()



@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    response = client.get("/api/auth/csrf")
    assert response.status_code == 200
    return response.json["csrf_token"]


def submit(client, route, data, token=None):
    headers = {"X-CSRF-Token": csrf(client) if token is None else token}
    return client.post(route, json=data, headers=headers)


def register(client, *, email="new.person@example.test", password="LongValidPassphrase!234"):
    return submit(client, "/api/auth/register", {
        "display_name": "  Example Resident  ", "email": email, "password": password,
    })


def test_health_still_works(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "service": "knowall-api"}


def test_register_creates_unverified_applicant_and_hashes_password(client, app):
    response = register(client, email="New.Person@EXAMPLE.test")
    assert response.status_code == 201
    account = response.json["user"]
    assert account["email"] == "new.person@example.test"
    assert account["email_verified"] is False
    assert account["display_name"] == "Example Resident"
    assert "password" not in str(response.json).lower()
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "new.person@example.test"))
        assert user and check_password_hash(user.password_hash, "LongValidPassphrase!234")
        assert user.password_hash != "LongValidPassphrase!234"
        role = db.session.scalar(select(RoleAssignment).where(RoleAssignment.user_id == user.id))
        assert role.role == PermissionRole.APPLICANT
        assert user.email_verified_at is None


def test_registration_does_not_automatically_log_in(client):
    assert register(client).status_code == 201
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json["error"]["code"] == "AUTH_REQUIRED"


def test_login_me_logout_lifecycle(client):
    assert register(client).status_code == 201
    response = submit(client, "/api/auth/login", {
        "email": "NEW.PERSON@EXAMPLE.TEST", "password": "LongValidPassphrase!234",
    })
    assert response.status_code == 200
    token_after_login = response.json["csrf_token"]
    assert response.json["user"]["email_verified"] is False
    assert client.get("/api/auth/me").status_code == 200
    # Previous token was invalidated during session rotation.
    stale = client.post("/api/auth/logout", headers={"X-CSRF-Token": "stale-token"})
    assert stale.status_code == 403
    assert client.get("/api/auth/me").status_code == 200
    goodbye = client.post("/api/auth/logout", headers={"X-CSRF-Token": token_after_login})
    assert goodbye.status_code == 200
    assert goodbye.json["message"] == "Logged out."
    assert client.get("/api/auth/me").status_code == 401


def test_duplicate_email_case_insensitive(client):
    assert register(client).status_code == 201
    response = register(client, email="NEW.PERSON@EXAMPLE.TEST")
    assert response.status_code == 409
    assert response.json["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


@pytest.mark.parametrize("email,password", [
    ("unknown@example.test", "LongValidPassphrase!234"),
    ("new.person@example.test", "wrong-password"),
])
def test_login_bad_credentials(client, email, password):
    assert register(client).status_code == 201
    response = submit(client, "/api/auth/login", {"email": email, "password": password})
    assert response.status_code == 401
    assert response.json["error"]["code"] == "INVALID_CREDENTIALS"
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("invalid", [
    {"display_name": "A", "email": "okay@example.test", "password": "LongValidPassphrase!234"},
    {"display_name": "Resident", "email": "missing-at", "password": "LongValidPassphrase!234"},
    {"display_name": "Resident", "email": "good@example.test", "password": "short"},
    {"display_name": "Resident", "email": "good@example.test", "password": "LongValidPassphrase!234", "phone": "not a phone"},
])
def test_registration_validation(client, invalid):
    response = submit(client, "/api/auth/register", invalid)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "VALIDATION_ERROR"


def test_rejects_client_supplied_role(client):
    response = submit(client, "/api/auth/register", {
        "display_name": "Resident", "email": "role@example.test",
        "password": "LongValidPassphrase!234", "role": "PLATFORM_ADMIN",
    })
    assert response.status_code == 400
    assert "role" in response.json["error"]["fields"]


def test_csrf_required_even_for_registration_and_login(client):
    assert client.post("/api/auth/register", json={}).status_code == 403
    assert client.post("/api/auth/login", json={}).status_code == 403
    assert client.post("/api/auth/login", json={}, headers={"X-CSRF-Token": "wrong"}).status_code == 403


def test_register_requires_json(client):
    response = client.post("/api/auth/register", data="hi", headers={"X-CSRF-Token": csrf(client)})
    assert response.status_code == 415


def test_suspended_user_cannot_login_or_access_me(client, app):
    assert register(client).status_code == 201
    assert submit(client, "/api/auth/login", {
        "email": "new.person@example.test", "password": "LongValidPassphrase!234",
    }).status_code == 200
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "new.person@example.test"))
        user.account_status = AccountStatus.SUSPENDED
        db.session.commit()
    assert client.get("/api/auth/me").status_code == 401
    assert submit(client, "/api/auth/login", {
        "email": "new.person@example.test", "password": "LongValidPassphrase!234",
    }).status_code == 401


def test_session_cookie_flags(client):
    response = client.get("/api/auth/csrf")
    cookies = response.headers.getlist("Set-Cookie")
    assert any("knowall_session=" in c for c in cookies)
    assert any("HttpOnly" in c and "SameSite=Lax" in c for c in cookies)
    assert response.headers["Cache-Control"] == "no-store"


def test_csrf_token_is_rotated_on_login(client):
    old_token = csrf(client)
    assert register(client).status_code == 201
    response = submit(client, "/api/auth/login", {
        "email": "new.person@example.test", "password": "LongValidPassphrase!234",
    })
    assert response.status_code == 200
    assert old_token != response.json["csrf_token"]


def test_existing_verified_account_response_remains_verified(client, app):
    with app.app_context():
        user = User(
            display_name="Seeded User", email="seed@example.test",
            password_hash=generate_password_hash("LongValidPassphrase!234"),
            email_verified_at=datetime.now(timezone.utc),
        )
        db.session.add(user)
        db.session.commit()
    response = submit(client, "/api/auth/login", {
        "email": "seed@example.test", "password": "LongValidPassphrase!234",
    })
    assert response.status_code == 200
    assert response.json["user"]["email_verified"] is True
