import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_engine
from app.documents import OCRRequired, clean_text, extract_pdf
from app.main import app
from app.models import DatasetSource, Judgment, JudgmentPassage, SystemMetadata
from app.sources import parse_supreme_metadata, validate_public_url
from app.storage import PrivateStorage, StorageError, validate_evidence


@pytest.mark.parametrize("key", ["../outside", "/absolute", "a/../b", "a\\b", "C:/file", "a/./b"])
def test_private_storage_rejects_paths(tmp_path, key):
    with pytest.raises(StorageError):
        PrivateStorage(tmp_path).path(key)


def test_storage_integrity_and_idempotence(tmp_path):
    store = PrivateStorage(tmp_path)
    content = b"Storage unit-test bytes; this is not legal evidence."
    first, second = store.put(content, "metadata"), store.put(content, "metadata")
    assert first == second
    assert first.sha256 == hashlib.sha256(content).hexdigest()
    assert store.read_verified(first.key, first.sha256) == content
    with pytest.raises(StorageError):
        store.read_verified(first.key, "0" * 64)


def test_upload_validation_rejects_malicious_inputs():
    for content, name in [(b"not-a-pdf", "file.pdf"), (b"not-an-image", "photo.png"), (b"invalid", "../case.pdf"), (b"", "empty.pdf")]:
        with pytest.raises(StorageError):
            validate_evidence(content, name, 1000)


@pytest.mark.parametrize("url", ["http://127.0.0.1/file", "https://evil.example/file", "file:///private", "https://user:password@indian-supreme-court-judgments.s3.ap-south-1.amazonaws.com/file"])
def test_download_allowlist(url):
    with pytest.raises(ValueError):
        validate_public_url(url)


def test_query_validation_and_private_routes():
    client = TestClient(app)
    assert client.post("/api/v1/search/judgments", json={"query": "  "}).status_code == 422
    assert client.post("/api/v1/search/judgments", json={"query": "equality", "limit": 1000}).status_code == 422
    assert client.get("/api/v1/evidence").status_code == 404
    assert client.get("/private_data/originals/file").status_code == 404
    assert client.get("/api/v1/cases").status_code == 401


@pytest.fixture
def db():
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Requires explicitly enabled PostgreSQL integration tests")
    with Session(get_engine()) as session:
        yield session


@pytest.fixture
def corpus(db):
    if os.environ.get("RUN_CORPUS_TESTS") != "1":
        pytest.skip("Requires approved, genuinely ingested public corpus and local model")
    receipts = list((get_settings().private_root / "receipts").glob("*.json"))
    assert len(receipts) >= 50
    expected_unique = len({json.loads(path.read_text())["pdf_sha256"] for path in receipts})
    assert db.scalar(select(func.count()).select_from(Judgment)) >= expected_unique > 0
    row = db.scalar(select(Judgment).order_by(Judgment.byte_size))
    assert row is not None
    return row


def test_additive_migrations_preserve_phase1():
    if os.environ.get("RUN_DB_TESTS") != "1":
        pytest.skip("Requires PostgreSQL")
    from alembic import command
    from alembic.config import Config
    # Isolated schema inside a rolled-back transaction; existing tables are untouched.
    schema = "migration_check_" + uuid4().hex
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_foundation")
            connection.execute(text("INSERT INTO system_metadata (key, value) VALUES ('preservation_probe', 'retained')"))
            command.upgrade(config, "head")
            command.upgrade(config, "head")
            assert connection.scalar(text("SELECT value FROM system_metadata WHERE key='preservation_probe'")) == "retained"
            assert connection.scalar(text("SELECT value FROM system_metadata WHERE key='development_phase'")) == "1"
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0005_visual_analysis"
            tables = set(inspect(connection).get_table_names(schema=schema))
            assert {"dataset_sources", "judgments", "judgment_passages", "legal_provisions", "cases", "evidence", "evidence_artifacts", "processing_jobs", "audit_logs"}.issubset(tables)
        finally:
            transaction.rollback()


def test_database_foundation_preserved(db):
    assert db.get(SystemMetadata, "development_phase").value == "1"
    assert db.get(SystemMetadata, "legal_data_schema").value == "2"
    # Phase 3 permits user-created cases; no legacy rows are assigned fake owners.
    assert db.scalar(text("SELECT count(*) FROM cases WHERE owner_id IS NULL")) == 0
    assert db.scalar(text("SELECT count(*) FROM evidence WHERE uploader_id IS NULL")) == 0


def test_public_library_api(db):
    client = TestClient(app)
    assert client.get("/api/v1/dataset-sources").status_code == 200
    assert client.get("/api/v1/ingestion-jobs").status_code == 200
    result = client.get("/api/v1/judgments?limit=2").json()
    assert result["total"] == db.scalar(select(func.count()).select_from(Judgment))
    assert len(result["items"]) <= 2
    assert "storage_key" not in json.dumps(result)
    assert client.get("/api/v1/judgments/not-a-uuid").status_code == 422
    assert client.get(f"/api/v1/judgments/{uuid4()}").status_code == 404
    assert client.get("/api/v1/legal-provisions?q=equality").status_code == 200


def test_search_failure_sanitized(db, monkeypatch):
    def failed(*args, **kwargs):
        raise RuntimeError("private internal detail")
    monkeypatch.setattr("app.vectors.semantic_search", failed)
    response = TestClient(app).post("/api/v1/search/judgments", json={"query": "fundamental rights"})
    assert response.status_code == 503
    assert "private internal detail" not in response.text


