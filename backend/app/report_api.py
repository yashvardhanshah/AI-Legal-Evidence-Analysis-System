"""Every report route is authenticated and scoped to the current case authorization."""
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import Response as ByteResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app import report_jobs
from app.auth import audit, current_user
from app.case_api import authorized_case
from app.config import get_settings
from app.library_api import session_dependency
from app.models import User, ProcessingJob, ReportVersion, ReportReview, AuditLog
from app.report_sources import verify_snapshot, ReportFailure
from app.storage import PrivateStorage, StorageError

router = APIRouter(prefix='/api/v1/cases/{case_id}', tags=['Private investigation reports'])


def scoped_job(db, user, case_id, job_id):
    authorized_case(db, user, case_id)
    job = db.get(ProcessingJob, job_id)
    if not job or job.kind != report_jobs.KIND or job.details.get('case_id') != str(case_id):
        raise HTTPException(404, 'Report job not found')
    return job


def scoped_report(db, user, case_id, report_id, complete=False):
    authorized_case(db, user, case_id)
    report = db.get(ReportVersion, report_id)
    if not report or report.case_id != case_id:
        raise HTTPException(404, 'Report not found')
    if complete and report.status != 'completed':
        raise HTTPException(409, 'Only completed versions can be inspected or reviewed')
    return report


def job_fields(job):
    return dict(id=job.id, status=job.status, attempts=job.attempts, max_attempts=job.max_attempts,
        processed=job.processed, total=job.total, error_code=job.error_code, message=report_jobs.ERRORS.get(job.error_code),
        created_at=job.created_at, finished_at=job.finished_at)


def reviews(db, report):
    return list(db.scalars(select(ReportReview).where(ReportReview.report_id == report.id).order_by(ReportReview.created_at, ReportReview.id)))


def review_fields(row):
    return {key: getattr(row, key) for key in 'id report_id reviewer_id reviewer_name reviewer_role disposition note pdf_sha256 snapshot_sha256 created_at'.split()}


def report_fields(db, report):
    history = reviews(db, report)
    decision = next((r.disposition for r in history if r.disposition != 'note'), 'draft') if report.status == 'completed' else 'unavailable'
    return {**{key: getattr(report, key) for key in 'id case_id job_id version attempt requested_by status title pipeline_version pdf_sha256 snapshot_sha256 byte_size page_count error_code created_at finished_at'.split()},
        'review_status': decision, 'is_approved': decision == 'approved', 'approval_embedded_in_pdf': False,
        'notice': 'Review-copy PDF. Human approval is external and hash bound; an unapproved report is not a finalized investigation. Verified statutory analysis is unavailable.',
        'reviews': [review_fields(r) for r in history]}


def capacity(db, user):
    query = select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind == report_jobs.KIND, ProcessingJob.status.in_(['queued', 'processing']))
    if db.scalar(query) >= 30 or db.scalar(query.where(ProcessingJob.requested_by == user.id)) >= 2:
        raise HTTPException(429, 'Report queue capacity reached')


def verified(report, pdf=False):
    try:
        raw = verify_snapshot(report)
        if pdf:
            raw = PrivateStorage(get_settings().private_root).read_verified(report.pdf_key, report.pdf_sha256)
            if len(raw) != report.byte_size:
                raise ReportFailure('integrity_failed')
        return raw
    except (ReportFailure, StorageError, OSError, ValueError, TypeError) as exc:
        raise HTTPException(409, 'Report integrity verification failed') from exc


class Generate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(default='Evidence-grounded investigation report', min_length=3, max_length=300)
    new_version: bool = False


@router.post('/report-jobs', status_code=202)
def generate(case_id: UUID, body: Generate, response: Response, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report_jobs.access(db, user, case_id)
    # Repeated clicks reuse an active job; completed snapshots require explicit new version.
    existing = db.scalar(select(ProcessingJob).where(ProcessingJob.kind == report_jobs.KIND,
        ProcessingJob.details['case_id'].astext == str(case_id), ProcessingJob.details['title'].astext == body.title,
        ProcessingJob.status.in_(['queued', 'processing'] if body.new_version else ['queued', 'processing', 'completed'])).order_by(ProcessingJob.created_at.desc()).limit(1))
    if existing:
        response.status_code = 200 if existing.status == 'completed' else 202
        return job_fields(existing)
    capacity(db, user)
    job = ProcessingJob(kind=report_jobs.KIND, requested_by=user.id, details=dict(case_id=str(case_id), title=body.title, pipeline_version=report_jobs.PIPELINE))
    db.add(job); db.flush()
    audit(db, user, 'report.queued', 'case', case_id, job_id=str(job.id)); db.commit()
    return job_fields(job)


@router.get('/report-jobs')
def jobs(case_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id)
    query = select(ProcessingJob).where(ProcessingJob.kind == report_jobs.KIND, ProcessingJob.details['case_id'].astext == str(case_id))
    return dict(items=[job_fields(j) for j in db.scalars(query.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit))])


