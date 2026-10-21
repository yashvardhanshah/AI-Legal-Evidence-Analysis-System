"""Durable private document jobs, immutable attempt history and fenced publication."""
from datetime import timedelta
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ner_model
from app.analysis_extraction import AnalysisFailure, extract_pages, page_count
from app.analysis_nlp import RULES_VERSION, entities
from app.auth import audit, now
from app.case_api import authorized_case
from app.config import get_settings
from app.database import get_engine
from app.models import AnalysisEntity, AnalysisModel, AnalysisPage, Evidence, EvidenceAnalysis, EvidenceArtifact, ProcessingJob, User
from app.storage import PrivateStorage, StorageError

PIPELINE_VERSION = "document-intelligence-v2"
SUPPORTED = {"application/pdf", "image/png", "image/jpeg"}
ERRORS = {
    "unsupported_document": "Only PDF, PNG and JPEG document analysis is supported in Phase 4.",
    "invalid_document": "The document is invalid, encrypted or unreadable.",
    "integrity_failed": "The original failed SHA-256 verification; processing was stopped.",
    "storage_unavailable": "The preserved original is unavailable; contact the operator.",
    "model_unavailable": "The approved local NER model is unavailable or failed verification.",
    "ocr_failed": "Local OCR failed. The worker may retry within its bounded attempt limit.",
    "ocr_timeout": "A page exceeded the configured OCR time limit.",
    "ocr_output_invalid": "OCR returned an unreadable result.",
    "no_text": "No text could be extracted or recognized; no entities or findings were published.",
    "access_revoked": "The requesting user no longer has write access to this active case.",
    "page_limit_exceeded": "The document exceeds the configured analysis page limit.",
    "text_limit_exceeded": "Extracted text exceeds the configured analysis limit; nothing was silently truncated.",
    "render_limit_exceeded": "A page exceeds the configured rendering pixel limit.",
    "pdf_text_extraction_failed": "A PDF page could not be extracted safely.",
    "job_timeout": "The document exceeded the configured processing time limit.",
    "worker_interrupted": "The worker was interrupted; this attempt was retained and may be retried.",
    "processing_failed": "Document processing failed; private exception details are not exposed.",
}


class LeaseLost(RuntimeError):
    pass


def lease_job(db, job_id, token):
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id).with_for_update())
    if not job or job.status != "processing" or job.lease_token != token:
        raise LeaseLost("Job ownership changed")
    return job


def check_access(db, job):
    user = db.get(User, job.requested_by) if job.requested_by else None
    evidence = db.get(Evidence, job.evidence_id) if job.evidence_id else None
    try:
        if not user or not user.is_active or not evidence:
            raise HTTPException(404)
        authorized_case(db, user, evidence.case_id, write=True)
    except HTTPException as exc:
        raise AnalysisFailure("access_revoked") from exc
    return user, evidence


def registry(db):
    settings = get_settings()
    receipt = ner_model.verify(settings.private_root)
    software = {name: importlib.metadata.version(name) for name in ("transformers", "torch", "pypdf", "pypdfium2", "Pillow")}
    tesseract = subprocess.check_output(["tesseract", "--version"], text=True, timeout=10).splitlines()[0]
    candidates = [Path("/usr/share/tesseract-ocr/5/tessdata/eng.traineddata")]
    import os
    if os.environ.get("TESSDATA_PREFIX"):
        candidates.insert(0, Path(os.environ["TESSDATA_PREFIX"])/"eng.traineddata")
    traineddata = next((path for path in candidates if path.is_file()), None)
    if traineddata is None:
        raise AnalysisFailure("ocr_failed", True)
    ocr_hash = ner_model.file_hash(traineddata)
    definitions = [dict(name=ner_model.MODEL, revision=ner_model.REVISION, task="named_entity_recognition", license_id="Apache-2.0",
                        source_url=f"https://huggingface.co/{ner_model.MODEL}/tree/{ner_model.REVISION}", byte_size=ner_model.TOTAL_BYTES,
                        file_hashes={name: item["sha256"] for name, item in receipt["files"].items()}, software=software),
                   dict(name="tesseract/eng.traineddata", revision=ocr_hash, task="english_ocr", license_id="Apache-2.0",
                        source_url="https://github.com/tesseract-ocr/tessdata_fast", byte_size=traineddata.stat().st_size,
                        file_hashes={"eng.traineddata": ocr_hash}, software={"tesseract": tesseract, **software})]
    output = []
    for definition in definitions:
        model = db.scalar(select(AnalysisModel).where(AnalysisModel.name == definition["name"], AnalysisModel.revision == definition["revision"]))
        if not model:
            model = AnalysisModel(**definition)
            db.add(model)
            db.flush()
        output.append(model)
    return output


