"""Real PostgreSQL/API security tests, rolled back; valid media derives from the licensed corpus."""
from datetime import timedelta
import hashlib
import io
import os
from pathlib import Path
import secrets
import subprocess
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth
from app.auth import ACCESS, CSRF, REFRESH, now
from app.config import get_settings
from app.database import get_engine
from app.library_api import session_dependency
from app.main import app
from app.models import AuditLog, AuthSession, Case, Evidence, Judgment, User
from app.storage import PrivateStorage, StorageError, validate_evidence


@pytest.fixture(scope="module")
def real_media(tmp_path_factory):
    if os.environ.get("RUN_DB_TESTS") != "1" or os.environ.get("RUN_CORPUS_TESTS") != "1":
        pytest.skip("Requires migrated PostgreSQL and approved genuine corpus")
    with Session(get_engine()) as db:
        judgment = db.scalar(select(Judgment).order_by(Judgment.byte_size))
        assert judgment is not None
        raw = PrivateStorage(get_settings().private_root).read_verified(judgment.storage_key, judgment.sha256)
        provenance = f"Public judgment {judgment.source_url}; CC BY 4.0, publisher attribution in dataset sources. Test derivatives of original page 1."
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(raw)
    try:
        image = doc[0].render(scale=0.5).to_pil().convert("RGB")
        image.thumbnail((640, 640))
        png, jpg = io.BytesIO(), io.BytesIO()
        image.save(png, "PNG")
        image.save(jpg, "JPEG")
    finally:
        doc.close()
    folder = tmp_path_factory.mktemp("licensed-media")
    (folder/"page.png").write_bytes(png.getvalue())
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(folder/"page.png"),
                    "-t", "0.5", "-r", "2", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", str(folder/"page.mp4")], check=True, timeout=30)
    return {"pdf": raw, "png": png.getvalue(), "jpg": jpg.getvalue(), "jpeg": jpg.getvalue(), "mp4": (folder/"page.mp4").read_bytes(), "provenance": provenance}


@pytest.fixture
def workspace(monkeypatch, tmp_path, real_media):
    # Dependency overrides share a savepoint-backed session; API commits are
    # real SQL writes within a transaction rolled back after each test.
    with get_engine().connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False) as db:
            def dependency():
                yield db
            app.dependency_overrides[session_dependency] = dependency
            monkeypatch.setattr(get_settings(), "private_root", tmp_path)
            monkeypatch.setattr(auth, "limiter", auth.RateLimiter())
            clients = []
            password = secrets.token_urlsafe(24)

            def new_user(role="legal_researcher"):
                client = TestClient(app)
                clients.append(client)
                client.get("/api/v1/auth/csrf")
                email = uuid4().hex+"@example.org"
                response = client.post("/api/v1/auth/register", json={"email": email, "display_name": "Authorized integration tester", "password": password}, headers=csrf(client))
                assert response.status_code == 201, response.text
                uid = UUID(response.json()["id"])
                user = db.get(User, uid)
                user.role = role
                db.commit()
                response = client.post("/api/v1/auth/login", json={"email": email, "password": password}, headers=csrf(client))
                assert response.status_code == 200, response.text
                return client, user

            try:
                yield db, new_user, real_media, password
            finally:
                app.dependency_overrides.clear()
                for client in clients:
                    client.close()
                db.close()
                transaction.rollback()


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get(CSRF, "")}


def create(client, **overrides):
    response = client.post("/api/v1/cases", json={"title": "Owner-authorized integration verification", "description": "User-created metadata for API verification; no asserted legal allegations.", "jurisdiction": "Academic verification workspace", **overrides}, headers=csrf(client))
    assert response.status_code == 201, response.text
    return response.json()


def upload(client, case_id, raw, extension, provenance):
    return client.post(f"/api/v1/cases/{case_id}/evidence", params={"filename": "licensed-source."+extension, "provenance": provenance}, content=raw, headers={**csrf(client), "Content-Type": "application/octet-stream"})


def test_registration_validation_fixed_role_and_hash(workspace):
    db, new_user, _, password = workspace
    client, user = new_user()
    assert user.role == "legal_researcher" and user.password_hash != password
    assert auth.password_matches(password, user.password_hash)
    body = {"email": uuid4().hex+"@example.org", "display_name": "Tester", "password": password, "role": "administrator"}
    response = client.post("/api/v1/auth/register", json=body, headers=csrf(client))
    assert response.status_code == 422 and password not in response.text
    body.pop("role")
    body["password"] = "short"
    assert client.post("/api/v1/auth/register", json=body, headers=csrf(client)).status_code == 422
    body.update(email=user.email, password=password)
    assert client.post("/api/v1/auth/register", json=body, headers=csrf(client)).status_code == 409


