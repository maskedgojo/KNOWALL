"""Flask application factory for the shared KNOWALL API."""
import uuid

import hmac

from flask import Flask, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from .config import Config
from .extensions import db, login_manager, migrate


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL is missing. Configure backend/.env.")
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is missing. Generate one for backend/.env.")

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Import all identity tables, including member evidence requests, before migrations.
    from .modules.identity import models  # noqa: F401
    from .modules.notices import models as notice_models  # noqa: F401
    from .modules.discussions import models as discussion_models  # noqa: F401
    from .modules.suggestions import models as suggestion_models  # noqa: F401
    from .modules.polls import models as poll_models  # noqa: F401
    from .modules.disputes import models as dispute_models  # noqa: F401
    from .modules.proposals import models as proposal_models  # noqa: F401
    from .modules.operations import models as operations_models  # noqa: F401
    from .modules.locality import models as locality_models  # noqa: F401
    from .modules.identity.models import User
    from .modules.identity.auth import auth_bp
    from .modules.identity.auth.recovery_routes import recovery_bp
    from .modules.identity.auth.security import protect_api_writes
    from .modules.identity.auth.recovery import password_fingerprint
    from .modules.identity.residential import residential_bp, profile_bp
    from .modules.identity.onboarding import onboarding_bp, invitations_bp
    from .modules.identity.documents import documents_bp
    from .modules.identity.admin import admin_bp
    from .modules.identity.member_evidence import member_evidence_bp
    from .modules.identity.member_evidence.routes import register_cli
    from .modules.notices.routes import notices_bp
    from .modules.discussions.routes import discussions_bp
    from .modules.suggestions.routes import suggestions_bp
    from .modules.governance.history import history_bp
    from .modules.polls.routes import polls_bp
    from .modules.disputes.routes import disputes_bp
    from .modules.proposals.routes import proposals_bp
    from .modules.governance.activity import activity_bp
    from .modules.operations.facilities import facilities_bp
    from .modules.operations.events import events_bp
    from .modules.operations.maintenance import maintenance_bp
    from .modules.operations.development import development_bp
    from .modules.operations.dashboard import dashboard_bp
    from .modules.operations.photos import photos_bp
    from .modules.locality import locality_bp
    from .api_docs import api_docs_bp

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            identifier = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None
        user = db.session.get(User, identifier)
        if user is None:
            return None
        # Check live account status and password state each time Flask-Login
        # restores a session (including after another device resets password).
        db.session.refresh(user)
        fingerprint = session.get("_password_fingerprint")
        expected = password_fingerprint(user.password_hash)
        if not user.is_active or not isinstance(fingerprint, str):
            return None
        return user if hmac.compare_digest(fingerprint, expected) else None

    @login_manager.unauthorized_handler
    def unauthorized():
        return jsonify({
            "error": {"code": "AUTH_REQUIRED", "message": "Please sign in to continue."}
        }), 401

    app.before_request(protect_api_writes)
    app.register_blueprint(auth_bp)
    app.register_blueprint(recovery_bp)
    app.register_blueprint(residential_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(onboarding_bp)
    app.register_blueprint(invitations_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(member_evidence_bp)
    app.register_blueprint(notices_bp)
    app.register_blueprint(discussions_bp)
    app.register_blueprint(suggestions_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(polls_bp)
    app.register_blueprint(disputes_bp)
    app.register_blueprint(proposals_bp)
    app.register_blueprint(activity_bp)
    for blueprint in (facilities_bp, events_bp, maintenance_bp, development_bp, dashboard_bp, photos_bp):
        app.register_blueprint(blueprint)
    app.register_blueprint(locality_bp)
    register_cli(app)
    app.register_blueprint(api_docs_bp)

    @app.after_request
    def prevent_auth_response_caching(response):
        if request.path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def oversized_request(_exc):
        return jsonify({
            "error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request body is too large."}
        }), 413

    @app.get("/api/health")
    def health_check():
        return jsonify({"status": "ok", "service": "knowall-api"}), 200

    return app
