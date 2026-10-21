"""Genuine document OCR/NLP and private job tests; SQL fixtures are rolled back."""
from datetime import timedelta
import hashlib
import io
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from test_phase3 import workspace, real_media, csrf, create, upload  # Reuse authorized PostgreSQL/API fixtures.
from app import analysis_jobs, analysis_nlp, analysis_worker, ner_model
from app.analysis_extraction import AnalysisFailure, extract_pages
from app.auth import now
from app.config import get_settings
from app.database import get_engine
from app.models import AnalysisEntity, AnalysisPage, Evidence, EvidenceAnalysis, ProcessingJob


@pytest.fixture(scope="module")
def source_pages(real_media):
    import pypdfium2 as pdfium
    source = PdfReader(io.BytesIO(real_media["pdf"]))
    writer = PdfWriter()
    writer.add_page(source.pages[0])
    pdf = io.BytesIO()
    writer.write(pdf)
    doc = pdfium.PdfDocument(pdf.getvalue())
    try:
        page = doc[0]
        independent = page.get_textpage().get_text_bounded()
        bitmap = page.render(scale=2.5)
        image = bitmap.to_pil().convert("RGB")
        bitmap.close()
        page.close()
        outputs = {}
        for suffix, fmt in [("png", "PNG"), ("jpg", "JPEG"), ("scanned_pdf", "PDF")]:
            buffer = io.BytesIO()
            image.save(buffer, format=fmt, resolution=180)
            outputs[suffix] = buffer.getvalue()
        image.close()
    finally:
        doc.close()
    return {"pdf": pdf.getvalue(), "independent": independent, "provenance": real_media["provenance"], **outputs}


@pytest.fixture
def pipeline(workspace, source_pages, monkeypatch):
    db, new_user, _, password = workspace
    connection = db.bind
    # Model files are shared read-only; originals/derivatives remain in fixture private storage.
    model_folder = Path(os.environ["PRIVATE_ROOT"])/"models"/"ner"/ner_model.REVISION
    monkeypatch.setattr(ner_model, "directory", lambda root: model_folder)
    monkeypatch.setattr(analysis_jobs, "get_engine", lambda: connection)
    monkeypatch.setattr(analysis_jobs, "Session", lambda bind: Session(bind=connection, join_transaction_mode="create_savepoint"))
    try:
        yield db, new_user, source_pages
    finally:
        connection.execute(text("SELECT pg_advisory_unlock_all()"))


def queued(client, case_id, evidence_id):
    response = client.post(f"/api/v1/cases/{case_id}/evidence/{evidence_id}/analysis", json={}, headers=csrf(client))
    assert response.status_code == 202, response.text
    return UUID(response.json()["id"])


def execute(db, job_id):
    claimed = analysis_worker.claim(db, db.bind)
    assert claimed and claimed[0] == job_id
    result = analysis_jobs.run_analysis(claimed[0], claimed[1])
    db.expire_all()
    return result, claimed


def setup_document(pipeline, kind="pdf"):
    db, new_user, media = pipeline
    owner, user = new_user()
    case = create(owner)
    extension = "pdf" if kind in {"pdf", "scanned_pdf"} else kind
    response = upload(owner, case["id"], media[kind], extension, media["provenance"])
    assert response.status_code == 201, response.text
    evidence = response.json()
    return db, new_user, media, owner, user, case, evidence


def test_embedded_text_independent_parser_and_spans(pipeline):
    import difflib
    db, _, media, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    assert execute(db, job_id)[0]
    run = db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id))
    page = db.scalar(select(AnalysisPage).where(AnalysisPage.analysis_id == run.id))
    normalize = lambda value: " ".join(value.split())
    similarity = difflib.SequenceMatcher(None, normalize(media["independent"]), normalize(page.text), autojunk=False).ratio()
    assert similarity > 0.8  # Independent PDFium reference; not the same extraction implementation.
    assert page.extraction_method == "pypdf-embedded" and page.ocr_confidence is None
    rows = list(db.scalars(select(AnalysisEntity).where(AnalysisEntity.page_id == page.id)))
    assert rows and any(row.label == "PERSON" and row.extractor == "ner" for row in rows)
    assert any(row.label == "DATE" and row.extractor == "rule" for row in rows)
    for entity in rows:
        assert page.text[entity.char_start:entity.char_end] == entity.text
        assert entity.score is None if entity.extractor == "rule" else 0 <= entity.score <= 1
    assert page.text_sha256 == hashlib.sha256(page.text.encode()).hexdigest()
    assert run.original_sha256 == evidence["sha256"] and run.artifact_id