@router.get('/report-jobs/{job_id}')
def job_detail(case_id: UUID, job_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    job = scoped_job(db, user, case_id, job_id)
    return {**job_fields(job), 'reports': [report_fields(db, r) for r in db.scalars(select(ReportVersion).where(ReportVersion.job_id == job.id).order_by(ReportVersion.attempt.desc()))]}


@router.post('/report-jobs/{job_id}/retry', status_code=202)
def retry(case_id: UUID, job_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report_jobs.access(db, user, case_id)
    job = scoped_job(db, user, case_id, job_id)
    if job.status != 'failed' or job.attempts >= job.max_attempts:
        raise HTTPException(409, 'Only failed jobs below the attempt cap can retry')
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.kind == report_jobs.KIND, ProcessingJob.details['case_id'].astext == str(case_id), ProcessingJob.status.in_(['queued', 'processing'])))
    if active:
        raise HTTPException(409, 'A report generation request is already active for this case')
    capacity(db, user)
    job.status, job.requested_by, job.next_attempt_at, job.finished_at = 'queued', user.id, None, None
    job.processed, job.total = 0, 0
    audit(db, user, 'report.retry', 'case', case_id, job_id=str(job.id)); db.commit()
    return job_fields(job)


@router.get('/reports')
def reports(case_id: UUID, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    authorized_case(db, user, case_id)
    query = select(ReportVersion).where(ReportVersion.case_id == case_id)
    return dict(items=[report_fields(db, r) for r in db.scalars(query.order_by(ReportVersion.version.desc()).offset(offset).limit(limit))],
        total=db.scalar(select(func.count()).select_from(query.subquery())))


@router.get('/reports/{report_id}')
def metadata(case_id: UUID, report_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report = scoped_report(db, user, case_id, report_id)
    if report.status == 'completed':
        verified(report, True)
    return report_fields(db, report)


@router.get('/reports/{report_id}/provenance')
def provenance(case_id: UUID, report_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report = scoped_report(db, user, case_id, report_id, True)
    verified(report)
    audit(db, user, 'report.provenance_read', 'case', case_id, report_id=str(report.id)); db.commit()
    return dict(report=report_fields(db, report), snapshot=report.snapshot)


@router.get('/reports/{report_id}/snapshot')
def download_snapshot(case_id: UUID, report_id: UUID, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report = scoped_report(db, user, case_id, report_id, True)
    raw = verified(report)
    audit(db, user, 'report.snapshot_downloaded', 'case', case_id, report_id=str(report.id)); db.commit()
    return ByteResponse(raw, media_type='application/json', headers={'Content-Disposition': f'attachment; filename="report-{report.id}-snapshot.json"', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/reports/{report_id}/pdf')
def download_pdf(case_id: UUID, report_id: UUID, preview: bool = False, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report = scoped_report(db, user, case_id, report_id, True)
    raw = verified(report, True)
    audit(db, user, 'report.pdf_downloaded', 'case', case_id, report_id=str(report.id), pdf_sha256=report.pdf_sha256, preview=preview); db.commit()
    return ByteResponse(raw, media_type='application/pdf', headers={'Content-Disposition': f'{"inline" if preview else "attachment"}; filename="report-{report.id}-v{report.version}.pdf"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox"})


@router.get('/reports/{report_id}/audit')
def history(case_id: UUID, report_id: UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report = scoped_report(db, user, case_id, report_id)
    query = select(AuditLog).where(AuditLog.resource_type == 'case', AuditLog.resource_id == case_id,
        (AuditLog.details['report_id'].astext == str(report_id)) | (AuditLog.details['job_id'].astext == str(report.job_id)), AuditLog.action.like('report.%'))
    return dict(items=[dict(id=a.id, action=a.action, actor=a.actor, details=a.details, created_at=a.created_at) for a in db.scalars(query.order_by(AuditLog.created_at, AuditLog.id).offset(offset).limit(limit))])


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    disposition: Literal['note', 'approved', 'rejected']
    note: str = Field(min_length=3, max_length=3000)
    pdf_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    snapshot_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')


@router.post('/reports/{report_id}/reviews', status_code=201)
def review(case_id: UUID, report_id: UUID, body: Review, user: User = Depends(current_user), db: Session = Depends(session_dependency)):
    report_jobs.access(db, user, case_id)
    report = scoped_report(db, user, case_id, report_id, True)
    if body.disposition != 'note' and user.role not in {'administrator', 'lawyer'}:
        raise HTTPException(403, 'Explicit approval or rejection requires an authorized lawyer or administrator')
    existing_reviews = reviews(db, report)
    if any(r.disposition != 'note' for r in existing_reviews):
        raise HTTPException(409, 'This report has a terminal review decision; generate a new version for further review')
    if len(existing_reviews) >= 100:
        raise HTTPException(429, 'Report review history limit reached; generate a new version')
    if body.pdf_sha256 != report.pdf_sha256 or body.snapshot_sha256 != report.snapshot_sha256:
        raise HTTPException(409, 'Review hashes do not match the inspected report version')
    verified(report, True)
    entry = ReportReview(report_id=report.id, reviewer_id=user.id, reviewer_name=user.display_name, reviewer_role=user.role, **body.model_dump())
    db.add(entry); db.flush()
    audit(db, user, 'report.reviewed', 'case', case_id, report_id=str(report.id), review_id=str(entry.id), disposition=entry.disposition,
        pdf_sha256=report.pdf_sha256, snapshot_sha256=report.snapshot_sha256)
    db.commit()
    return review_fields(entry)
