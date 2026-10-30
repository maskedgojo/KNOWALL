"""Phase 2B model tests; SQLite is only used for isolated unit tests."""
import hashlib
from datetime import date, datetime, timedelta, timezone

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.modules.identity.models import (
    ApplicationReview, ApplicationStatus, DocumentType, Flat, Household,
    Invitation, Membership, MembershipApplication, OCRResult, OCRStatus,
    ResidentCategory, ReviewDecision, Tower, User, VerificationDocument,
)


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def fixture_data():
    admin = User(display_name="Admin", email="admin@example.com", password_hash="fixture")
    applicant = User(display_name="Rahul", email="rahul@example.com", password_hash="fixture")
    family = User(display_name="Priya", email="priya@example.com", password_hash="fixture")
    tower = Tower(name="B")
    flat = Flat(tower=tower, flat_number="402", floor_number=4)
    household = Household(flat=flat, label="Owner household")
    db.session.add_all([admin, applicant, family, household])
    db.session.flush()
    return admin, applicant, family, flat, household


def test_owner_application_and_multiple_ocr_runs_and_review(app):
    with app.app_context():
        admin, applicant, _, flat, home = fixture_data()
        application = MembershipApplication(
            user=applicant, flat=flat, household=home,
            category=ResidentCategory.OWNER, status=ApplicationStatus.PENDING,
        )
        document = VerificationDocument(
            application=application, uploaded_by=applicant,
            document_type=DocumentType.OCCUPANCY_LETTER,
            original_filename="fictional_letter.pdf", storage_key="private/abc.pdf",
            mime_type="application/pdf", file_size_bytes=45000,
            sha256_checksum="a" * 64,
        )
        good_ocr = OCRResult(
            document=document, status=OCRStatus.COMPLETED,
            extracted_text="Rahul B-402", extracted_fields={"flat": "B-402"},
            comparison_results={"flat": "MATCH"}, warnings=[],
        )
        retry = OCRResult(document=document, status=OCRStatus.FAILED, error_message="Unreadable scan")
        review = ApplicationReview(
            application=application, reviewer=admin,
            decision=ReviewDecision.NEEDS_CORRECTION, reason="Upload a clearer copy",
        )
        db.session.add_all([application, document, good_ocr, retry, review])
        db.session.commit()
        assert len(application.documents) == 1
        assert len(document.ocr_results) == 2
        assert good_ocr.extracted_fields["flat"] == "B-402"
        assert application.reviews[0].reviewer.email == "admin@example.com"


def test_duplicate_open_application_but_rejected_can_resubmit(app):
    with app.app_context():
        _, applicant, _, flat, home = fixture_data()
        first = MembershipApplication(
            user=applicant, flat=flat, household=home,
            category=ResidentCategory.OWNER, status=ApplicationStatus.PENDING,
        )
        db.session.add(first)
        db.session.commit()
        second = MembershipApplication(
            user=applicant, flat=flat, household=home,
            category=ResidentCategory.OWNER, status=ApplicationStatus.DRAFT,
        )
        db.session.add(second)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        first.status = ApplicationStatus.REJECTED
        db.session.commit()
        db.session.add(MembershipApplication(
            user=applicant, flat=flat, household=home,
            category=ResidentCategory.OWNER, status=ApplicationStatus.DRAFT,
        ))
        db.session.commit()


def test_family_sponsor_required_when_submitted(app):
    with app.app_context():
        _, applicant, family, flat, home = fixture_data()
        owner = Membership(
            user=applicant, household=home, category=ResidentCategory.OWNER,
            valid_from=date(2026, 10, 22),
        )
        db.session.add(owner)
        db.session.flush()
        draft = MembershipApplication(
            user=family, flat=flat, household=home,
            category=ResidentCategory.FAMILY_MEMBER,
            status=ApplicationStatus.DRAFT,
        )
        db.session.add(draft)
        db.session.commit()
        draft.status = ApplicationStatus.PENDING
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        draft.sponsor = owner
        draft.status = ApplicationStatus.PENDING
        db.session.commit()


def test_invitation_is_single_use_per_application(app):
    with app.app_context():
        admin, applicant, family, flat, home = fixture_data()
        invitation = Invitation(
            flat=flat, household=home, invited_by=admin,
            invited_email="RAHUL@EXAMPLE.COM",
            token_hash=hashlib.sha256(b"sample-one-use-token").hexdigest(),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db.session.add(invitation)
        db.session.flush()
        assert invitation.invited_email == "rahul@example.com"
        db.session.add(MembershipApplication(
            user=applicant, flat=flat, household=home,
            invitation=invitation, category=ResidentCategory.OWNER,
        ))
        db.session.commit()
        db.session.add(MembershipApplication(
            user=family, flat=flat, household=home,
            invitation=invitation, category=ResidentCategory.OWNER,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_invalid_document_size_rejected(app):
    with app.app_context():
        _, applicant, _, flat, home = fixture_data()
        application = MembershipApplication(user=applicant, flat=flat, household=home,
                                            category=ResidentCategory.OWNER)
        db.session.add(VerificationDocument(
            application=application, uploaded_by=applicant,
            document_type=DocumentType.OCCUPANCY_LETTER,
            original_filename="too-large.pdf", storage_key="private/large.pdf",
            mime_type="application/pdf", file_size_bytes=6 * 1024 * 1024,
            sha256_checksum="a" * 64,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_rejection_or_correction_requires_reason(app):
    with app.app_context():
        admin, applicant, _, flat, home = fixture_data()
        application = MembershipApplication(user=applicant, flat=flat, household=home,
                                            category=ResidentCategory.OWNER)
        db.session.add(ApplicationReview(
            application=application, reviewer=admin,
            decision=ReviewDecision.REJECTED,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
