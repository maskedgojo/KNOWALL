"""Phase 7 API tests use synthetic evidence and mocked OCR inference only."""
import io
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.modules.identity.models import (
    AccountStatus, ApplicationStatus, DocumentType, Flat,
    MembershipApplication, OCRResult, OCRStatus, PermissionRole,
    ResidentCategory, RoleAssignment, Tower, User, VerificationDocument,
)

PASS = "ValidPasswordForTests2026!"


@pytest.fixture()
def app(tmp_path):
    instance = create_app({
        "TESTING": True, "SECRET_KEY": "phase7-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite+pysqlite:///:memory:",
        "SESSION_COOKIE_SECURE": False, "MAIL_DELIVERY_MODE": "memory",
        "OCR_PRIVATE_DIR": str(tmp_path / "private_uploads"),
    })
    with instance.app_context():
        db.create_all()
    yield instance
    with instance.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def ids(app):
    with app.app_context():
        tower = Tower(name="B")
        db.session.add(tower)
        db.session.flush()
        flat = Flat(tower=tower, flat_number="402", floor_number=4)
        db.session.add(flat)
        db.session.flush()
        users = []
        for name, email in [("Rahul Sharma", "rahul@example.test"), ("Other Resident", "other@example.test")]:
            user = User(display_name=name, email=email,
                        password_hash=generate_password_hash(PASS),
                        email_verified_at=datetime.now(timezone.utc),
                        account_status=AccountStatus.ACTIVE)
            db.session.add(user)
            db.session.flush()
            db.session.add(RoleAssignment(user_id=user.id, role=PermissionRole.APPLICANT))
            users.append(user)
        application = MembershipApplication(
            user_id=users[0].id, flat_id=flat.id,
            category=ResidentCategory.OWNER, status=ApplicationStatus.PENDING,
        )
        db.session.add(application)
        db.session.commit()
        return {"app": str(application.id), "app_uuid": application.id}


def token(client):
    return client.get("/api/auth/csrf").json["csrf_token"]


def login(client, email="rahul@example.test"):
    response = client.post("/api/auth/login", json={"email": email, "password": PASS},
                           headers={"X-CSRF-Token": token(client)})
    assert response.status_code == 200, response.json


def picture():
    out = io.BytesIO()
    Image.new("RGB", (320, 240), "white").save(out, format="PNG")
    return out.getvalue()


def upload(client, ids, *, content=None, filename="sample.png", kind="OCCUPANCY_LETTER"):
    content = picture() if content is None else content
    return client.post("/api/documents/upload", data={
        "application_id": ids["app"], "document_type": kind,
        "file": (io.BytesIO(content), filename),
    }, content_type="multipart/form-data", headers={"X-CSRF-Token": token(client)})


def ocr(client, document_id):
    return client.post(f"/api/documents/{document_id}/ocr", headers={"X-CSRF-Token": token(client)})


def uploaded(client, ids):
    response = upload(client, ids)
    assert response.status_code == 201, response.json
    return response.json["document"]["id"]


def test_requires_authentication(client, ids):
    assert upload(client, ids).status_code == 401


def test_upload_rejects_invalid_bytes(client, ids):
    login(client)
    assert upload(client, ids, content=b"not a png").status_code == 400


def test_upload_rejects_unsupported_extension(client, ids):
    login(client)
    assert upload(client, ids, filename="attack.html").status_code == 400


def test_upload_rejects_oversized_blob(client, ids):
    login(client)
    assert upload(client, ids, content=b"x" * (5 * 1024 * 1024 + 1)).status_code == 400


def test_upload_privately_and_download(client, ids, app):
    login(client)
    document_id = uploaded(client, ids)
    detail = client.get(f"/api/documents/{document_id}")
    assert detail.status_code == 200
    assert "storage_key" not in detail.json["document"]
    download = client.get(f"/api/documents/{document_id}/file")
    assert download.status_code == 200
    assert download.data == picture()
    assert "no-store" in download.headers["Cache-Control"]
    with app.app_context():
        stored = db.session.get(VerificationDocument, __import__('uuid').UUID(document_id))
        assert stored.storage_key != "sample.png"
        assert stored.sha256_checksum


