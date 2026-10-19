"""Opt-in real HTTP flow using an existing licensed judgment; never downloads data.

Creates user-authorized verification metadata, not fabricated case allegations.
Credentials and verification receipts stay only in ignored private runtime storage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import DatasetSource, Judgment
from app.storage import PrivateStorage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://frontend:3000/api/backend")
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    # Never send generated credentials to an arbitrary external service.
    if args.base_url not in {"http://frontend:3000/api/backend", "http://127.0.0.1:3000/api/backend", "http://localhost:3000/api/backend", "http://127.0.0.1:8000/api/v1"}:
        parser.error("Use a supported local service URL")
    store = PrivateStorage(get_settings().private_root)
    receipt = store.path("auth/phase3-flow.json")
    receipt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if args.verify_existing:
        state = json.loads(receipt.read_text())
    else:
        if receipt.exists():
            parser.error("A saved flow already exists; use --verify-existing to preserve it")
        state = {"email": "verification-"+uuid4().hex+"@example.org", "password": secrets.token_urlsafe(32)}
    with httpx.Client(base_url=args.base_url+"/", timeout=90) as client:
        def request(method, path, **kwargs):
            headers = {"X-CSRF-Token": client.cookies.get("legal_csrf", "")}
            result = client.request(method, path.lstrip("/"), headers=headers, **kwargs)
            if not result.is_success:
                raise RuntimeError(f"HTTP verification failed: {method} {path.split('?')[0]} -> {result.status_code}")
            return result

        request("GET", "auth/csrf")
        if not args.verify_existing:
            result = request("POST", "auth/register", json={"email": state["email"], "password": state["password"], "display_name": "Phase 3 authorized flow verification"}).json()
            state["user_id"] = result["id"]
        request("POST", "auth/login", json={"email": state["email"], "password": state["password"]})
        assert request("GET", "auth/me").json()["id"] == state["user_id"]
        request("POST", "auth/refresh")
        if not args.verify_existing:
            case = request("POST", "cases", json={"title": "Phase 3 owner-authorized workflow verification", "description": "User-authorized academic integration check using an existing CC BY 4.0 public judgment; no legal allegations are asserted.", "jurisdiction": "Academic verification workspace"}).json()
            state["case_id"] = case["id"]
            with Session(get_engine()) as db:
                source_document = db.scalar(select(Judgment).order_by(Judgment.byte_size))
                source = db.get(DatasetSource, source_document.source_id)
                raw = store.read_verified(source_document.storage_key, source_document.sha256)
                provenance = f"Authorized public-source verification copy, not private case evidence: {source_document.source_url}; {source.license_id}; {source.attribution}"
            evidence = request("POST", f"cases/{state['case_id']}/evidence", params={"filename": "authorized-public-judgment.pdf", "provenance": provenance[:2000]}, content=raw).json()
            assert evidence["sha256"] == hashlib.sha256(raw).hexdigest()
            state["evidence_id"], state["sha256"] = evidence["id"], evidence["sha256"]
            # Only the operator's private runtime directory stores the password.
            fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as output:
                json.dump(state, output)
        case = request("GET", f"cases/{state['case_id']}").json()
        assert case["owner_id"] == state["user_id"]
        evidence = request("GET", f"cases/{state['case_id']}/evidence/{state['evidence_id']}").json()
        assert evidence["uploader_id"] == state["user_id"] and evidence["sha256"] == state["sha256"]
        downloaded = request("GET", f"cases/{state['case_id']}/evidence/{state['evidence_id']}/download")
        assert hashlib.sha256(downloaded.content).hexdigest() == state["sha256"]
        events = request("GET", f"cases/{state['case_id']}/audit").json()["items"]
        assert {"case.create", "evidence.upload", "evidence.download"}.issubset({row["action"] for row in events})
        request("POST", "auth/logout")
        assert client.get("auth/me").status_code == 401
        print(json.dumps({"result": "PASS", "mode": "verify persisted flow" if args.verify_existing else "register-login-create-upload-hash-download-logout",
                          "user_id": state["user_id"], "case_id": state["case_id"], "evidence_id": state["evidence_id"], "sha256": state["sha256"]}, indent=2))


if __name__ == "__main__":
    main()
