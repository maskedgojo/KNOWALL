"""Phase 4A endpoints: register, login, logout, current user and CSRF token."""
import re

from flask import Blueprint, jsonify, request, session
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.modules.identity.models import AccountStatus, AuditLog, PermissionRole, RoleAssignment, User
from .security import ensure_csrf_token
from .recovery import password_fingerprint, issue_registration_verification


auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_PATTERN = re.compile(r"^\+?[0-9]{7,15}$")


def error(code: str, message: str, status: int, *, fields: dict | None = None):
    body: dict = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return jsonify(body), status


def json_object(allowed: set[str]):
    if not request.is_json:
        return None, error("UNSUPPORTED_MEDIA_TYPE", "Send a JSON object.", 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None, error("VALIDATION_ERROR", "A JSON object is required.", 400)
    unknown = sorted(set(body) - allowed)
    if unknown:
        return None, error(
            "VALIDATION_ERROR", "Unexpected fields are not accepted.", 400,
            fields={field: "Unknown field." for field in unknown},
        )
    return body, None


def public_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "phone": user.phone,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "occupation": user.occupation,
        "email_verified": user.email_verified_at is not None,
        "account_status": user.account_status.value,
    }


@auth_bp.get("/csrf")
def get_csrf():
    return jsonify({"csrf_token": ensure_csrf_token()}), 200


@auth_bp.post("/register")
def register():
    body, failure = json_object({"display_name", "email", "password", "phone"})
    if failure:
        return failure

    problems = {}
    name = body.get("display_name")
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 120:
        problems["display_name"] = "Must contain 2 to 120 characters."

    email = body.get("email")
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    if len(normalized_email) > 255 or not EMAIL_PATTERN.fullmatch(normalized_email):
        problems["email"] = "Enter a valid email address."

    password = body.get("password")
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        problems["password"] = "Password must contain 12 to 128 characters."

    phone = body.get("phone")
    if phone is not None and (
        not isinstance(phone, str) or not PHONE_PATTERN.fullmatch(phone.strip())
    ):
        problems["phone"] = "Use 7 to 15 digits, optionally starting with +."

    if problems:
        return error("VALIDATION_ERROR", "Check the submitted fields.", 400, fields=problems)

    if db.session.scalar(select(User.id).where(User.email == normalized_email)) is not None:
        return error("EMAIL_ALREADY_REGISTERED", "This email is already registered.", 409)

    user = User(
        display_name=name.strip(), email=normalized_email,
        password_hash=generate_password_hash(password),
        phone=phone.strip() if phone is not None else None,
        account_status=AccountStatus.ACTIVE,
        # Unverified until Phase 4B email-verification flow completes.
        email_verified_at=None,
    )
    try:
        db.session.add(user)
        db.session.flush()  # Assign ID before attaching the applicant role.
        db.session.add(RoleAssignment(user=user, role=PermissionRole.APPLICANT))
        db.session.add(AuditLog(
            actor=user, action="ACCOUNT_REGISTERED", entity_type="USER", entity_id=user.id,
            details={"source": "self_registration"},
        ))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # Concurrent requests trying the same email must not create duplicates.
        return error("EMAIL_ALREADY_REGISTERED", "This email is already registered.", 409)

    # Send a one-time verification email. Account creation is retained even
    # when SMTP is temporarily unavailable; the user may request a resend.
    issue_registration_verification(user)
    return jsonify({
        "message": "Account created. Check your email for a verification link.",
        "user": public_user(user),
    }), 201


@auth_bp.post("/login")
def login():
    body, failure = json_object({"email", "password"})
    if failure:
        return failure
    email = body.get("email")
    password = body.get("password")
    normalized_email = email.strip().lower() if isinstance(email, str) else ""
    if not normalized_email or len(normalized_email) > 255 or not isinstance(password, str):
        return error("VALIDATION_ERROR", "Email and password are required.", 400)

    user = db.session.scalar(select(User).where(User.email == normalized_email))
    if user is None or not check_password_hash(user.password_hash, password) or not user.is_active:
        return error("INVALID_CREDENTIALS", "Invalid email or password.", 401)

    # Replace pre-login session state and rotate CSRF after authentication.
    session.clear()
    if not login_user(user, remember=False, fresh=True):
        return error("LOGIN_FAILED", "Unable to start a session.", 401)
    session.permanent = True
    session["_password_fingerprint"] = password_fingerprint(user.password_hash)
    csrf = ensure_csrf_token()
    return jsonify({"user": public_user(user), "csrf_token": csrf}), 200


@auth_bp.get("/me")
@login_required
def me():
    return jsonify({"user": public_user(current_user)}), 200


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    # A fresh guest CSRF token allows signing in again without a page reload.
    return jsonify({"message": "Logged out.", "csrf_token": ensure_csrf_token()}), 200