@pytest.mark.parametrize("kind,method", [("png", "tesseract-image-eng"), ("jpg", "tesseract-image-eng"), ("scanned_pdf", "tesseract-pdf-eng")])
def test_genuine_source_raster_ocr(pipeline, kind, method):
    db, _, _, client, _, case, evidence = setup_document(pipeline, kind)
    job_id = queued(client, case["id"], evidence["id"])
    assert execute(db, job_id)[0], db.get(ProcessingJob, job_id).error_code
    run = db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id))
    page = db.scalar(select(AnalysisPage).where(AnalysisPage.analysis_id == run.id))
    assert page.extraction_method == method and len(page.text) > 100
    assert page.ocr_confidence is not None and 0 <= page.ocr_confidence <= 100
    assert len(page.ocr_words) > 20
    for word in page.ocr_words:
        assert page.text[word["char_start"]:word["char_end"]] == word["text"]
        assert word["confidence"] is None or 0 <= word["confidence"] <= 100


def test_analysis_endpoint_scope_and_read_only_roles(pipeline):
    db, new_user, _, client, _, case, evidence = setup_document(pipeline)
    other, researcher = new_user()
    base = f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}"
    assert other.post(base+"/analysis", json={}, headers=csrf(other)).status_code == 404
    assert other.get(base+"/analysis-jobs").status_code == 404
    assert TestClient(__import__('app.main', fromlist=['app']).app).get(base+"/analyses").status_code == 401
    job_id = queued(client, case["id"], evidence["id"])
    assert client.post(base+"/analysis", json={}, headers=csrf(client)).json()["id"] == str(job_id)
    assert execute(db, job_id)[0]
    run = db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id))
    for suffix in [f"/analysis-jobs/{job_id}", f"/analyses/{run.id}", f"/analyses/{run.id}/pages", f"/analyses/{run.id}/pages/1", f"/analyses/{run.id}/download"]:
        assert other.get(base+suffix).status_code == 404
    assert client.post(f"/api/v1/cases/{case['id']}/members", json={"email": researcher.email}, headers=csrf(client)).status_code == 201
    assert other.get(base+f"/analyses/{run.id}/pages/1").status_code == 200
    assert other.post(base+"/analysis", json={"reanalyze": True}, headers=csrf(other)).status_code == 403
    assert other.post(base+f"/analysis-jobs/{job_id}/retry", headers=csrf(other)).status_code == 403


def test_job_status_does_not_expose_private_lease_or_public_ingestion(pipeline):
    db, _, _, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    base = f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}"
    detail = client.get(base+f"/analysis-jobs/{job_id}")
    assert detail.json()["status"] == "queued"
    assert "lease_token" not in detail.text and "storage_key" not in detail.text
    assert client.get(f"/api/v1/ingestion-jobs/{job_id}").status_code == 404
    assert str(job_id) not in client.get("/api/v1/ingestion-jobs").text


def test_integrity_failure_never_publishes_results(pipeline):
    db, _, _, client, _, case, evidence = setup_document(pipeline)
    record = db.get(Evidence, UUID(evidence["id"]))
    record.sha256 = "0"*64
    db.commit()
    job_id = queued(client, case["id"], evidence["id"])
    assert not execute(db, job_id)[0]
    job = db.get(ProcessingJob, job_id)
    assert job.status == "failed" and job.error_code == "integrity_failed"
    run = db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id))
    assert run.artifact_id is None
    assert client.get(f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}/analyses/{run.id}/pages").status_code == 409