def test_real_document_integrity_extraction_and_chunks(db, corpus):
    from app.ingestion import storage
    raw = storage().read_verified(corpus.storage_key, corpus.sha256)
    pages, method = extract_pdf(raw, get_settings().max_pdf_pages, get_settings().ocr_enabled)
    assert method == corpus.extraction_method
    passages = list(db.scalars(select(JudgmentPassage).where(JudgmentPassage.judgment_id == corpus.id)))
    assert passages
    for p in passages:
        assert pages[p.page_number-1][p.char_start:p.char_end] == p.text
        assert hashlib.sha256(p.text.encode()).hexdigest() == p.text_sha256
        assert 0 < p.token_count <= 256
    assert [hashlib.sha256(page.encode()).hexdigest() for page in pages] == corpus.provenance["cleaned_page_sha256"]


def test_duplicate_real_document_no_new_rows(db, corpus):
    from app.ingestion import ingest_document
    from app.sources import DocumentPlan
    source = db.get(DatasetSource, corpus.source_id)
    doc = DocumentPlan(external_id=corpus.external_id, pdf_url=corpus.source_url, metadata_url=corpus.metadata_url,
        pdf_bytes=corpus.byte_size, metadata_bytes=1, pdf_etag=corpus.provenance["pdf_etag"], metadata_etag=corpus.provenance["metadata_etag"])
    before = db.scalar(select(func.count()).select_from(Judgment))
    record, created = ingest_document(db, source, doc)
    assert not created and record.id == corpus.id
    assert db.scalar(select(func.count()).select_from(Judgment)) == before


def test_missing_source_metadata_stays_missing(db, corpus):
    parsed = parse_supreme_metadata({"path": corpus.external_id}, corpus.external_id)
    assert parsed["title"] is None and parsed["judgment_date"] is None and parsed["citation"] is None


def test_real_embeddings_and_persistent_chroma(db, corpus):
    import numpy as np
    from app.vectors import collection, embedder
    passage = db.scalar(select(JudgmentPassage).where(JudgmentPassage.judgment_id == corpus.id))
    vectors = embedder().encode([passage.text, passage.text], normalize_embeddings=True)
    assert vectors.shape == (2, 384) and np.isfinite(vectors).all()
    assert np.allclose(vectors[0], vectors[1])
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
    expected = db.scalar(select(func.count()).select_from(JudgmentPassage).where(JudgmentPassage.indexed_at.is_not(None)))
    assert collection().count() == expected > 0
    child = subprocess.check_output([sys.executable, "-c", "from app.vectors import collection; print(collection().count())"], text=True)
    assert int(child.strip().splitlines()[-1]) == expected


def test_actual_search_matches_postgres_provenance(db, corpus):
    response = TestClient(app).post("/api/v1/search/judgments", json={"query": "fundamental rights and equality before the law", "limit": 3})
    assert response.status_code == 200
    result = response.json()
    assert result["metric"] == "cosine_distance" and result["items"]
    assert len({item["judgment_id"] for item in result["items"]}) == len(result["items"])
    for item in result["items"]:
        from uuid import UUID
        passage = db.get(JudgmentPassage, UUID(item["passage_id"]))
        judgment = db.get(Judgment, passage.judgment_id)
        assert item["excerpt"] == passage.text
        assert item["source_url"] == judgment.source_url
        assert item["title"] == judgment.title
        assert isinstance(item["distance"], float)


def test_ocr_fallback_from_real_source_page(db, corpus):
    import pypdfium2 as pdfium
    from app.ingestion import storage
    raw = storage().read_verified(corpus.storage_key, corpus.sha256)
    document = pdfium.PdfDocument(raw)
    try:
        bitmap = document[0].render(scale=2).to_pil().convert("RGB")
        buffer = io.BytesIO()
        bitmap.save(buffer, format="PDF")
    finally:
        document.close()
    # This is a rasterized derivative of a real source, not synthetic legal text.
    with pytest.raises(OCRRequired):
        extract_pdf(buffer.getvalue(), 2, allow_ocr=False)
    pages, method = extract_pdf(buffer.getvalue(), 2, allow_ocr=True)
    assert method == "pypdf+tesseract-eng" and len(pages[0]) >= 30


def test_ingestion_failure_and_safe_retry_on_real_corpus(db, corpus, monkeypatch):
    from app import ingestion
    from app.config import get_settings
    manifest = get_settings().private_root / "plans" / "supreme-1951-50.json"
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    original = ingestion.ingest_document
    fail_once = True

    def interrupted(session, source, doc):
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise ConnectionError("Controlled integration-test interruption")
        return original(session, source, doc)

    # Job and audit fixtures are rolled back; the real corpus is never replaced.
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as isolated:
                monkeypatch.setattr(ingestion, "ingest_document", interrupted)
                failed = ingestion.ingest_batch(isolated, manifest, digest, 45_000_000)
                assert failed["failed"] == 1 and failed["status"] == "failed"
                monkeypatch.setattr(ingestion, "ingest_document", original)
                from uuid import UUID
                retried = ingestion.ingest_batch(isolated, manifest, digest, 45_000_000, UUID(failed["job_id"]))
                assert retried["status"] == "completed" and retried["failed"] == 0
                assert retried["imported"] == 0 and retried["duplicates"] == 50
        finally:
            transaction.rollback()
