"""Small CSRF guard for same-origin, cookie-authenticated Flask JSON APIs.

This uses Flask's signed, HTTP-only session cookie and a random, per-session
header token. No browser localStorage, Redis, or new table is required.
"""
import hmac
import secrets

from flask import jsonify, request, session


def ensure_csrf_token() -> str:
    token = session.get("_csrf_token")
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def protect_api_writes():
    if not request.path.startswith("/api/"):
        return None
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    expected = session.get("_csrf_token")
    submitted = request.headers.get("X-CSRF-Token", "")
    if (not isinstance(expected, str) or not isinstance(submitted, str)
            or not expected or not hmac.compare_digest(expected, submitted)):
        return jsonify({
            "error": {
                "code": "CSRF_REQUIRED",
                "message": "Request a CSRF token from GET /api/auth/csrf and send it in X-CSRF-Token.",
            }
        }), 403
    return None
