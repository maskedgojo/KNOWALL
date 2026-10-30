"""Phase 4B API endpoints: verification, resend, forgot and reset password."""
from flask import Blueprint, current_app, jsonify, session
from flask_login import logout_user
from sqlalchemy import select, update
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, AuditLog, AuthToken, AuthTokenPurpose, User,
)
from app.modules.identity.models.user import utc_now
from .recovery import (
    claim_token, create_one_time_token, dispatch_link, may_issue_again,
    rate_limited, revoke_undelivered_token,
)
from .routes import error, json_object, EMAIL_PATTERN
from .security import ensure_csrf_token

recovery_bp = Blueprint("recovery", __name__, url_prefix="/api/auth")
GENERIC_RESPONSE = {"message": "If the account is eligible, an email will be sent shortly."}


def _normalized_email(body):
    email = body.get("email")
    value = email.strip().lower() if isinstance(email, str) else ""
    if not value or len(value) > 255 or not EMAIL_PATTERN.fullmatch(value):
        return None
    return value


def _request_email(purpose: AuthTokenPurpose):
    body, failure = json_object({"email"})
    if failure:
        return failure
    normalized = _normalized_email(body)
    if normalized is None:
        return error("VALIDATION_ERROR", "Enter a valid email address.", 400,
                     fields={"email": "Invalid email address."})
    # Rate limit by IP, separately from one-token-per-account cooldown.
    # Do not reveal which addresses exist or whether they are verified.
    if rate_limited(purpose.value):
        return error("RATE_LIMITED", "Too many requests. Try again later.", 429)

    user = db.session.scalar(select(User).where(User.email == normalized))
    eligible = (
        user is not None and user.account_status == AccountStatus.ACTIVE and
        (purpose != AuthTokenPurpose.EMAIL_VERIFICATION or user.email_verified_at is None)
    )
    if eligible and may_issue_again(user.id, purpose):
        raw, token = create_one_time_token(user, purpose)
        db.session.commit()
        try:
            dispatch_link(user, raw, purpose)
        except Exception:
            current_app.logger.exception("KNOWALL account email delivery failed")
            revoke_undelivered_token(token.id)
    return jsonify(GENERIC_RESPONSE), 202


@recovery_bp.post("/verification/resend")
def resend_verification():
    return _request_email(AuthTokenPurpose.EMAIL_VERIFICATION)


@recovery_bp.post("/verify-email")
def verify_email():
    body, failure = json_object({"token"})
    if failure:
        return failure
    token = claim_token(body.get("token"), AuthTokenPurpose.EMAIL_VERIFICATION)
    if token is None:
        db.session.rollback()
        return error("INVALID_OR_EXPIRED_TOKEN", "The verification link is invalid or expired.", 400)
    user = db.session.get(User, token.user_id)
    if user is None or user.account_status != AccountStatus.ACTIVE or user.email_verified_at is not None:
        db.session.rollback()
        return error("INVALID_OR_EXPIRED_TOKEN", "The verification link is invalid or expired.", 400)
    now = utc_now()
    user.email_verified_at = now
    db.session.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFICATION,
        AuthToken.id != token.id,
        AuthToken.used_at.is_(None),
        AuthToken.revoked_at.is_(None),
    ).values(revoked_at=now))
    db.session.add(AuditLog(actor=user, action="EMAIL_VERIFIED", entity_type="USER",
                            entity_id=user.id, details=None))
    db.session.commit()
    return jsonify({"message": "Email verified successfully."}), 200


@recovery_bp.post("/password/forgot")
def forgot_password():
    return _request_email(AuthTokenPurpose.PASSWORD_RESET)


@recovery_bp.post("/password/reset")
def reset_password():
    body, failure = json_object({"token", "new_password"})
    if failure:
        return failure
    new_password = body.get("new_password")
    if not isinstance(new_password, str) or not 12 <= len(new_password) <= 128:
        return error("VALIDATION_ERROR", "Password must contain 12 to 128 characters.", 400,
                     fields={"new_password": "Use 12 to 128 characters."})
    token = claim_token(body.get("token"), AuthTokenPurpose.PASSWORD_RESET)
    if token is None:
        db.session.rollback()
        return error("INVALID_OR_EXPIRED_TOKEN", "The reset link is invalid or expired.", 400)
    user = db.session.get(User, token.user_id)
    if user is None or user.account_status != AccountStatus.ACTIVE:
        db.session.rollback()
        return error("INVALID_OR_EXPIRED_TOKEN", "The reset link is invalid or expired.", 400)
    if check_password_hash(user.password_hash, new_password):
        db.session.rollback()
        return error("PASSWORD_REUSE_NOT_ALLOWED", "Choose a different password.", 400)
    now = utc_now()
    user.password_hash = generate_password_hash(new_password)
    db.session.execute(update(AuthToken).where(
        AuthToken.user_id == user.id,
        AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
        AuthToken.id != token.id,
        AuthToken.used_at.is_(None), AuthToken.revoked_at.is_(None),
    ).values(revoked_at=now))
    db.session.add(AuditLog(actor=user, action="PASSWORD_RESET", entity_type="USER",
                            entity_id=user.id, details=None))
    db.session.commit()
    # Changing password_hash makes fingerprint checks invalidate ALL existing
    # signed Flask sessions on their next request; current client is logged out.
    logout_user()
    session.clear()
    return jsonify({"message": "Password reset successfully. Please sign in again.",
                    "csrf_token": ensure_csrf_token()}), 200
