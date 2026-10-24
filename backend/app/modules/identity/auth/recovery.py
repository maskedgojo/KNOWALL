"""One-time auth token management and basic abuse prevention.

Token creation/consumption is persisted in PostgreSQL; IP rate limiting is
process-local (adequate for one-server V1, not a cluster-wide guarantee).
"""
import hashlib
import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
import token
from urllib.parse import quote

from flask import current_app, request
from sqlalchemy import select, update

from app.extensions import db
from app.modules.identity.models import AuthToken, AuthTokenPurpose
from app.modules.identity.models.user import utc_now
from .mailer import deliver_auth_email


def password_fingerprint(password_hash: str) -> str:
    """Bind signed client sessions to current password state, with no schema change.

    The cookie contains an HMAC, never the database password hash itself.
    """
    key = current_app.secret_key.encode("utf-8")
    return hmac.new(key, password_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def as_utc(value: datetime) -> datetime:
    """SQLite test DB strips tzinfo; PostgreSQL returns aware datetimes."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def rate_limited(action: str) -> bool:
    """Bounded, in-memory per-IP window. No Redis requirement for this MVP."""
    limiter = current_app.extensions.setdefault("knowall_recovery_limiter", {
        "lock": threading.Lock(), "events": {},
    })
    key = (action, request.remote_addr or "unknown")
    now = time.monotonic()
    window = int(current_app.config["RECOVERY_IP_WINDOW_SECONDS"])
    limit = int(current_app.config["RECOVERY_IP_LIMIT"])
    with limiter["lock"]:
        events = limiter["events"]
        if len(events) > 1500:
            # Remove stale entries to cap memory; no persistent store.
            for item in list(events):
                events[item] = [t for t in events[item] if t > now - window]
                if not events[item]:
                    del events[item]
        recent = [t for t in events.get(key, []) if t > now - window]
        if len(recent) >= limit:
            events[key] = recent
            return True
        recent.append(now)
        events[key] = recent
        return False


def may_issue_again(user_id, purpose: AuthTokenPurpose) -> bool:
    last = db.session.scalar(
        select(AuthToken.created_at)
        .where(AuthToken.user_id == user_id, AuthToken.purpose == purpose,
               AuthToken.used_at.is_(None), AuthToken.revoked_at.is_(None))
        .order_by(AuthToken.created_at.desc()).limit(1)
    )
    if last is None:
        return True
    elapsed = (utc_now() - as_utc(last)).total_seconds()
    return elapsed >= int(current_app.config["RECOVERY_RESEND_COOLDOWN_SECONDS"])


def create_one_time_token(user, purpose: AuthTokenPurpose):
    now = utc_now()
    db.session.execute(
        update(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
        ).values(revoked_at=now)
    )
    raw = secrets.token_urlsafe(32)
    ttl_minutes = (current_app.config["EMAIL_VERIFICATION_TTL_MINUTES"]
                   if purpose == AuthTokenPurpose.EMAIL_VERIFICATION
                   else current_app.config["PASSWORD_RESET_TTL_MINUTES"])
    token = AuthToken(
        user_id=user.id, purpose=purpose, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        created_at=now, expires_at=now + timedelta(minutes=int(ttl_minutes)),
    )
    db.session.add(token)
    return raw, token


def claim_token(raw: str, purpose: AuthTokenPurpose):
    """Atomically claim an unexpired token. Caller must commit after business change."""
    if not isinstance(raw, str) or not 20 <= len(raw) <= 300:
        return None
    try:
        raw.encode("ascii")
    except UnicodeEncodeError:
        return None
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    token = db.session.scalar(
        select(AuthToken).where(AuthToken.token_hash == token_hash,
                                AuthToken.purpose == purpose)
    )
    if token is None:
        return None
    now = utc_now()
    if token.used_at is not None or token.revoked_at is not None or as_utc(token.expires_at) <= now:
        return None
    
    result = db.session.execute(
        update(AuthToken)
        .where(
            AuthToken.id == token.id,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
            AuthToken.expires_at > now,
        )
        .values(used_at=now)
        .execution_options(synchronize_session="fetch")
    )

    if result.rowcount != 1:
        return None
    return token


def dispatch_link(user, raw: str, purpose: AuthTokenPurpose) -> None:
    base = current_app.config["FRONTEND_BASE_URL"].rstrip("/")
    path = "/verify-email" if purpose == AuthTokenPurpose.EMAIL_VERIFICATION else "/reset-password"
    link = f"{base}{path}?token={quote(raw, safe='')}"
    if purpose == AuthTokenPurpose.EMAIL_VERIFICATION:
        subject = "Verify your KNOWALL email"
        message = ("Verify the email address for your KNOWALL account using this one-time link:\n"
                   f"{link}\n\nIf you did not sign up, you can ignore this email.\n")
    else:
        subject = "Reset your KNOWALL password"
        message = ("You can reset your KNOWALL account password using this one-time link:\n"
                   f"{link}\n\nIf you did not request a reset, ignore this email.\n")
    deliver_auth_email(to_address=user.email, subject=subject, body=message)


def revoke_undelivered_token(token_id) -> None:
    """Allow an immediate resend after a delivery error."""
    db.session.execute(update(AuthToken).where(
        AuthToken.id == token_id,
        AuthToken.used_at.is_(None), AuthToken.revoked_at.is_(None),
    ).values(revoked_at=utc_now()))
    db.session.commit()


def issue_registration_verification(user) -> None:
    """Registration is successful even if SMTP is unavailable; resend is possible."""
    raw, token = create_one_time_token(user, AuthTokenPurpose.EMAIL_VERIFICATION)
    db.session.commit()
    try:
        dispatch_link(user, raw, AuthTokenPurpose.EMAIL_VERIFICATION)
    except Exception:
        current_app.logger.exception("KNOWALL verification email delivery failed")
        revoke_undelivered_token(token.id)
