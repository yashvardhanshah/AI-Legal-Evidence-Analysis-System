"""Opt-in genuine-source OCR/NLP flow and explicitly limited measured evaluation."""
import argparse
import difflib
import hashlib
import io
import json
import time
import unicodedata

import httpx
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.models import DatasetSource, Judgment
from app.storage import PrivateStorage


def normalized(value):
    return " ".join(unicodedata.normalize("NFC", value).split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    store = PrivateStorage(get_settings().private_root)
    owner = json.loads(store.path("auth/phase3-flow.json").read_text())
    receipt_path = store.path("auth/phase4-flow.json")
    if args.verify_existing and not receipt_path.exists():
        parser.error("Run the opt-in genuine flow once before verifying persisted results")
    state = json.loads(receipt_path.read_text()) if receipt_path.exists() else {"case_id": owner["case_id"], "samples": {"embedded_pdf": {"evidence_id": owner["evidence_id"], "sha256": owner["sha256"]}}}
    with Session(get_engine()) as db:
        source_document = db.scalar(select(Judgment).where(Judgment.sha256 == owner["sha256"]))
        if not source_document:
            raise RuntimeError("The previously authorized judgment source is unavailable")
        source = db.get(DatasetSource, source_document.source_id)
        raw = store.read_verified(source_document.storage_key, source_document.sha256)
        provenance = f"Authorized evaluation derivative of page 1: {source_document.source_url}; {source.license_id}; {source.attribution}. Rasterized at 180 DPI, no invented source content."
        state["source_url"] = source_document.source_url
    reference = PdfReader(io.BytesIO(raw)).pages[0].extract_text()
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(raw)
    page = document[0]
    independent = page.get_textpage().get_text_bounded()
    bitmap = page.render(scale=2.5)
    image = bitmap.to_pil().convert("RGB")
    bitmap.close()
    page.close()
    document.close()
    with httpx.Client(base_url="http://frontend:3000/api/backend/", timeout=90) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, headers={"X-CSRF-Token": client.cookies.get("legal_csrf", "")}, **kwargs)
            if not response.is_success:
                raise RuntimeError(f"Local HTTP verification failed: {method} -> {response.status_code}")
            return response
        request("GET", "auth/csrf")
        request("POST", "auth/login", json={"email": owner["email"], "password": owner["password"]})
        try:
            if not args.verify_existing:
                for name, extension, fmt in [("source_png", "png", "PNG"), ("scanned_pdf", "pdf", "PDF")]:
                    if name not in state["samples"]:
                        buffer = io.BytesIO()
                        image.save(buffer, format=fmt, resolution=180)
                        content = buffer.getvalue()
                        result = request("POST", f"cases/{owner['case_id']}/evidence", params={"filename": "phase4-authorized-source-page."+extension, "provenance": provenance[:2000]}, content=content)
                        saved = result.json()
                        assert saved["sha256"] == hashlib.sha256(content).hexdigest()
                        state["samples"][name] = {"evidence_id": saved["id"], "sha256": saved["sha256"]}
                        receipt_path.write_text(json.dumps(state, indent=2))
                for sample in state["samples"].values():
                    prefix = f"cases/{state['case_id']}/evidence/{sample['evidence_id']}"
                    result = request("POST", prefix+"/analysis", json={}).json()
                    sample["job_id"] = result["id"]
                receipt_path.write_text(json.dumps(state, indent=2))
            report = {"source_url": state["source_url"], "case_id": state["case_id"], "samples": {},
                      "metric_notice": "OCR similarity compares with the publisher PDF text layer, which itself contains errors; SequenceMatcher ratio is not ground-truth CER or calibrated accuracy. NER anchor coverage is limited to six manually identified person mentions, not full precision/recall."}
            # These exact mentions are present on this licensed source page. No entities are injected into analysis.
            anchors = ["Vidya Sagar", "P. A. Mehta", "LOGENDRA NATH JHA", "PATANJALI SASTRI", "S. R. DAS", "VIVIAN BosE"]
            assert all(anchor in reference for anchor in anchors)
            for name, sample in state["samples"].items():
                prefix = f"cases/{state['case_id']}/evidence/{sample['evidence_id']}"
                deadline = time.monotonic()+720
                while True:
                    job = request("GET", prefix+"/analysis-jobs/"+sample["job_id"]).json()
                    if job["status"] in {"completed", "failed"}:
                        break
                    if time.monotonic() > deadline:
                        raise RuntimeError("Worker did not finish within the verification budget")
                    time.sleep(2)
                if job["status"] != "completed":
                    raise RuntimeError("Real analysis job failed: "+str(job["error_code"]))
                run = next(item for item in job["runs"] if item["status"] == "completed")
                sample["analysis_id"] = run["id"]
                extracted = request("GET", prefix+f"/analyses/{run['id']}/pages/1").json()
                original = request("GET", prefix+"/download").content
                assert hashlib.sha256(original).hexdigest() == sample["sha256"] == run["original_sha256"]
                assert hashlib.sha256(extracted["text"].encode()).hexdigest() == extracted["text_sha256"]
                for entity in extracted["entities"]:
                    assert extracted["text"][entity["char_start"]:entity["char_end"]] == entity["text"]
                artifact = request("GET", prefix+f"/analyses/{run['id']}/download")
                assert hashlib.sha256(artifact.content).hexdigest() == artifact.headers["x-content-sha256"]
                labels = {}
                for entity in extracted["entities"]:
                    labels[entity["label"]] = labels.get(entity["label"], 0)+1
                persons = [e["text"] for e in extracted["entities"] if e["label"] == "PERSON"]
                matched = [anchor for anchor in anchors if normalized(anchor).casefold() in {normalized(value).strip(" .").casefold() for value in persons}]
                comparison = independent if name == "embedded_pdf" else reference
                report["samples"][name] = {"evidence_id": sample["evidence_id"], "job_id": sample["job_id"], "analysis_id": run["id"],
                    "original_sha256": sample["sha256"], "pages": run["page_count"], "page1_method": extracted["extraction_method"],
                    "page1_characters": len(extracted["text"]), "page1_text_sha256": extracted["text_sha256"],
                    "page1_character_similarity": difflib.SequenceMatcher(None, normalized(comparison), normalized(extracted["text"]), autojunk=False).ratio(),
                    "page1_tesseract_confidence": extracted["ocr_confidence"], "page1_entities_by_label": labels,
                    "exact_person_anchors_matched": matched, "person_anchor_count": len(anchors),
                    "public_source_entity_examples": [{key: entity[key] for key in ("label", "text", "char_start", "char_end", "extractor", "score")} for entity in extracted["entities"][:10]]}
            receipt_path.write_text(json.dumps(state, indent=2))
            store.path("auth/phase4-evaluation.json").write_text(json.dumps(report, indent=2))
            print(json.dumps(report, indent=2))
        finally:
            image.close()
            request("POST", "auth/logout")


if __name__ == "__main__":
    main()
