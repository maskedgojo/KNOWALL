"""KNOWALL runtime configuration (single-society Flask API)."""
import os
from pathlib import Path
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # Must not live under frontend/public or Flask static.
    OCR_PRIVATE_DIR = os.getenv("OCR_PRIVATE_DIR", str(Path(__file__).resolve().parents[1] / "private_uploads"))

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    SESSION_COOKIE_NAME = "knowall_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # False ONLY for local HTTP development. Set COOKIE_SECURE=true behind HTTPS.
    SESSION_COOKIE_SECURE = env_bool("COOKIE_SECURE")
    SESSION_COOKIE_DOMAIN = None  # Host-only: don't share with arbitrary subdomains.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    SESSION_REFRESH_EACH_REQUEST = False
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # Global safety ceiling; Phase 7 adds per-document limits.

    # Phase 4B email verification & account recovery.
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")
    MAIL_DELIVERY_MODE = os.getenv("MAIL_DELIVERY_MODE", "console")
    MAIL_FROM = os.getenv("MAIL_FROM", "noreply@knowall.local")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls")
    EMAIL_VERIFICATION_TTL_MINUTES = 24 * 60
    PASSWORD_RESET_TTL_MINUTES = 30
    RECOVERY_RESEND_COOLDOWN_SECONDS = 60
    RECOVERY_IP_LIMIT = 12
    RECOVERY_IP_WINDOW_SECONDS = 15 * 60
