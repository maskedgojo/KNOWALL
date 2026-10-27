"""Shared Module 2 scaffolding. Does not migrate the project database."""
import pytest

from app import create_app
from app.extensions import db
from app.modules.governance.features import FEATURES, UNIMPLEMENTED_API_PREFIXES
from app.modules.governance.scope import configured_society
from app.modules.identity.access.permissions import KNOWN_PERMISSIONS
from app.modules.identity.models import SocietyProfile

NOTICE_PERMISSIONS = {"society.notices.read", "society.notices.manage"}


@pytest.fixture()
def app():
    instance = create_app({
        "TESTING": True,
        "SECRET_KEY": "module2-scaffold-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False,
        "MAIL_DELIVERY_MODE": "memory",
    })
    with instance.app_context():
        db.create_all()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.drop_all()


def test_configured_society_uses_only_the_singleton(app):
    with app.app_context():
        assert configured_society() is None
        db.session.add(SocietyProfile(
            id=1, name="Green Valley Residency", address="1 Main Road",
            locality="Green Valley", city="Bhubaneswar",
        ))
        db.session.commit()
        profile = configured_society()
        assert profile is not None and profile.id == 1


def test_feature_catalog_does_not_mark_unbuilt_work_complete():
    assert FEATURES["notices"]["status"] == "in_progress"
    assert FEATURES["discussions"]["status"] == "in_progress"
    assert FEATURES["suggestions"]["status"] == "in_progress"
    assert FEATURES["transparency"]["status"] == "in_progress"
    assert FEATURES["polls"]["status"] == "in_progress"
    assert FEATURES["disputes"]["status"] == "in_progress"
    assert FEATURES["proposals"]["status"] == "in_progress"
    assert FEATURES["polls"]["blockers"]
    assert FEATURES["disputes"]["blockers"]
    assert FEATURES["proposals"]["blockers"]
    assert "complete" not in {item["status"] for item in FEATURES.values()}


def test_scaffold_adds_no_permissions_or_feature_routes(app):
    assert NOTICE_PERMISSIONS <= KNOWN_PERMISSIONS
    society_codes = {code for code in KNOWN_PERMISSIONS if code.startswith("society.")}
    assert society_codes <= NOTICE_PERMISSIONS | {
        "society.maintenance.create", "society.facilities.book",
    }
    paths = {rule.rule for rule in app.url_map.iter_rules()}
    for prefix in UNIMPLEMENTED_API_PREFIXES:
        assert not any(path == prefix or path.startswith(prefix + "/") for path in paths)
