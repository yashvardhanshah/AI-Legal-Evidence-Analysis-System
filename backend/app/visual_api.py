"""Case-scoped commands/results; no unauthenticated or public visual artifacts."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user, audit
from app.case_api import authorized_case, authorized_evidence
from app.config import get_settings
from app.library_api import session_dependency
from app.models import User, ProcessingJob, VisualAnalysis, VisualFrame, VisualDetection, AnalysisModel, EvidenceArtifact
from app.storage import PrivateStorage, StorageError
from app.visual_jobs import KIND, PIPELINE_VERSION, ERRORS, SUPPORTED

router = APIRouter(prefix='/api/v1/cases/{case_id}/evidence/{evidence_id}',tags=['Private visual analysis'])


def fields(job):
    return dict(id=job.id,evidence_id=job.evidence_id,status=job.status,attempts=job.attempts,max_attempts=job.max_attempts,
        processed=job.processed,total=job.total,error_code=job.error_code,message=ERRORS.get(job.error_code),
        created_at=job.created_at,started_at=job.started_at,finished_at=job.finished_at,next_attempt_at=job.next_attempt_at,
        pipeline_version=job.details.get('pipeline_version'))


def scoped_job(db,user,case_id,evidence_id,job_id):
    authorized_evidence(db,user,case_id,evidence_id)
    record = db.scalar(select(ProcessingJob).where(ProcessingJob.id==job_id,ProcessingJob.evidence_id==evidence_id,ProcessingJob.kind==KIND))
    if not record:
        raise HTTPException(404,'Visual job not found')
    return record


def scoped_run(db,user,case_id,evidence_id,analysis_id,complete=False):
    authorized_evidence(db,user,case_id,evidence_id)
    record = db.scalar(select(VisualAnalysis).where(VisualAnalysis.id==analysis_id,VisualAnalysis.evidence_id==evidence_id))
    if not record:
        raise HTTPException(404,'Visual analysis not found')
    if complete and record.status!='completed':
        raise HTTPException(409,'This attempt has no complete published visual result')
    return record


def run_fields(db,run):
    model = db.get(AnalysisModel,run.model_id) if run.model_id else None
    return dict(id=run.id,job_id=run.job_id,evidence_id=run.evidence_id,status=run.status,attempt=run.attempt,
        pipeline_version=run.pipeline_version,original_sha256=run.original_sha256,settings=run.settings,media=run.media,
        created_at=run.created_at,finished_at=run.finished_at,error_code=run.error_code,message=ERRORS.get(run.error_code),
        frame_count=db.scalar(select(func.count()).select_from(VisualFrame).where(VisualFrame.analysis_id==run.id)),
        model=None if not model else dict(name=model.name,revision=model.revision,license_id=model.license_id,
            source_url=model.source_url,byte_size=model.byte_size,file_hashes=model.file_hashes,software=model.software))


def queue_capacity(db,user):
    query = select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind==KIND,ProcessingJob.status.in_(['queued','processing']))
    if db.scalar(query)>=100 or db.scalar(query.where(ProcessingJob.requested_by==user.id))>=3:
        raise HTTPException(429,'Visual queue limit reached; wait for existing jobs')


class VisualRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reanalyze: bool = False


@router.post('/visual-analysis',status_code=202)
def trigger(case_id: UUID,evidence_id: UUID,response: Response,body: VisualRequest=VisualRequest(),user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    authorized_case(db,user,case_id,write=True)
    evidence = authorized_evidence(db,user,case_id,evidence_id)
    if evidence.mime_type not in SUPPORTED:
        raise HTTPException(422,ERRORS['unsupported_visual'])
    existing = db.scalar(select(ProcessingJob).where(ProcessingJob.kind==KIND,ProcessingJob.evidence_id==evidence_id,ProcessingJob.status.in_(['queued','processing'])))
    if existing:
        return fields(existing)
    if not body.reanalyze:
        completed = db.scalar(select(ProcessingJob).where(ProcessingJob.kind==KIND,ProcessingJob.evidence_id==evidence_id,ProcessingJob.status=='completed').order_by(ProcessingJob.created_at.desc()))
        if completed and completed.details.get('pipeline_version')==PIPELINE_VERSION:
            response.status_code=200
            return fields(completed)
    queue_capacity(db,user)
    job = ProcessingJob(kind=KIND,status='queued',evidence_id=evidence_id,requested_by=user.id,details=dict(pipeline_version=PIPELINE_VERSION))
    db.add(job)
    db.flush()
    audit(db,user,'visual.queued','case',case_id,evidence_id=str(evidence_id),job_id=str(job.id))
    db.commit()
    return fields(job)


@router.get('/visual-jobs')
def jobs(case_id: UUID,evidence_id: UUID,limit: int=Query(20,ge=1,le=100),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    authorized_evidence(db,user,case_id,evidence_id)
    query = select(ProcessingJob).where(ProcessingJob.kind==KIND,ProcessingJob.evidence_id==evidence_id)
    return {'items':[fields(j) for j in db.scalars(query.order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit))]}


@router.get('/visual-jobs/{job_id}')
def job_detail(case_id: UUID,evidence_id: UUID,job_id: UUID,user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    job = scoped_job(db,user,case_id,evidence_id,job_id)
    return {**fields(job),'runs':[run_fields(db,r) for r in db.scalars(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id).order_by(VisualAnalysis.attempt.desc()))]}


@router.post('/visual-jobs/{job_id}/retry',status_code=202)
def retry(case_id: UUID,evidence_id: UUID,job_id: UUID,user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    authorized_case(db,user,case_id,write=True)
    job = scoped_job(db,user,case_id,evidence_id,job_id)
    if job.status!='failed' or job.attempts>=job.max_attempts:
        raise HTTPException(409,'Only failed jobs below their attempt cap can be retried')
    active = db.scalar(select(ProcessingJob.id).where(ProcessingJob.kind==KIND,ProcessingJob.evidence_id==evidence_id,ProcessingJob.status.in_(['queued','processing'])))
    if active:
        raise HTTPException(409,'A visual job is already active for this evidence')
    queue_capacity(db,user)
    job.status,job.processed,job.total='queued',0,0
    job.requested_by,job.next_attempt_at,job.finished_at=user.id,None,None
    audit(db,user,'visual.retry_requested','case',case_id,job_id=str(job.id))
    db.commit()
    return fields(job)


@router.get('/visual-analyses')
def analyses(case_id: UUID,evidence_id: UUID,limit: int=Query(20,ge=1,le=100),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    authorized_evidence(db,user,case_id,evidence_id)
    query=select(VisualAnalysis).where(VisualAnalysis.evidence_id==evidence_id)
    return {'items':[run_fields(db,r) for r in db.scalars(query.order_by(VisualAnalysis.created_at.desc()).offset(offset).limit(limit))]}


@router.get('/visual-analyses/{analysis_id}')
def analysis_detail(case_id: UUID,evidence_id: UUID,analysis_id: UUID,user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    run=scoped_run(db,user,case_id,evidence_id,analysis_id)
    audit(db,user,'visual.read','case',case_id,analysis_id=str(run.id))
    db.commit()
    return run_fields(db,run)


def frame_fields(db,frame):
    items=db.scalars(select(VisualDetection).where(VisualDetection.frame_id==frame.id).order_by(VisualDetection.confidence.desc(),VisualDetection.id))
    return dict(id=frame.id,frame_index=frame.frame_index,timestamp_ms=frame.timestamp_ms,width=frame.width,height=frame.height,
        pixel_sha256=frame.pixel_sha256,inference_ms=frame.inference_ms,
        detections=[dict(id=d.id,class_id=d.class_id,label=d.label,confidence=d.confidence,x1=d.x1,y1=d.y1,x2=d.x2,y2=d.y2,provenance=d.provenance) for d in items])


@router.get('/visual-analyses/{analysis_id}/frames')
def frames(case_id: UUID,evidence_id: UUID,analysis_id: UUID,limit: int=Query(10,ge=1,le=25),offset: int=Query(0,ge=0),user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    scoped_run(db,user,case_id,evidence_id,analysis_id,True)
    query=select(VisualFrame).where(VisualFrame.analysis_id==analysis_id)
    audit(db,user,'visual.frames_read','case',case_id,analysis_id=str(analysis_id))
    records=list(db.scalars(query.order_by(VisualFrame.frame_index).offset(offset).limit(limit)))
    db.commit()
    return {'items':[frame_fields(db,f) for f in records],'total':db.scalar(select(func.count()).select_from(query.subquery()))}


@router.get('/visual-analyses/{analysis_id}/frames/{frame_id}/artifact')
def artifact(case_id: UUID,evidence_id: UUID,analysis_id: UUID,frame_id: UUID,annotated: bool=True,user: User=Depends(current_user),db: Session=Depends(session_dependency)):
    scoped_run(db,user,case_id,evidence_id,analysis_id,True)
    frame=db.scalar(select(VisualFrame).where(VisualFrame.id==frame_id,VisualFrame.analysis_id==analysis_id))
    if not frame:
        raise HTTPException(404,'Visual frame not found')
    item=db.get(EvidenceArtifact,frame.annotated_artifact_id if annotated else frame.source_artifact_id)
    if not item or item.evidence_id!=evidence_id:
        raise HTTPException(409,'Visual artifact unavailable')
    try:
        content=PrivateStorage(get_settings().private_root).read_verified(item.storage_key,item.sha256)
    except (OSError,StorageError) as exc:
        raise HTTPException(409,'Visual artifact failed integrity verification') from exc
    audit(db,user,'visual.artifact_read','case',case_id,analysis_id=str(analysis_id),frame_id=str(frame_id),annotated=annotated)
    db.commit()
    return Response(content,media_type='image/png',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
        'X-Content-SHA256':item.sha256,'Content-Disposition':f'inline; filename="visual-{frame.id}.png"'})