def test_ocr_timeout_safe_retry_retains_attempts(pipeline, monkeypatch):
    db, _, _, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    original = analysis_jobs.extract_pages
    def timeout(*args):
        raise AnalysisFailure("ocr_timeout", True)
    monkeypatch.setattr(analysis_jobs, "extract_pages", timeout)
    assert not execute(db, job_id)[0]
    job = db.get(ProcessingJob, job_id)
    assert job.status == "queued" and job.attempts == 1 and job.error_code == "ocr_timeout"
    job.next_attempt_at = now()-timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(analysis_jobs, "extract_pages", original)
    assert execute(db, job_id)[0]
    runs = list(db.scalars(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id).order_by(EvidenceAnalysis.attempt)))
    assert [run.status for run in runs] == ["failed", "completed"]
    assert db.get(ProcessingJob, job_id).attempts == 2


def test_expired_lease_recovery_and_fencing(pipeline):
    db, _, _, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    old = analysis_worker.claim(db, db.bind)
    job = db.get(ProcessingJob, job_id)
    db.add(EvidenceAnalysis(job_id=job_id, evidence_id=UUID(evidence["id"]), attempt=1, status="processing",
                            original_sha256=evidence["sha256"], pipeline_version=analysis_jobs.PIPELINE_VERSION))
    job.lease_expires_at = now()-timedelta(seconds=1)
    db.commit()
    db.bind.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": old[2]})
    current = analysis_worker.claim(db, db.bind)
    assert current[0] == old[0] and current[1] != old[1]
    assert not analysis_jobs.run_analysis(old[0], old[1])
    assert analysis_jobs.run_analysis(current[0], current[1])
    db.expire_all()
    states = list(db.scalars(select(EvidenceAnalysis.status).where(EvidenceAnalysis.job_id == job_id).order_by(EvidenceAnalysis.attempt)))
    assert states == ["interrupted", "completed"]


def test_background_access_revocation(pipeline):
    db, new_user, _, client, _, case, evidence = setup_document(pipeline)
    member, user = new_user("investigator")
    url = f"/api/v1/cases/{case['id']}"
    client.post(url+"/members", json={"email": user.email}, headers=csrf(client))
    job_id = queued(member, case["id"], evidence["id"])
    assert client.delete(url+f"/members/{user.id}", headers=csrf(client)).status_code == 200
    assert not execute(db, job_id)[0]
    assert db.get(ProcessingJob, job_id).error_code == "access_revoked"


def test_empty_and_unsupported_documents(pipeline):
    db, new_user, media = pipeline
    client, _ = new_user()
    case = create(client)
    empty = PdfWriter()
    empty.add_blank_page(width=300, height=300)
    buffer = io.BytesIO()
    empty.write(buffer)
    # Blank bytes are an explicit rejection fixture; no fabricated legal content.
    saved = upload(client, case["id"], buffer.getvalue(), "pdf", "Explicit blank-page negative test fixture").json()
    job_id = queued(client, case["id"], saved["id"])
    assert not execute(db, job_id)[0]
    assert db.get(ProcessingJob, job_id).error_code == "no_text"
    record = db.get(Evidence, UUID(saved["id"]))
    record.mime_type = "video/mp4"  # Rolled-back unsupported-type fixture, not a live video record.
    db.commit()
    assert client.post(f"/api/v1/cases/{case['id']}/evidence/{saved['id']}/analysis", json={}, headers=csrf(client)).status_code == 422
    with pytest.raises(AnalysisFailure) as unsupported:
        list(extract_pages(media["png"], "video/mp4", get_settings()))
    assert unsupported.value.code == "unsupported_document"


def test_model_integrity_and_page_limits(pipeline, monkeypatch):
    db, _, media, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    def missing(*args):
        raise ner_model.ModelUnavailable("Controlled unavailable model")
    monkeypatch.setattr(ner_model, "verify", missing)
    assert not execute(db, job_id)[0]
    assert db.get(ProcessingJob, job_id).error_code == "model_unavailable"
    monkeypatch.setattr(get_settings(), "analysis_max_page_chars", 10)
    with pytest.raises(AnalysisFailure) as size:
        list(extract_pages(media["pdf"], "application/pdf", get_settings()))
    assert size.value.code == "text_limit_exceeded"


