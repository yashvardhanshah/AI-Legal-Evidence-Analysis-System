"""Authenticated analysis commands and provenance-bound private results."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis_jobs import ERRORS, PIPELINE_VERSION, SUPPORTED
from app.auth import audit, current_user, now
from app.case_api import authorized_case, authorized_evidence
from app.config import get_settings
from app.library_api import session_dependency
from app.models import AnalysisEntity, AnalysisModel, AnalysisPage, EvidenceAnalysis, EvidenceArtifact, ProcessingJob, User
from app.storage import PrivateStorage, StorageError

router = APIRouter(prefix="/api/v1/cases/{case_id}/evidence/{evidence_id}", tags=["Private document analysis"])


def job_fields(job):
    return {"id": job.id, "evidence_id": job.evidence_id, "status": job.status, "attempts": job.attempts,
            "max_attempts": job.max_attempts, "processed": job.processed, "total": job.total,
            "error_code": job.error_code, "message": ERRORS.get(job.error_code) if job.error_code else None,
            "next_attempt_at": job.next_attempt_at, "created_at": job.created_at, "started_at": job.started_at,
            "finished_at": job.finished_at, "pipeline_version": job.details.get("pipeline_version")}


def scoped_job(db, user, case_id, evidence_id, job_id):
    authorized_evidence(db, user, case_id, evidence_id)
    job = db.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id, ProcessingJob.evidence_id == evidence_id, ProcessingJob.kind == "evidence_analysis"))
    if not job:
        raise HTTPException(404, "Analysis job not found")
    return job


def scoped_run(db, user, case_id, evidence_id, analysis_id, complete=False):
    authorized_evidence(db, user, case_id, evidence_id)
    run = db.scalar(select(EvidenceAnalysis).where(EvidenceAnalysis.id == analysis_id, EvidenceAnalysis.evidence_id == evidence_id))
    if not run:
        raise HTTPException(404, "Analysis not found")
    if complete and run.status != "completed":
        raise HTTPException(409, "This attempt has no completed published result")
    return run


def run_fields(db, run):
    models = []
    for model_id in (run.ner_model_id, run.ocr_model_id):
        model = db.get(AnalysisModel, model_id) if model_id else None
        if model:
            models.append({"id": model.id, "name": model.name, "revision": model.revision, "license_id": model.license_id,
                           "source_url": model.source_url, "byte_size": model.byte_size, "software": model.software, "file_hashes": model.file_hashes})
    return {"id": run.id, "job_id": run.job_id, "evidence_id": run.evidence_id, "attempt": run.attempt, "status": run.status,
            "original_sha256": run.original_sha256, "pipeline_version": run.pipeline_version, "settings": run.settings,
            "warnings": run.warnings, "error_code": run.error_code, "message": ERRORS.get(run.error_code),
            "created_at": run.created_at, "finished_at": run.finished_at, "models": models,
            "page_count": db.scalar(select(func.count()).select_from(AnalysisPage).where(AnalysisPage.analysis_id == run.id))}


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reanalyze: bool = False


@router.post("/analysis", status_code=202)
def analyze(case_id: UUID, evidence_id: UUID, response: Response, body: AnalyzeRequest = AnalyzeRequest(),
            user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id, write=True)
    evidence = authorized_evidence(db, user, case_id, evidence_id)
    if evidence.mime_type not in SUPPORTED:
        raise HTTPException(422, ERRORS["unsupported_document"])
    # Case row lock serializes trigger/retry requests, with a DB unique index as defence in depth.
    existing = db.scalar(select(ProcessingJob).where(ProcessingJob.evidence_id == evidence_id, ProcessingJob.kind == "evidence_analysis",
                                                    ProcessingJob.status.in_(["queued", "processing"])))
    if existing:
        return job_fields(existing)
    if not body.reanalyze:
        completed = db.scalar(select(ProcessingJob).where(ProcessingJob.evidence_id == evidence_id, ProcessingJob.kind == "evidence_analysis",
                                                          ProcessingJob.status == "completed").order_by(ProcessingJob.created_at.desc()))
        if completed and completed.details.get("pipeline_version") == PIPELINE_VERSION:
            response.status_code = 200
            return job_fields(completed)
    active = db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind == "evidence_analysis",
                        ProcessingJob.requested_by == user.id, ProcessingJob.status.in_(["queued", "processing"])))
    queued = db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind == "evidence_analysis", ProcessingJob.status.in_(["queued", "processing"])))
    if active >= 3 or queued >= 100:
        raise HTTPException(429, "Analysis queue limit reached; wait for existing jobs")
    job = ProcessingJob(kind="evidence_analysis", evidence_id=evidence.id, requested_by=user.id, status="queued", details={"pipeline_version": PIPELINE_VERSION})
    db.add(job)
    db.flush()
    audit(db, user, "analysis.queued", "case", case_id, evidence_id=str(evidence.id), job_id=str(job.id))
    db.commit()
    return job_fields(job)


@router.get("/analysis-jobs")
def jobs(case_id: UUID, evidence_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
         user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_evidence(db, user, case_id, evidence_id)
    query = select(ProcessingJob).where(ProcessingJob.kind == "evidence_analysis", ProcessingJob.evidence_id == evidence_id)
    return {"items": [job_fields(job) for job in db.scalars(query.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit))]}


@router.get("/analysis-jobs/{job_id}")
def job_detail(case_id: UUID, evidence_id: UUID, job_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    job = scoped_job(db, user, case_id, evidence_id, job_id)
    runs = db.scalars(select(EvidenceAnalysis).where(EvidenceAnalysis.job_id == job.id).order_by(EvidenceAnalysis.attempt.desc()))
    return {**job_fields(job), "runs": [run_fields(db, run) for run in runs]}


@router.post("/analysis-jobs/{job_id}/retry", status_code=202)
def retry(case_id: UUID, evidence_id: UUID, job_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id, write=True)
    job = scoped_job(db, user, case_id, evidence_id, job_id)
    if job.status != "failed" or job.attempts >= job.max_attempts:
        raise HTTPException(409, "Only failed jobs below their attempt limit can be retried")
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.evidence_id == evidence_id, ProcessingJob.kind == "evidence_analysis", ProcessingJob.status.in_(["queued", "processing"])))
    if active:
        raise HTTPException(409, "An analysis job is already active for this evidence")
    job.status, job.processed, job.total = "queued", 0, 0
    job.requested_by, job.next_attempt_at, job.finished_at = user.id, None, None
    audit(db, user, "analysis.retry_requested", "case", case_id, job_id=str(job.id))
    db.commit()
    return job_fields(job)


@router.get("/analyses")
def analyses(case_id: UUID, evidence_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_evidence(db, user, case_id, evidence_id)
    rows = db.scalars(select(EvidenceAnalysis).where(EvidenceAnalysis.evidence_id == evidence_id).order_by(EvidenceAnalysis.created_at.desc()).offset(offset).limit(limit))
    return {"items": [run_fields(db, run) for run in rows]}


@router.get("/analyses/{analysis_id}")
def analysis_detail(case_id: UUID, evidence_id: UUID, analysis_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    run = scoped_run(db, user, case_id, evidence_id, analysis_id)
    audit(db, user, "analysis.read", "case", case_id, analysis_id=str(run.id), evidence_id=str(evidence_id))
    db.commit()
    return run_fields(db, run)


@router.get("/analyses/{analysis_id}/pages")
def pages(case_id: UUID, evidence_id: UUID, analysis_id: UUID, limit: int = Query(10, ge=1, le=25), offset: int = Query(0, ge=0),
          user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    scoped_run(db, user, case_id, evidence_id, analysis_id, True)
    query = select(AnalysisPage).where(AnalysisPage.analysis_id == analysis_id)
    rows = db.scalars(query.order_by(AnalysisPage.page_number).offset(offset).limit(limit))
    return {"items": [{"id": page.id, "page_number": page.page_number, "extraction_method": page.extraction_method,
                       "text_sha256": page.text_sha256, "characters": len(page.text), "ocr_confidence": page.ocr_confidence,
                       "warnings": page.warnings} for page in rows], "total": db.scalar(select(func.count()).select_from(query.subquery()))}


@router.get("/analyses/{analysis_id}/pages/{page_number}")
def page_detail(case_id: UUID, evidence_id: UUID, analysis_id: UUID, page_number: int,
                user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    scoped_run(db, user, case_id, evidence_id, analysis_id, True)
    page = db.scalar(select(AnalysisPage).where(AnalysisPage.analysis_id == analysis_id, AnalysisPage.page_number == page_number))
    if not page:
        raise HTTPException(404, "Analysis page not found")
    rows = db.scalars(select(AnalysisEntity).where(AnalysisEntity.page_id == page.id).order_by(AnalysisEntity.char_start, AnalysisEntity.char_end))
    audit(db, user, "analysis.page_read", "case", case_id, analysis_id=str(analysis_id), page_number=page_number)
    db.commit()
    return {"id": page.id, "page_number": page.page_number, "extraction_method": page.extraction_method, "text": page.text,
            "text_sha256": page.text_sha256, "ocr_confidence": page.ocr_confidence, "width": page.width, "height": page.height,
            "ocr_words": page.ocr_words, "warnings": page.warnings,
            "entities": [{"id": e.id, "label": e.label, "text": e.text, "char_start": e.char_start, "char_end": e.char_end,
                          "extractor": e.extractor, "score": e.score, "model_id": e.model_id, "provenance": e.provenance} for e in rows]}


@router.get("/analyses/{analysis_id}/download")
def download_analysis(case_id: UUID, evidence_id: UUID, analysis_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    run = scoped_run(db, user, case_id, evidence_id, analysis_id, True)
    artifact = db.get(EvidenceArtifact, run.artifact_id)
    if not artifact or artifact.evidence_id != evidence_id:
        raise HTTPException(409, "Derived artifact unavailable")
    try:
        body = PrivateStorage(get_settings().private_root).read_verified(artifact.storage_key, artifact.sha256)
    except (OSError, StorageError) as exc:
        raise HTTPException(409, "Derived artifact failed integrity verification") from exc
    audit(db, user, "analysis.download", "case", case_id, analysis_id=str(run.id))
    db.commit()
    return Response(body, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="analysis-{run.id}.json"',
                     "Cache-Control": "no-store", "X-Content-SHA256": artifact.sha256, "X-Content-Type-Options": "nosniff"})