def test_invalid_login_lockout_and_secure_cookie_flags(workspace):
    db, new_user, _, password = workspace
    client, user = new_user()
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password}, headers=csrf(client))
    cookies = response.headers.get_list("set-cookie")
    assert any("legal_access=" in value and "HttpOnly" in value and "SameSite=strict" in value for value in cookies)
    assert any("legal_refresh=" in value and "HttpOnly" in value for value in cookies)
    assert "access_token" not in response.text
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": user.email, "password": secrets.token_urlsafe(16)}, headers=csrf(client)).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": user.email, "password": password}, headers=csrf(client)).status_code == 401
    assert user.locked_until > now()


def test_csrf_origin_and_public_access(workspace):
    _, new_user, _, _ = workspace
    client, _ = new_user()
    assert client.post("/api/v1/cases", json={"title": "Unauthorized request", "jurisdiction": "Test"}).status_code == 403
    assert client.post("/api/v1/cases", json={"title": "Unauthorized request", "jurisdiction": "Test"}, headers={**csrf(client), "Origin": "https://evil.example"}).status_code == 403
    anonymous = TestClient(app)
    assert anonymous.get("/api/v1/cases").status_code == 401
    assert anonymous.get("/api/v1/judgments?limit=1").status_code == 200
    assert anonymous.get("/api/v1/dataset-sources").status_code == 200


def test_refresh_rotation_expiration_and_replay(workspace):
    db, new_user, _, _ = workspace
    client, user = new_user()
    old_refresh = client.cookies.get(REFRESH)
    claims = jwt.decode(client.cookies.get(ACCESS), auth.signing_key(), algorithms=["HS256"], audience=get_settings().jwt_audience, issuer=get_settings().jwt_issuer)
    claims["exp"] = now()-timedelta(seconds=1)
    expired = jwt.encode(claims, auth.signing_key(), algorithm="HS256")
    client.cookies.set(ACCESS, expired, domain="testserver.local", path="/")
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/refresh", headers=csrf(client)).status_code == 200
    assert old_refresh != client.cookies.get(REFRESH)
    assert client.get("/api/v1/auth/me").status_code == 200
    client.cookies.set(REFRESH, old_refresh, domain="testserver.local", path="/")
    assert client.post("/api/v1/auth/refresh", headers=csrf(client)).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_stolen_access_token(workspace):
    _, new_user, _, _ = workspace
    client, _ = new_user()
    access = client.cookies.get(ACCESS)
    assert client.post("/api/v1/auth/logout", headers=csrf(client)).status_code == 200
    client.cookies.set(ACCESS, access, domain="testserver.local", path="/")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_case_creation_search_edit_and_archive(workspace):
    db, new_user, _, _ = workspace
    client, user = new_user()
    case = create(client)
    assert case["owner_id"] == str(user.id) and case["reference"].startswith("CASE-") and case["created_at"]
    assert client.get("/api/v1/cases", params={"q": "Owner-authorized"}).json()["total"] == 1
    result = client.patch(f"/api/v1/cases/{case['id']}", json={"title": "Updated owner metadata", "incident_on": "2026-10-01"}, headers=csrf(client))
    assert result.status_code == 200 and result.json()["incident_on"] == "2026-10-01"
    assert client.patch(f"/api/v1/cases/{case['id']}", json={"owner_id": str(uuid4())}, headers=csrf(client)).status_code == 422
    assert client.post(f"/api/v1/cases/{case['id']}/archive", headers=csrf(client)).json()["status"] == "archived"
    assert client.patch(f"/api/v1/cases/{case['id']}", json={"title": "Blocked"}, headers=csrf(client)).status_code == 409
    assert client.get(f"/api/v1/cases/{case['id']}").status_code == 200


