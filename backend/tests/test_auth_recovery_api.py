"""Phase 4B: isolated HTTP tests, using in-memory email delivery only."""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse
import hashlib

import pytest
from sqlalchemy import select

from app import create_app
from app.extensions import db
from app.modules.identity.models import AuthToken, AuthTokenPurpose, User
from app.modules.identity.models.user import utc_now


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "non-production-phase-4b-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
        "MAIL_DELIVERY_MODE": "memory",
        "FRONTEND_BASE_URL": "http://localhost:3000",
    })
    # Keep application contexts scoped: a permanently open context can cache
    # Flask-Login's current_user across independent HTTP requests.
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def post(client, route, body):
    return client.post(route, json=body, headers={"X-CSRF-Token": csrf(client)})


def register(client):
    return post(client, "/api/auth/register", {
        "display_name": "Example Resident", "email": "demo@example.test",
        "password": "OriginalPassword123!",
    })


def mail_token(app, *, index=-1):
    message = app.extensions["knowall_outbox"][index]
    url = next(part for part in message["body"].split() if "?token=" in part)
    return parse_qs(urlparse(url).query)["token"][0]


def test_registration_sends_verification_link_but_does_not_verify_automatically(client, app):
    response = register(client)
    assert response.status_code == 201
    assert response.json["user"]["email_verified"] is False
    assert len(app.extensions["knowall_outbox"]) == 1
    assert "verify-email?token=" in app.extensions["knowall_outbox"][0]["body"]
    token = mail_token(app)
    with app.app_context():
        record = db.session.scalar(select(AuthToken))
        assert record.purpose == AuthTokenPurpose.EMAIL_VERIFICATION
        assert record.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token != record.token_hash
        assert "OriginalPassword123!" not in str(record.__dict__)


def test_email_verification_consumes_token_once(client, app):
    register(client)
    token = mail_token(app)
    response = post(client, "/api/auth/verify-email", {"token": token})
    assert response.status_code == 200
    assert post(client, "/api/auth/verify-email", {"token": token}).status_code == 400
    with app.app_context():
        user = db.session.scalar(select(User).where(User.email == "demo@example.test"))
        assert user.email_verified_at is not None
        assert db.session.scalar(select(AuthToken)).used_at is not None


def test_resend_is_generic_and_old_verification_token_is_revoked(client, app):
    register(client)
    old = mail_token(app)
    response = post(client, "/api/auth/verification/resend", {"email": "UNKNOWN@example.test"})
    assert response.status_code == 202
    original_count = len(app.extensions["knowall_outbox"])
    response = post(client, "/api/auth/verification/resend", {"email": "demo@example.test"})
    assert response.status_code == 202
    assert len(app.extensions["knowall_outbox"]) == original_count  # cooldown
    with app.app_context():
        token = db.session.scalar(select(AuthToken))
        token.created_at = utc_now() - timedelta(minutes=5)
        db.session.commit()
    assert post(client, "/api/auth/verification/resend", {"email": "demo@example.test"}).status_code == 202
    assert len(app.extensions["knowall_outbox"]) == original_count + 1
    assert post(client, "/api/auth/verify-email", {"token": old}).status_code == 400
    assert post(client, "/api/auth/verify-email", {"token": mail_token(app)}).status_code == 200
    assert post(client, "/api/auth/verification/resend", {"email": "demo@example.test"}).status_code == 202
    assert len(app.extensions["knowall_outbox"]) == original_count + 1


def test_forgot_password_unknown_and_known_account_have_same_response(client, app):
    register(client)
    one = post(client, "/api/auth/password/forgot", {"email": "someone-else@example.test"})
    two = post(client, "/api/auth/password/forgot", {"email": "demo@example.test"})
    assert one.status_code == two.status_code == 202
    assert one.json == two.json
    assert len(app.extensions["knowall_outbox"]) == 2  # initial verification + one reset
    assert "reset-password?token=" in app.extensions["knowall_outbox"][-1]["body"]


