"""Durable report jobs with fenced publication, immutable versions and bounded retry."""
from datetime import timedelta
from uuid import UUID
import importlib.metadata
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from app.analysis_jobs import lease_job, LeaseLost
from app.auth import audit, now
from app.case_api import authorized_case
from app.config import get_settings
from app.database import get_engine
from app.models import ProcessingJob, ReportVersion, User
from app.report_sources import snapshot, canonical, sha, ReportFailure, PIPELINE
from app.storage import PrivateStorage, StorageError
from app.report_pdf import render

KIND = 'case_report'
ERRORS = {
    'integrity_failed': 'Source or report integrity verification failed; no PDF was published.',
    'access_revoked': 'The requester no longer has generation access to this active case.',
    'report_limit_exceeded': 'Report source or output limits exceeded; nothing was silently truncated.',
    'storage_unavailable': 'Private source or report storage is unavailable.',
    'processing_failed': 'Local report generation failed; private details are not exposed.',
    'worker_interrupted': 'The worker was interrupted; its retained attempt may be retried.',
    'job_timeout': 'Report generation exceeded its deadline.',
}


def access(db, user, case_id, write=True):
    if not user or not user.is_active:
        raise HTTPException(404, 'Case not found')
    case = authorized_case(db, user, case_id, write=write)
    if write and user.role not in {'administrator', 'lawyer', 'investigator'}:
        raise HTTPException(403, 'Report generation and annotations require investigator, lawyer or administrator role')
    return case


def context(db, job):
    try:
        user = db.get(User, job.requested_by)
        return user, access(db, user, UUID(job.details['case_id']))
    except (HTTPException, ValueError, KeyError) as exc:
        raise ReportFailure('access_revoked') from exc


def run_analysis(job_id, token):
    run_id = None
    try:
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token)
            if job.kind != KIND:
                raise LeaseLost('Wrong worker kind')
            user, case = context(db, job)
            # Case row lock serializes version assignment, including independent jobs.
            version = (db.scalar(select(func.max(ReportVersion.version)).where(ReportVersion.case_id == case.id)) or 0)+1
            run = ReportVersion(case_id=case.id, job_id=job.id, requested_by=user.id, attempt=job.attempts,
                version=version, title=job.details['title'], pipeline_version=PIPELINE, status='processing', snapshot={})
            db.add(run); db.flush(); run_id = run.id
            job.processed, job.total = 0, 3
            db.commit()
        # One repeatable-read transaction captures a consistent source state. Original files
        # and retained extraction artifacts are independently verified before rendering.
        with Session(get_engine()) as source_db:
            # Externally managed transactions (including rollback verification)
            # retain their caller's isolation; normal workers own an Engine.
            if isinstance(source_db.bind, Engine):
                source_db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
            run = source_db.get(ReportVersion, run_id)
            job = source_db.get(ProcessingJob, job_id)
            user = source_db.get(User, job.requested_by)
            case = authorized_case(source_db, user, run.case_id)
            content = snapshot(source_db, case, run.id, run.version, run.title, user.id, now().isoformat())
            content['generator'] = {'name': 'ReportLab', 'version': importlib.metadata.version('reportlab'), 'license': 'BSD'}
        raw = canonical(content)
        snapshot_hash = sha(raw)
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token); context(db, job)
            job.processed = 1; db.commit()
        pdf, pages = render(content, snapshot_hash)
        store = PrivateStorage(get_settings().private_root, 50_000_000)
        source_file = store.put(raw, 'derived')
        pdf_file = store.put(pdf, 'derived')
        # A stale child may leave an unreferenced immutable blob, but can never publish it.
        with Session(get_engine()) as db:
            job = lease_job(db, job_id, token); user, case = context(db, job)
            run = db.get(ReportVersion, run_id)
            run.snapshot, run.snapshot_sha256, run.snapshot_key = content, source_file.sha256, source_file.key
            run.pdf_key, run.pdf_sha256, run.byte_size, run.page_count = pdf_file.key, pdf_file.sha256, pdf_file.size, pages
            run.status, run.finished_at = 'completed', now()
            job.status, job.processed, job.finished_at, job.lease_expires_at = 'completed', 3, now(), None
            audit(db, user, 'report.completed', 'case', case.id, report_id=str(run.id), version=run.version,
                pdf_sha256=run.pdf_sha256, snapshot_sha256=run.snapshot_sha256, pages=pages)
            db.commit()
        return True
    except LeaseLost:
        return False
    except ReportFailure as exc:
        fail_job(job_id, token, exc.code, exc.retryable, run_id)
    except StorageError:
        fail_job(job_id, token, 'integrity_failed', False, run_id)
    except OSError:
        fail_job(job_id, token, 'storage_unavailable', True, run_id)
    except Exception:
        fail_job(job_id, token, 'processing_failed', True, run_id)
    return False


def fail_job(job_id, token, code, retryable, run_id=None):
    with Session(get_engine()) as db:
        try:
            job = lease_job(db, job_id, token)
        except LeaseLost:
            return
        if job.kind != KIND:
            return
        run = db.get(ReportVersion, run_id) if run_id else db.scalar(select(ReportVersion).where(ReportVersion.job_id == job.id, ReportVersion.attempt == job.attempts))
        if run and run.status != 'completed':
            run.status, run.error_code, run.finished_at = 'failed', code, now()
        job.error_code = code if code in ERRORS else 'processing_failed'
        if retryable and job.attempts < job.max_attempts:
            job.status, job.processed, job.total = 'queued', 0, 0
            job.next_attempt_at = now()+timedelta(seconds=min(30, 2**job.attempts))
        else:
            job.status, job.finished_at = 'failed', now()
        job.lease_expires_at = None
        audit(db, db.get(User, job.requested_by), 'report.failed', 'case', UUID(job.details['case_id']), job_id=str(job.id), error_code=job.error_code)
        db.commit()