def test_other_user_cannot_enumerate_case_or_evidence(workspace):
    _, new_user, media, _ = workspace
    owner, _ = new_user()
    stranger, _ = new_user()
    case = create(owner)
    saved = upload(owner, case["id"], media["pdf"], "pdf", media["provenance"]).json()
    assert stranger.get("/api/v1/cases").json()["total"] == 0
    paths = ["", "/evidence", f"/evidence/{saved['id']}", f"/evidence/{saved['id']}/download", "/audit", "/members"]
    for path in paths:
        assert stranger.get(f"/api/v1/cases/{case['id']}"+path).status_code == 404
    assert stranger.patch(f"/api/v1/cases/{case['id']}", json={"title": "Blocked"}, headers=csrf(stranger)).status_code == 404
    assert stranger.post(f"/api/v1/cases/{case['id']}/archive", headers=csrf(stranger)).status_code == 404
    assert upload(stranger, case["id"], media["pdf"], "pdf", media["provenance"]).status_code == 404
    assert stranger.post(f"/api/v1/cases/{case['id']}/members", json={"email": "x@example.org"}, headers=csrf(stranger)).status_code == 404


@pytest.mark.parametrize("role,can_write", [("legal_researcher", False), ("investigator", True), ("lawyer", True)])
def test_assigned_roles_and_revocation(workspace, role, can_write):
    _, new_user, media, _ = workspace
    owner, _ = new_user()
    member, target = new_user(role)
    case = create(owner)
    url = f"/api/v1/cases/{case['id']}"
    assert owner.post(url+"/members", json={"email": target.email}, headers=csrf(owner)).status_code == 201
    assert member.get(url).status_code == 200
    assert member.patch(url, json={"description": "Collaborator metadata update"}, headers=csrf(member)).status_code == (200 if can_write else 403)
    assert upload(member, case["id"], media["pdf"], "pdf", media["provenance"]).status_code == (201 if can_write else 403)
    assert member.post(url+"/archive", headers=csrf(member)).status_code == 403
    assert owner.delete(url+f"/members/{target.id}", headers=csrf(owner)).status_code == 200
    assert member.get(url).status_code == 404


def test_administrator_and_role_assignment(workspace):
    _, new_user, _, _ = workspace
    owner, target = new_user()
    admin, _ = new_user("administrator")
    case = create(owner)
    assert admin.get(f"/api/v1/cases/{case['id']}").status_code == 200
    assert owner.patch(f"/api/v1/admin/users/{target.id}/role", json={"role": "administrator"}, headers=csrf(owner)).status_code == 403
    assert admin.patch(f"/api/v1/admin/users/{target.id}/role", json={"role": "lawyer"}, headers=csrf(admin)).status_code == 200
    assert owner.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("extension", ["pdf", "png", "jpg", "jpeg", "mp4"])
def test_real_authorized_media_hash_download_audit(workspace, extension):
    db, new_user, media, _ = workspace
    client, user = new_user()
    case = create(client)
    raw = media[extension]
    result = upload(client, case["id"], raw, extension, media["provenance"])
    assert result.status_code == 201, result.text
    row = result.json()
    assert row["sha256"] == hashlib.sha256(raw).hexdigest() and row["uploader_id"] == str(user.id)
    assert "storage_key" not in row
    downloaded = client.get(f"/api/v1/cases/{case['id']}/evidence/{row['id']}/download")
    assert downloaded.status_code == 200 and downloaded.content == raw
    assert downloaded.headers["x-content-sha256"] == row["sha256"]
    assert downloaded.headers["content-disposition"].startswith("attachment;")
    assert downloaded.headers["cache-control"] == "no-store"
    actions = [item["action"] for item in client.get(f"/api/v1/cases/{case['id']}/audit").json()["items"]]
    assert "evidence.upload" in actions and "evidence.download" in actions
    assert upload(client, case["id"], raw, extension, media["provenance"]).status_code == 409


def test_upload_validation_size_paths_and_integrity_failure(workspace, monkeypatch):
    db, new_user, media, _ = workspace
    client, _ = new_user()
    case = create(client)
    for filename, raw in [("../unsafe.pdf", media["pdf"]), ("evil\r\n.pdf", media["pdf"]), ("not.pdf", b"not a PDF"), ("mismatch.png", media["jpg"]), ("fake.mp4", b"\x00\x00\x00\x18ftypisom00000000")]:
        result = client.post(f"/api/v1/cases/{case['id']}/evidence", params={"filename": filename, "provenance": "Negative validation test"}, content=raw, headers=csrf(client))
        assert result.status_code == 422, result.text
    monkeypatch.setattr(get_settings(), "max_file_bytes", 100)
    assert upload(client, case["id"], media["pdf"], "pdf", media["provenance"]).status_code == 413
    monkeypatch.setattr(get_settings(), "max_file_bytes", 20_000_000)
    saved = upload(client, case["id"], media["pdf"], "pdf", media["provenance"]).json()
    row = db.get(Evidence, UUID(saved["id"]))
    row.sha256 = "0"*64  # Controlled DB fixture corruption, rolled back.
    db.commit()
    response = client.get(f"/api/v1/cases/{case['id']}/evidence/{row.id}/download")
    assert response.status_code == 409 and response.content != media["pdf"]
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "evidence.integrity_failed")) >= 1