def run_analysis(job_id, token):
    settings = get_settings()
    run_id = None
    try:
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token)
            user, evidence = check_access(db, job)
            run = EvidenceAnalysis(id=uuid4(), job_id=job.id, evidence_id=evidence.id, attempt=job.attempts,
                                   status="processing", original_sha256=evidence.sha256, pipeline_version=PIPELINE_VERSION,
                                   settings={"rules_version": RULES_VERSION, "ocr_language": "eng", "ocr_thread_limit": 1, "render_dpi": settings.analysis_render_dpi,
                                             "max_pages": settings.analysis_max_pages, "max_chars": settings.analysis_max_chars,
                                             "text_coordinates": "zero-based Python Unicode character offsets within persisted page text; end exclusive",
                                             "normalization": "CRLF/CR to LF; NUL to U+FFFD; no spelling correction",
                                             "ocr_layout": "TSV word order, spaces within lines, newline between TSV lines",
                                             "ocr_confidence": "character-weighted mean Tesseract word confidence, 0-100; not calibrated accuracy"})
            db.add(run)
            db.flush()
            run_id = run.id
            key, expected, mime = evidence.storage_key, evidence.sha256, evidence.mime_type
            db.commit()  # Do not hold row locks during file parsing/inference.
        if mime not in SUPPORTED:
            raise AnalysisFailure("unsupported_document")
        store = PrivateStorage(settings.private_root, settings.max_file_bytes)
        try:
            raw = store.read_verified(key, expected)
        except StorageError as exc:
            raise AnalysisFailure("integrity_failed") from exc
        except OSError as exc:
            raise AnalysisFailure("storage_unavailable", True) from exc
        count = page_count(raw, mime, settings)
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token)
            check_access(db, job)
            ner, ocr = registry(db)
            run = db.get(EvidenceAnalysis, run_id)
            run.ner_model_id, run.ocr_model_id = ner.id, ocr.id
            ner_id = ner.id
            job.total, job.processed = count, 0
            db.commit()
        artifact_pages, character_count = [], 0
        for extracted in extract_pages(raw, mime, settings):
            predicted = entities(extracted["text"])
            character_count += len(extracted["text"].strip())
            with Session(get_engine()) as db:
                job = lease_job(db, job_id, token)
                check_access(db, job)
                page = AnalysisPage(id=uuid4(), analysis_id=run_id, **extracted)
                db.add(page)
                db.flush()
                for entity in predicted:
                    db.add(AnalysisEntity(page_id=page.id, model_id=ner_id if entity["extractor"] == "ner" else None, **entity))
                job.processed = extracted["page_number"]
                db.commit()
            artifact_pages.append({**extracted, "entities": predicted})
        if character_count == 0:
            raise AnalysisFailure("no_text")
        try:
            store.read_verified(key, expected)  # Verify again before publishing a completed result.
        except (OSError, StorageError) as exc:
            raise AnalysisFailure("integrity_failed") from exc
        body = json.dumps({"pipeline_version": PIPELINE_VERSION, "original_sha256": expected,
                           "ner_model": ner_model.MODEL, "ner_revision": ner_model.REVISION,
                           "analysis_id": str(run_id), "pages": artifact_pages}, ensure_ascii=False).encode()
        derived = PrivateStorage(settings.private_root, 50_000_000).put(body, "derived")
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token)
            user, evidence = check_access(db, job)
            artifact = EvidenceArtifact(evidence_id=evidence.id, kind="analysis-"+str(run_id), storage_key=derived.key,
                                        sha256=derived.sha256, byte_size=derived.size, producer_version=PIPELINE_VERSION)
            db.add(artifact)
            db.flush()
            run = db.get(EvidenceAnalysis, run_id)
            run.artifact_id, run.status, run.finished_at = artifact.id, "completed", now()
            run.warnings = sorted({warning for page in artifact_pages for warning in page["warnings"]})
            job.status, job.finished_at, job.error_code = "completed", now(), None
            job.lease_expires_at = None
            audit(db, user, "analysis.completed", "case", evidence.case_id, evidence_id=str(evidence.id), analysis_id=str(run.id), original_sha256=expected)
            db.commit()
        return True
    except LeaseLost:
        return False
    except ner_model.ModelUnavailable:
        fail_job(job_id, token, "model_unavailable", False, run_id)
    except AnalysisFailure as exc:
        fail_job(job_id, token, exc.code, exc.retryable, run_id)
    except Exception:
        # Never expose parser/model exceptions that might contain evidence text.
        fail_job(job_id, token, "processing_failed", True, run_id)
    return False


def fail_job(job_id, token, code, retryable, run_id=None):
    with Session(get_engine()) as db:
        try:
            job = lease_job(db, job_id, token)
        except LeaseLost:
            return
        run = db.get(EvidenceAnalysis, run_id) if run_id else db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job.id, EvidenceAnalysis.attempt == job.attempts))
        if run:
            run.status, run.error_code, run.finished_at = "failed", code, now()
        job.error_code = code if code in ERRORS else "processing_failed"
        if retryable and job.attempts < job.max_attempts:
            job.status, job.processed, job.total = "queued", 0, 0
            job.next_attempt_at = now()+timedelta(seconds=min(30, 2**job.attempts))
        else:
            job.status, job.finished_at = "failed", now()
        job.lease_expires_at = None
        evidence = db.get(Evidence, job.evidence_id)
        if evidence:
            audit(db, db.get(User, job.requested_by), "analysis.failed", "case", evidence.case_id, job_id=str(job.id), error_code=job.error_code, attempt=job.attempts)
        db.commit()
