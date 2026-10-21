"""Separate PostgreSQL-backed worker; no analysis runs in API request handlers."""
import argparse
import os
import signal
from datetime import timedelta
import subprocess
import sys
import time
from uuid import UUID, uuid4

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.analysis_jobs import fail_job, now, run_analysis
from app.config import get_settings
from app.database import get_engine
from app.models import EvidenceAnalysis, VisualAnalysis, ResearchRun, ProcessingJob, SystemMetadata

HEARTBEAT = "analysis_worker_heartbeat"

def heartbeat_key(kind):
    return {'evidence_analysis':HEARTBEAT,'visual_analysis':'visual_worker_heartbeat','legal_research':'research_worker_heartbeat'}[kind]


def heartbeat(kind='evidence_analysis'):
    key = heartbeat_key(kind)
    with Session(get_engine()) as db:
        row = db.get(SystemMetadata, key)
        if not row:
            db.add(SystemMetadata(key=key, value=now().isoformat()))
        else:
            row.value = now().isoformat()
        db.commit()


def healthy(kind='evidence_analysis'):
    from datetime import datetime
    try:
        with Session(get_engine()) as db:
            row = db.get(SystemMetadata, heartbeat_key(kind))
            return bool(row and (now()-datetime.fromisoformat(row.value)).total_seconds() < 45)
    except (SQLAlchemyError, ValueError):
        # Startup/restart failures must not emit connection details into health logs.
        return False


def claim(db, guard, kind='evidence_analysis'):
    clock = now()
    query = select(ProcessingJob).where(ProcessingJob.kind == kind,
        or_((ProcessingJob.status == "queued") & or_(ProcessingJob.next_attempt_at.is_(None), ProcessingJob.next_attempt_at <= clock),
            (ProcessingJob.status == "processing") & (ProcessingJob.lease_expires_at < clock)))
    candidates = db.scalars(query.order_by(ProcessingJob.created_at).limit(10).with_for_update(skip_locked=True))
    for job in candidates:
        lock_key = int.from_bytes(job.id.bytes[:8], "big", signed=True)
        if not guard.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}):
            continue
        if job.status == "processing":
            record = {'evidence_analysis':EvidenceAnalysis,'visual_analysis':VisualAnalysis,'legal_research':ResearchRun}[kind]
            prior = db.scalar(select(record).where(record.job_id == job.id, record.attempt == job.attempts))
            if prior and prior.status == "processing":
                prior.status, prior.error_code, prior.finished_at = "interrupted", "worker_interrupted", clock
        if job.attempts >= job.max_attempts:
            job.status, job.error_code, job.finished_at = "failed", "worker_interrupted", clock
            guard.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            continue
        job.status, job.attempts, job.lease_token = "processing", job.attempts+1, uuid4()
        job.lease_expires_at = clock+timedelta(seconds=get_settings().analysis_job_timeout+30)
        job.started_at, job.finished_at, job.error_code, job.next_attempt_at = clock, None, None, None
        job.processed, job.total = 0, 0
        identifier, token = job.id, job.lease_token
        db.commit()
        return identifier, token, lock_key
    db.commit()
    return None


def process_once(kind='evidence_analysis'):
    failure = fail_job
    if kind == 'visual_analysis':
        from app.visual_jobs import fail_job as failure
    elif kind == 'legal_research':
        from app.research_jobs import fail_job as failure
    # Dedicated connection holds a session advisory lock across child processing.
    with get_engine().connect().execution_options(isolation_level="AUTOCOMMIT") as guard:
        with Session(get_engine()) as db:
            claimed = claim(db, guard, kind)
        if not claimed:
            return False
        identifier, token, lock_key = claimed
        child = None
        try:
            child = subprocess.Popen([sys.executable, "-m", "app.analysis_worker", "--kind", kind, "--execute", str(identifier), "--lease", str(token)],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=os.name != "nt")
            deadline, next_heartbeat = time.monotonic()+get_settings().analysis_job_timeout, 0
            while child.poll() is None:
                if time.monotonic() >= deadline:
                    terminate(child)
                    child.wait()
                    failure(identifier, token, "job_timeout", True)
                    break
                if time.monotonic() >= next_heartbeat:
                    heartbeat(kind)
                    next_heartbeat = time.monotonic()+10
                time.sleep(0.5)
            else:
                if child.returncode != 0:
                    failure(identifier, token, "worker_interrupted", True)
        finally:
            if child and child.poll() is None:
                terminate(child)
                child.wait()
            guard.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
    return True


def terminate(child):
    if os.name != "nt":
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        child.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--execute", type=UUID)
    parser.add_argument("--lease", type=UUID)
    parser.add_argument('--kind', choices=['evidence_analysis','visual_analysis','legal_research'], default='evidence_analysis')
    args = parser.parse_args()
    if args.health:
        raise SystemExit(0 if healthy(args.kind) else 1)
    if args.execute:
        if not args.lease:
            parser.error("Internal execution requires a lease")
        runner = run_analysis
        if args.kind == 'visual_analysis':
            from app.visual_jobs import run_analysis as runner
        elif args.kind == 'legal_research':
            from app.research_jobs import run_analysis as runner
        runner(args.execute, args.lease)
        return
    while True:
        try:
            heartbeat(args.kind)
            processed = process_once(args.kind)
        except Exception:
            # Database interruption never resets the queue or prints private data.
            processed = False
        if args.once:
            return
        if not processed:
            time.sleep(get_settings().analysis_poll_seconds)


if __name__ == "__main__":
    main()