def test_auth_throttle_and_tampered_jwt(workspace):
    _, new_user, _, _ = workspace
    client, _ = new_user()
    access = client.cookies.get(ACCESS)
    client.cookies.set(ACCESS, access[:-8]+"tampered", domain="testserver.local", path="/")
    assert client.get("/api/v1/cases").status_code == 401
    # Exercise the actual route without spending CPU on 30 password KDF calls.
    from starlette.requests import Request
    auth.limiter.entries.clear()
    req = Request({"type": "http", "client": ("testclient", 123)})
    for _ in range(30):
        auth.limiter.check(req, "login", 30, 60)
    assert client.post("/api/v1/auth/login", json={"email": "unknown@example.org", "password": "unused"}, headers=csrf(client)).status_code == 429


def test_actual_stream_limit_and_archived_upload(workspace, monkeypatch):
    _, new_user, media, _ = workspace
    client, _ = new_user()
    case = create(client)
    monkeypatch.setattr(get_settings(), "max_file_bytes", 100)
    response = client.post(f"/api/v1/cases/{case['id']}/evidence", params={"filename": "source.pdf", "provenance": media["provenance"]},
                           content=iter([media["pdf"][:60], media["pdf"][60:120]]), headers=csrf(client))
    assert "content-length" not in response.request.headers
    assert response.status_code == 413
    monkeypatch.setattr(get_settings(), "max_file_bytes", 20_000_000)
    assert client.post(f"/api/v1/cases/{case['id']}/archive", headers=csrf(client)).status_code == 200
    assert upload(client, case["id"], media["pdf"], "pdf", media["provenance"]).status_code == 409


def test_evidence_bound_to_case_and_secure_cookie_option(workspace, monkeypatch):
    _, new_user, media, password = workspace
    client, user = new_user()
    first, second = create(client), create(client)
    saved = upload(client, first["id"], media["pdf"], "pdf", media["provenance"]).json()
    assert client.get(f"/api/v1/cases/{second['id']}/evidence/{saved['id']}/download").status_code == 404
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password}, headers=csrf(client))
    assert response.status_code == 200
    assert all("Secure" in value for value in response.headers.get_list("set-cookie"))


def test_jwt_purpose_issuer_and_algorithm_rejection(workspace):
    _, new_user, _, _ = workspace
    client, _ = new_user()
    claims = jwt.decode(client.cookies.get(ACCESS), auth.signing_key(), algorithms=["HS256"], audience=get_settings().jwt_audience)
    for modified, algorithm in [({**claims, "type": "refresh"}, "HS256"), ({**claims, "iss": "untrusted"}, "HS256"), (claims, "HS384")]:
        invalid = jwt.encode(modified, auth.signing_key(), algorithm=algorithm)
        client.cookies.set(ACCESS, invalid, domain="testserver.local", path="/")
        assert client.get("/api/v1/auth/me").status_code == 401


def test_operator_import_requires_real_authorized_uploader(workspace, tmp_path):
    db, new_user, media, _ = workspace
    from app.ingestion import import_evidence
    owner, user = new_user()
    _, stranger = new_user()
    case = create(owner)
    path = tmp_path/"authorized.pdf"
    path.write_bytes(media["pdf"])
    with pytest.raises(ValueError):
        import_evidence(db, UUID(case["id"]), path, media["provenance"])
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as denied:
        import_evidence(db, UUID(case["id"]), path, media["provenance"], stranger.id)
    assert denied.value.status_code == 404
    result = import_evidence(db, UUID(case["id"]), path, media["provenance"], user.id)
    assert result.uploader_id == user.id and result.sha256 == hashlib.sha256(media["pdf"]).hexdigest()