def test_foreign_user_cannot_view_document(client, app, ids):
    login(client)
    document_id = uploaded(client, ids)
    client.post("/api/auth/logout", headers={"X-CSRF-Token": token(client)})
    login(client, "other@example.test")
    assert client.get(f"/api/documents/{document_id}").status_code == 404
    assert client.get(f"/api/documents/{document_id}/file").status_code == 404
    assert client.get(f"/api/documents/{document_id}/ocr").status_code == 404


def test_extracts_and_compares_fields_without_approving(client, ids, app, monkeypatch):
    login(client)
    doc = uploaded(client, ids)
    from app.modules.identity.documents import surya_engine
    monkeypatch.setattr(surya_engine, "extract_text", lambda p, m: "Resident Name: Rahul Sharma\nTower: B\nFlat Number: 402\nResident Category: OWNER")
    response = ocr(client, doc)
    assert response.status_code == 200, response.json
    assert response.json["ocr"]["comparison_results"]["flat_number"]["status"] == "MATCH"
    assert response.json["ocr"]["status"] == "COMPLETED"
    with app.app_context():
        application = db.session.get(MembershipApplication, ids["app_uuid"])
        assert application.status == ApplicationStatus.PENDING


def test_mismatches_are_warnings(client, ids, monkeypatch):
    login(client)
    doc = uploaded(client, ids)
    from app.modules.identity.documents import surya_engine
    monkeypatch.setattr(surya_engine, "extract_text", lambda p, m: "Resident Name: Rahul Sharma\nTower: D\nFlat Number: 999\nResident Category: OWNER")
    result = ocr(client, doc)
    assert result.status_code == 200
    comparison = result.json["ocr"]["comparison_results"]
    assert comparison["tower"]["status"] == "MISMATCH"
    assert comparison["flat_number"]["status"] == "MISMATCH"
    assert result.json["ocr"]["warnings"]


def test_failed_ocr_preserves_file_and_review_path(client, ids, monkeypatch):
    login(client)
    doc = uploaded(client, ids)
    from app.modules.identity.documents import surya_engine
    def fail(p, m):
        raise RuntimeError("test simulation")
    monkeypatch.setattr(surya_engine, "extract_text", fail)
    assert ocr(client, doc).status_code == 503
    output = client.get(f"/api/documents/{doc}/ocr")
    assert output.status_code == 200
    assert output.json["results"][0]["status"] == "FAILED"
    assert client.get(f"/api/documents/{doc}/file").status_code == 200


def test_ocr_repeated_reuses_completed_result(client, ids, monkeypatch):
    login(client)
    doc = uploaded(client, ids)
    from app.modules.identity.documents import surya_engine
    calls = []
    def fake(p, m):
        calls.append(1)
        return "Resident Name: Rahul Sharma\nTower: B\nFlat Number: 402\nResident Category: OWNER"
    monkeypatch.setattr(surya_engine, "extract_text", fake)
    assert ocr(client, doc).status_code == 200
    repeat = ocr(client, doc)
    assert repeat.status_code == 200 and repeat.json["reused"] is True
    assert len(calls) == 1


def test_closed_application_cannot_upload(client, ids, app):
    login(client)
    with app.app_context():
        application = db.session.get(MembershipApplication, ids["app_uuid"])
        application.status = ApplicationStatus.APPROVED
        db.session.commit()
    assert upload(client, ids).status_code == 409


def test_invalid_document_id_does_not_expose_anything(client, ids):
    login(client)
    assert client.get(f"/api/documents/{uuid4()}/file").status_code == 404


def test_application_document_listing(client, ids):
    login(client)
    doc = uploaded(client, ids)
    listed = client.get(f"/api/documents/application/{ids['app']}")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json["documents"]] == [doc]
