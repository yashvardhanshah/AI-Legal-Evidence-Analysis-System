"""Operator-only ingestion. PostgreSQL and immutable files precede vector indexing."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.documents import chunk_pages, extract_pdf
from app.models import AuditLog, Case, DatasetSource, Evidence, Judgment, JudgmentPassage, LegalProvision, ProcessingJob
from app.sources import BatchPlan, fetch, parse_supreme_metadata
from app.storage import PrivateStorage, validate_evidence
from app.vectors import tokenizer

PIPELINE_VERSION = "pdf-page-token220-overlap32-v1"


def storage():
    settings = get_settings()
    return PrivateStorage(settings.private_root, settings.max_file_bytes)


def acquire_document(doc) -> tuple[bytes, bytes]:
    """Durable verified download receipts allow extraction retries without redownloads."""
    store = storage()
    receipt_id = hashlib.sha256((doc.pdf_url + doc.pdf_etag + doc.metadata_etag).encode()).hexdigest()
    receipt_path = store.path(f"receipts/{receipt_id}.json")
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_bytes())
        if receipt["pdf_url"] != doc.pdf_url or receipt["metadata_url"] != doc.metadata_url:
            raise ValueError("Download receipt source mismatch")
        body = store.read_verified(receipt["pdf_key"], receipt["pdf_sha256"])
        metadata = store.read_verified(receipt["metadata_key"], receipt["metadata_sha256"])
        if len(body) != doc.pdf_bytes or len(metadata) != doc.metadata_bytes:
            raise ValueError("Download receipt size mismatch")
        return body, metadata
    metadata = fetch(doc.metadata_url, doc.metadata_bytes, doc.metadata_etag)
    body = fetch(doc.pdf_url, doc.pdf_bytes, doc.pdf_etag)
    if len(body) != doc.pdf_bytes or len(metadata) != doc.metadata_bytes:
        raise ValueError("Downloaded bytes differ from approved manifest")
    parse_supreme_metadata(json.loads(metadata), doc.external_id)
    validate_evidence(body, doc.external_id + ".pdf", get_settings().max_file_bytes)
    original, metadata_file = store.put(body), store.put(metadata, "metadata")
    receipt_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt_path.write_text(json.dumps({"pdf_url": doc.pdf_url, "metadata_url": doc.metadata_url, "pdf_key": original.key,
        "pdf_sha256": original.sha256, "metadata_key": metadata_file.key, "metadata_sha256": metadata_file.sha256,
        "retrieved_at": datetime.now(timezone.utc).isoformat()}, indent=2))
    return body, metadata


def approved_plan(path: Path, digest: str, budget: int):
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Manifest differs from the approved plan")
    plan = BatchPlan.model_validate_json(content)
    if plan.total_bytes > budget or budget > 60_000_000:
        raise ValueError("Batch exceeds approved byte budget")
    return plan


def acquire_batch(path: Path, digest: str, budget: int):
    plan = approved_plan(path, digest, budget)
    for doc in plan.documents:
        acquire_document(doc)
        print(json.dumps({"external_id": doc.external_id, "status": "originals_preserved", "pdf_bytes": doc.pdf_bytes}), flush=True)
        time.sleep(0.1)
    return {"documents_preserved": len(plan.documents), "total_bytes": plan.total_bytes, "manifest_sha256": digest}


def ingest_document(session, source: DatasetSource, doc) -> tuple[Judgment, bool]:
    existing = session.scalar(select(Judgment).where(Judgment.source_id == source.id, Judgment.external_id == doc.external_id))
    if existing:
        # A retry must not silently overwrite a source version that has changed.
        if existing.provenance.get("pdf_etag") != doc.pdf_etag:
            raise ValueError("Source version changed; explicit version review is required")
        storage().read_verified(existing.storage_key, existing.sha256)
        return existing, False
    body, raw_meta = acquire_document(doc)
    if len(raw_meta) != doc.metadata_bytes:
        raise ValueError("Metadata byte count differs from plan")
    meta = json.loads(raw_meta)
    parsed = parse_supreme_metadata(meta, doc.external_id)
    if len(body) != doc.pdf_bytes:
        raise ValueError("PDF byte count differs from plan")
    validate_evidence(body, doc.external_id + ".pdf", get_settings().max_file_bytes)
    original, metadata_file = storage().put(body), storage().put(raw_meta, "metadata")
    existing = session.scalar(select(Judgment).where(Judgment.sha256 == original.sha256))
    if existing:
        session.add(AuditLog(action="duplicate_document", resource_type="judgment", resource_id=existing.id, actor="operator-cli", details={"requested_external_id": doc.external_id, "source_id": str(source.id)}))
        session.commit()
        return existing, False
    settings = get_settings()
    pages, method = extract_pdf(body, settings.max_pdf_pages, settings.ocr_enabled, settings.ocr_timeout_seconds)
    passages = chunk_pages(pages, tokenizer())
    if not passages:
        raise ValueError("No extractable passages")
    judgment = Judgment(source_id=source.id, external_id=doc.external_id, **parsed,
        source_url=doc.pdf_url, metadata_url=doc.metadata_url, sha256=original.sha256, storage_key=original.key,
        byte_size=original.size, page_count=len(pages), extraction_method=method, pipeline_version=PIPELINE_VERSION,
        provenance={"pdf_etag": doc.pdf_etag, "metadata_etag": doc.metadata_etag, "metadata_sha256": metadata_file.sha256, "metadata_storage_key": metadata_file.key,
                    "upstream_path": meta.get("path"), "neutral_citation": meta.get("nc_display"), "source_scraped_at": meta.get("scraped_at"),
                    "retrieved_at": datetime.now(timezone.utc).isoformat(), "license": source.license_id, "attribution": source.attribution,
                    "cleaned_page_sha256": [hashlib.sha256(page.encode()).hexdigest() for page in pages], "tokenizer_revision": settings.embedding_revision})
    session.add(judgment)
    session.flush()
    session.add_all(JudgmentPassage(judgment_id=judgment.id, **passage) for passage in passages)
    session.add(AuditLog(action="judgment_ingested", resource_type="judgment", resource_id=judgment.id, actor="operator-cli", details={"sha256": original.sha256, "source_id": str(source.id), "passages": len(passages)}))
    session.commit()
    return judgment, True


def ingest_batch(session, manifest_path: Path, approved_sha256: str, budget: int, retry_job_id: UUID | None = None) -> dict:
    digest = approved_sha256
    plan = approved_plan(manifest_path, digest, budget)
    source = session.scalar(select(DatasetSource).where(DatasetSource.slug == plan.source_slug))
    if not source or source.status != "verified" or source.license_id != plan.license_id:
        raise ValueError("Source has not passed license and provenance review")
    if retry_job_id:
        job = session.get(ProcessingJob, retry_job_id)
        if not job or job.kind != "judgment_ingestion" or job.status not in {"failed", "processing"} or job.details.get("manifest_sha256") != digest:
            raise ValueError("Retry does not match a recoverable job and manifest")
        job.status, job.processed, job.error_code = "queued", 0, None
    else:
        job = ProcessingJob(kind="judgment_ingestion", source_id=source.id, status="queued", attempts=0, processed=0, total=len(plan.documents), details={"manifest_sha256": digest})
        session.add(job)
    session.commit()
    job_id = job.id
    job.status, job.started_at, job.finished_at = "processing", datetime.now(timezone.utc), None
    job.attempts += 1
    session.commit()
    outcomes, imported, duplicates = [], 0, 0
    for doc in plan.documents:
        try:
            judgment, created = ingest_document(session, source, doc)
            imported += int(created)
            duplicates += int(not created)
            outcomes.append({"external_id": doc.external_id, "judgment_id": str(judgment.id), "status": "imported" if created else "duplicate"})
        except Exception as exc:
            session.rollback()
            outcomes.append({"external_id": doc.external_id, "source_url": doc.pdf_url, "status": "failed", "error_code": type(exc).__name__})
        job = session.get(ProcessingJob, job_id)
        job.processed = len(outcomes)
        job.details = {"manifest_sha256": digest, "imported": imported, "duplicates": duplicates, "outcomes": outcomes}
        session.commit()
        print(json.dumps(outcomes[-1]), flush=True)
        time.sleep(0.1)
    failures = sum(x["status"] == "failed" for x in outcomes)
    job.status = "failed" if failures else "completed"
    job.error_code = "document_failures" if failures else None
    job.finished_at = datetime.now(timezone.utc)
    session.commit()
    return {"job_id": str(job.id), "status": job.status, "imported": imported, "duplicates": duplicates, "failed": failures, "manifest_sha256": digest}


def import_evidence(session, case_id: UUID, path: Path, provenance: str) -> Evidence:
    if not session.get(Case, case_id) or not provenance.strip():
        raise ValueError("Existing authorized case and provenance are required")
    if path.stat().st_size > get_settings().max_file_bytes:
        raise ValueError("Evidence exceeds size limit")
    body = path.read_bytes()
    mime = validate_evidence(body, path.name, get_settings().max_file_bytes)
    original = storage().put(body, "evidence-originals")
    existing = session.scalar(select(Evidence).where(Evidence.case_id == case_id, Evidence.sha256 == original.sha256))
    if existing:
        return existing
    record = Evidence(case_id=case_id, original_filename=path.name, mime_type=mime, byte_size=original.size, sha256=original.sha256, storage_key=original.key, provenance=provenance)
    session.add(record)
    session.flush()
    session.add(AuditLog(action="evidence_preserved", resource_type="evidence", resource_id=record.id, actor="operator-cli", details={"sha256": original.sha256, "case_id": str(case_id)}))
    session.commit()
    return record


def import_provision(session, manifest_path: Path) -> LegalProvision:
    """Import a human-verified exact PDF passage; never invent statutory text."""
    from pydantic import BaseModel, Field, HttpUrl, ConfigDict
    class VerifiedProvision(BaseModel):
        model_config = ConfigDict(extra="forbid")
        source_slug: str
        act_identifier: str = Field(min_length=1, max_length=255)
        act_title: str = Field(min_length=1)
        version: str = Field(min_length=1, max_length=255)
        provision_identifier: str = Field(min_length=1, max_length=100)
        text: str = Field(min_length=10)
        source_url: HttpUrl
        document_path: Path
        page_number: int = Field(gt=0)
        source_document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
        verified_by: str = Field(min_length=1)
    item = VerifiedProvision.model_validate_json(manifest_path.read_bytes())
    source = session.scalar(select(DatasetSource).where(DatasetSource.slug == item.source_slug))
    from urllib.parse import urlsplit
    if not source or source.status != "verified" or not source.license_id or urlsplit(str(item.source_url)).hostname not in {"indiacode.nic.in", "www.indiacode.nic.in", "indiacode.gov.in", "www.indiacode.gov.in"}:
        raise ValueError("An authoritative source with verified access and reuse rights is required")
    if item.document_path.stat().st_size > get_settings().max_file_bytes:
        raise ValueError("Source PDF exceeds size limit")
    body = item.document_path.read_bytes()
    if hashlib.sha256(body).hexdigest() != item.source_document_sha256:
        raise ValueError("Source PDF hash mismatch")
    pages, _ = extract_pdf(body, get_settings().max_pdf_pages)
    from app.documents import clean_text
    if item.page_number > len(pages) or clean_text(item.text) not in pages[item.page_number - 1]:
        raise ValueError("Provision text is not an exact normalized source-page passage")
    original = storage().put(body)
    existing = session.scalar(select(LegalProvision).where(LegalProvision.source_id == source.id, LegalProvision.act_identifier == item.act_identifier, LegalProvision.version == item.version, LegalProvision.provision_identifier == item.provision_identifier))
    text_hash = hashlib.sha256(item.text.encode()).hexdigest()
    if existing:
        if existing.sha256 != text_hash:
            raise ValueError("Existing statute version differs; explicit version review is required")
        return existing
    record = LegalProvision(source_id=source.id, act_identifier=item.act_identifier, act_title=item.act_title, version=item.version, provision_identifier=item.provision_identifier,
        text=item.text, source_url=str(item.source_url), storage_key=original.key, source_document_sha256=original.sha256, page_number=item.page_number, sha256=text_hash)
    session.add(record)
    session.flush()
    session.add(AuditLog(action="provision_verified", resource_type="legal_provision", resource_id=record.id, actor=item.verified_by, details={"source_document_sha256": original.sha256}))
    session.commit()
    return record
