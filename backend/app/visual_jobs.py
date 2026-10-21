"""Durable visual attempts, current case authorization and immutable private artifacts."""
from datetime import timedelta
import hashlib
import importlib.metadata
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import visual_model, visual_inference
from app.analysis_jobs import lease_job, LeaseLost, check_access
from app.analysis_extraction import AnalysisFailure
from app.auth import audit, now
from app.config import get_settings
from app.database import get_engine
from app.models import AnalysisModel, VisualAnalysis, VisualFrame, VisualDetection, Evidence, EvidenceArtifact, ProcessingJob, User
from app.storage import PrivateStorage, StorageError

PIPELINE_VERSION = 'visual-yolox-v1'
KIND = 'visual_analysis'
SUPPORTED = {'image/png','image/jpeg','video/mp4'}
ERRORS = {
    'unsupported_visual': 'Visual analysis supports only PNG, JPEG and MP4 evidence.',
    'integrity_failed': 'Original SHA-256 verification failed; analysis stopped.',
    'storage_unavailable': 'Preserved original is unavailable; contact the operator.',
    'model_unavailable': 'The pinned local YOLOX model is unavailable or failed integrity checks.',
    'invalid_media': 'Media could not be safely validated or decoded.',
    'invalid_timestamps': 'Video has unavailable or non-monotonic presentation timestamps.',
    'decode_incomplete': 'The complete video could not be decoded; no complete result was published.',
    'pixel_limit_exceeded': 'Decoded dimensions exceed the configured visual pixel limit.',
    'duration_limit_exceeded': 'Video exceeds the configured visual-analysis duration limit.',
    'frame_limit_exceeded': 'Video exceeds the configured sampled-frame limit; use a larger documented interval.',
    'detection_limit_exceeded': 'A frame exceeded the bounded detection limit.',
    'model_output_invalid': 'The model returned unsupported or invalid output.',
    'artifact_failed': 'Private derived image could not be encoded.',
    'access_revoked': 'The requesting user no longer has write access to the active case.',
    'job_timeout': 'Visual analysis exceeded its processing deadline.',
    'worker_interrupted': 'The worker was interrupted; bounded retry may resume as a new attempt.',
    'processing_failed': 'Visual processing failed; private internal details are not exposed.',
}


def registry(db):
    visual_model.verify(get_settings().private_root)
    record = db.scalar(select(AnalysisModel).where(AnalysisModel.name==visual_model.MODEL, AnalysisModel.revision==visual_model.REVISION))
    if record is None:
        record = AnalysisModel(name=visual_model.MODEL, revision=visual_model.REVISION,task='object_detection',license_id='Apache-2.0',
            source_url=visual_model.SOURCE,byte_size=visual_model.SIZE,file_hashes={visual_model.NAME:visual_model.SHA256},
            software={name:importlib.metadata.version(name) for name in ['opencv-python-headless','numpy','Pillow']})
        db.add(record)
        db.flush()
    return record