def test_password_reset_invalidates_existing_session_across_clients(client, app):
    register(client)
    login = post(client, "/api/auth/login", {
        "email": "demo@example.test", "password": "OriginalPassword123!",
    })
    assert login.status_code == 200
    assert client.get("/api/auth/me").status_code == 200

    reset_client = app.test_client()
    assert post(reset_client, "/api/auth/password/forgot", {"email": "demo@example.test"}).status_code == 202
    token = mail_token(app)
    result = post(reset_client, "/api/auth/password/reset", {
        "token": token, "new_password": "NewStrongPassword789!",
    })
    assert result.status_code == 200
    assert "csrf_token" in result.json
    assert reset_client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").status_code == 401
    assert post(client, "/api/auth/login", {
        "email": "demo@example.test", "password": "OriginalPassword123!",
    }).status_code == 401
    assert post(client, "/api/auth/login", {
        "email": "demo@example.test", "password": "NewStrongPassword789!",
    }).status_code == 200
    assert post(reset_client, "/api/auth/password/reset", {
        "token": token, "new_password": "AnotherStrongPassword678!",
    }).status_code == 400


def test_invalid_expired_token_rejected(client, app):
    register(client)
    token = mail_token(app)
    with app.app_context():
        record = db.session.scalar(select(AuthToken))
        record.created_at = utc_now() - timedelta(days=3)
        record.expires_at = utc_now() - timedelta(days=2)
        db.session.commit()
    bad = post(client, "/api/auth/verify-email", {"token": token})
    assert bad.status_code == 400
    assert bad.json["error"]["code"] == "INVALID_OR_EXPIRED_TOKEN"
    assert post(client, "/api/auth/password/reset", {
        "token": "not-an-authentication-token", "new_password": "ValidPassword12345!",
    }).status_code == 400


def test_password_reuse_does_not_consume_token(client, app):
    register(client)
    post(client, "/api/auth/password/forgot", {"email": "demo@example.test"})
    token = mail_token(app)
    same = post(client, "/api/auth/password/reset", {
        "token": token, "new_password": "OriginalPassword123!",
    })
    assert same.status_code == 400
    assert same.json["error"]["code"] == "PASSWORD_REUSE_NOT_ALLOWED"
    assert post(client, "/api/auth/password/reset", {
        "token": token, "new_password": "ChangedPassword12345!",
    }).status_code == 200


@pytest.mark.parametrize("endpoint,payload", [
    ("/api/auth/verification/resend", {"email": "x"}),
    ("/api/auth/password/forgot", {"email": "x"}),
    ("/api/auth/verify-email", {"token": ""}),
    ("/api/auth/password/reset", {"token": "t", "new_password": "short"}),
])
def test_invalid_payloads(client, endpoint, payload):
    response = post(client, endpoint, payload)
    assert response.status_code == 400


@pytest.mark.parametrize("endpoint", [
    "/api/auth/verification/resend", "/api/auth/verify-email",
    "/api/auth/password/forgot", "/api/auth/password/reset",
])
def test_csrf_mandatory(client, endpoint):
    assert client.post(endpoint, json={}).status_code == 403


def test_ip_rate_limit_is_enforced_without_redis(client):
    for _ in range(12):
        assert post(client, "/api/auth/password/forgot", {"email": "missing@example.test"}).status_code == 202
    response = post(client, "/api/auth/password/forgot", {"email": "missing@example.test"})
    assert response.status_code == 429
    assert response.json["error"]["code"] == "RATE_LIMITED"


def test_reset_password_requires_active_account(client, app):
    from app.modules.identity.models import AccountStatus
    register(client)
    post(client, "/api/auth/password/forgot", {"email": "demo@example.test"})
    token = mail_token(app)
    with app.app_context():
        account = db.session.scalar(select(User).where(User.email == "demo@example.test"))
        account.account_status = AccountStatus.SUSPENDED
        db.session.commit()
    response = post(client, "/api/auth/password/reset", {
        "token": token, "new_password": "ChangedPassword12345!",
    })
    assert response.status_code == 400


def test_failed_delivery_does_not_block_registration_and_allows_resend(client, app, monkeypatch):
    from app.modules.identity.auth import recovery
    def fail(**kwargs):
        raise OSError("delivery offline")
    monkeypatch.setattr(recovery, "deliver_auth_email", fail)
    assert register(client).status_code == 201
    with app.app_context():
        token = db.session.scalar(select(AuthToken))
        assert token.revoked_at is not None
    monkeypatch.undo()
    response = post(client, "/api/auth/verification/resend", {"email": "demo@example.test"})
    assert response.status_code == 202
    assert len(app.extensions["knowall_outbox"]) == 1