def test_completed_result_and_artifact_access(pipeline):
    db, _, _, client, _, case, evidence = setup_document(pipeline)
    job_id = queued(client, case["id"], evidence["id"])
    assert execute(db, job_id)[0]
    base = f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}"
    response = client.get(base+"/analyses")
    run = response.json()["items"][0]
    assert len(run["models"]) == 2 and run["original_sha256"] == evidence["sha256"]
    original = client.get(base+f"/analyses/{run['id']}/download")
    assert original.status_code == 200
    assert hashlib.sha256(original.content).hexdigest() == original.headers["x-content-sha256"]
    assert client.post(base+"/analysis", json={}, headers=csrf(client)).status_code == 200
    assert client.post(base+f"/analysis-jobs/{job_id}/retry", headers=csrf(client)).status_code == 409
    assert "storage_key" not in response.text


def test_literal_rules_preserve_real_source_text(source_pages):
    page = PdfReader(io.BytesIO(source_pages["pdf"])).pages[0].extract_text()
    results = analysis_nlp.rule_entities(page)
    assert any(result["label"] == "DATE" and result["text"] == "May 24" for result in results)
    assert any(result["label"] == "DOCUMENT_REFERENCE" for result in results)
    for result in results:
        assert page[result["char_start"]:result["char_end"]] == result["text"]
        assert result["score"] is None


def test_ner_aggregates_subwords_in_real_person_name(pipeline):
    _, _, media = pipeline
    text = PdfReader(io.BytesIO(media["pdf"])).pages[0].extract_text()
    assert "Vidya Sagar" in text  # Actual licensed page, not synthetic evidence.
    candidates = analysis_nlp.named_entities(text)
    names = [entity for entity in candidates if entity["label"] == "PERSON"]
    assert any(entity["text"] == "Vidya Sagar" for entity in names)
    for entity in candidates:
        assert text[entity["char_start"]:entity["char_end"]] == entity["text"]
        assert entity["provenance"]["word_aggregation"] == "average subtoken BIO probabilities"


def test_manual_retry_exhaustion_preserves_failed_attempts(pipeline):
    db, new_user, _ = pipeline
    client, _ = new_user()
    case = create(client)
    empty = PdfWriter()
    empty.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    empty.write(buffer)
    saved = upload(client, case["id"], buffer.getvalue(), "pdf", "Explicit blank-page retry negative test fixture").json()
    base = f"/api/v1/cases/{case['id']}/evidence/{saved['id']}"
    job_id = queued(client, case["id"], saved["id"])
    for attempt in range(1, 4):
        assert not execute(db, job_id)[0]
        job = db.get(ProcessingJob, job_id)
        assert job.status == "failed" and job.attempts == attempt and job.error_code == "no_text"
        response = client.post(base+f"/analysis-jobs/{job_id}/retry", headers=csrf(client))
        assert response.status_code == (202 if attempt < 3 else 409)
    assert db.scalar(select(func.count()).select_from(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job_id)) == 3


def test_enqueue_is_asynchronous_and_queue_is_bounded(pipeline, monkeypatch):
    db, new_user, media = pipeline
    client, _ = new_user()
    case = create(client)
    def forbidden(*args):
        raise AssertionError("API enqueue must not execute inference")
    monkeypatch.setattr(analysis_nlp, "ner", forbidden)
    for number, kind in enumerate(["pdf", "png", "jpg", "scanned_pdf"], 1):
        suffix = "pdf" if kind == "scanned_pdf" else kind
        saved = upload(client, case["id"], media[kind], suffix, media["provenance"]).json()
        response = client.post(f"/api/v1/cases/{case['id']}/evidence/{saved['id']}/analysis", json={}, headers=csrf(client))
        assert response.status_code == (202 if number <= 3 else 429)
    assert db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind == "evidence_analysis", ProcessingJob.requested_by == UUID(client.get('/api/v1/auth/me').json()['id']))) == 3