def run_analysis(job_id, token):
    run_id = None
    settings = get_settings()
    try:
        with Session(get_engine()) as db:
            job = lease_job(db,job_id,token)
            if job.kind != KIND:
                raise LeaseLost('Wrong worker kind')
            user, evidence = check_access(db,job)
            run = VisualAnalysis(id=uuid4(),job_id=job.id,evidence_id=evidence.id,attempt=job.attempts,status='processing',
                original_sha256=evidence.sha256,pipeline_version=PIPELINE_VERSION,
                settings=dict(confidence=settings.visual_confidence,nms=settings.visual_nms,input_size=[640,640],
                    interval_ms=settings.visual_interval_ms,max_frames=settings.visual_max_frames,max_seconds=settings.visual_max_seconds,
                    max_pixels=settings.visual_max_pixels,preprocessing='EXIF/rotation on derivative; RGB 0-255, top-left letterbox 114, no normalization',
                    interpretation='Sampled object candidates only. No identity, re-identification, tracking or crime inference.'))
            db.add(run)
            db.flush()
            run_id, key, expected, mime = run.id,evidence.storage_key,evidence.sha256,evidence.mime_type
            db.commit()
        if mime not in SUPPORTED:
            raise visual_inference.VisualFailure('unsupported_visual')
        store = PrivateStorage(settings.private_root, settings.max_file_bytes)
        try:
            raw = store.read_verified(key,expected)
        except StorageError as exc:
            raise visual_inference.VisualFailure('integrity_failed') from exc
        except OSError as exc:
            raise visual_inference.VisualFailure('storage_unavailable',True) from exc
        with Session(get_engine()) as db:
            lease_job(db,job_id,token)
            check_access(db,db.get(ProcessingJob,job_id))
            db.get(VisualAnalysis,run_id).model_id = registry(db).id
            db.commit()
        count = 0
        derived = PrivateStorage(settings.private_root,50_000_000)
        for sample in visual_inference.frames(raw,mime):
            with Session(get_engine()) as db:
                check_access(db,lease_job(db,job_id,token))
            image = sample.pop('image')
            detections, elapsed = visual_inference.detect(image)
            source = derived.put(visual_inference.png(image),'derived')
            annotated = derived.put(visual_inference.png(visual_inference.annotate(image,detections)),'derived')
            height,width = image.shape[:2]
            with Session(get_engine()) as db:
                job = lease_job(db,job_id,token)
                user,evidence = check_access(db,job)
                run = db.get(VisualAnalysis,run_id)
                run.media = sample['media']
                artifacts = []
                for suffix,stored in [('source',source),('annotated',annotated)]:
                    artifact = EvidenceArtifact(evidence_id=evidence.id,kind=f'visual-{run_id}-{sample["frame_index"]}-{suffix}',
                        storage_key=stored.key,sha256=stored.sha256,byte_size=stored.size,producer_version=PIPELINE_VERSION)
                    db.add(artifact)
                    db.flush()
                    artifacts.append(artifact.id)
                frame = VisualFrame(id=uuid4(),analysis_id=run_id,frame_index=sample['frame_index'],timestamp_ms=sample['timestamp_ms'],
                    width=width,height=height,pixel_sha256=hashlib.sha256(image.tobytes()).hexdigest(),inference_ms=elapsed,
                    source_artifact_id=artifacts[0],annotated_artifact_id=artifacts[1])
                db.add(frame)
                db.flush()
                for item in detections:
                    db.add(VisualDetection(frame_id=frame.id,**item))
                count += 1
                job.processed,job.total = count,max(count,sample['total'])
                db.commit()
        if not count:
            raise visual_inference.VisualFailure('invalid_media')
        try:
            store.read_verified(key,expected)
        except (OSError,StorageError) as exc:
            raise visual_inference.VisualFailure('integrity_failed') from exc
        with Session(get_engine()) as db:
            job = lease_job(db,job_id,token)
            user,evidence = check_access(db,job)
            run = db.get(VisualAnalysis,run_id)
            run.status,run.finished_at = 'completed',now()
            job.status,job.finished_at,job.error_code = 'completed',now(),None
            job.processed,job.total,job.lease_expires_at = count,count,None
            audit(db,user,'visual.completed','case',evidence.case_id,evidence_id=str(evidence.id),analysis_id=str(run_id),sha256=expected,frames=count)
            db.commit()
        return True
    except LeaseLost:
        return False
    except visual_model.ModelUnavailable:
        fail_job(job_id,token,'model_unavailable',False,run_id)
    except (visual_inference.VisualFailure,AnalysisFailure) as exc:
        fail_job(job_id,token,exc.code,exc.retryable,run_id)
    except Exception:
        fail_job(job_id,token,'processing_failed',True,run_id)
    return False


def fail_job(job_id, token, code, retryable, run_id=None):
    with Session(get_engine()) as db:
        try:
            job = lease_job(db,job_id,token)
            if job.kind != KIND:
                return
        except LeaseLost:
            return
        run = db.get(VisualAnalysis,run_id) if run_id else db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job.id,VisualAnalysis.attempt==job.attempts))
        if run:
            run.status,run.error_code,run.finished_at = 'failed',code,now()
        job.error_code = code if code in ERRORS else 'processing_failed'
        if retryable and job.attempts < job.max_attempts:
            job.status,job.processed,job.total = 'queued',0,0
            job.next_attempt_at = now()+timedelta(seconds=min(30,2**job.attempts))
        else:
            job.status,job.finished_at = 'failed',now()
        job.lease_expires_at = None
        evidence = db.get(Evidence,job.evidence_id)
        if evidence:
            audit(db,db.get(User,job.requested_by),'visual.failed','case',evidence.case_id,job_id=str(job.id),error_code=job.error_code,attempt=job.attempts)
        db.commit()
