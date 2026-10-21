"""Public source search and authenticated case-private research/review APIs."""
from datetime import date
import hashlib,json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,ConfigDict,Field,model_validator
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from app import legal_retrieval,research_jobs,vectors
from app.auth import current_user,audit
from app.case_api import authorized_case
from app.config import get_settings
from app.library_api import session_dependency
from app.models import User,ProcessingJob,ResearchRun,ResearchInput,ResearchResult,ResearchReview,AnalysisPage,EvidenceAnalysis,Evidence,LegalProvision

router=APIRouter(prefix='/api/v1',tags=['Grounded legal research'])

class Filters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['all','judgment','statute']='all'
    court:str|None=Field(default=None,max_length=255)
    year:int|None=Field(default=None,ge=1800,le=2200)
    source_id:UUID|None=None
    act:str|None=Field(default=None,max_length=255)
    version:str|None=Field(default=None,max_length=255)
    as_of:date|None=None

class Search(Filters):
    query:str=Field(min_length=3,max_length=1000)
    limit:int=Field(default=5,ge=1,le=20)
    @model_validator(mode='after')
    def stripped(self):
        self.query=self.query.strip()
        if len(self.query)<3:raise ValueError('A meaningful search query is required')
        return self

@router.get('/research/statute-sources')
def statute_sources(db:Session=Depends(session_dependency)):
    return dict(items=legal_retrieval.CATALOG,imported_provisions=db.scalar(select(func.count()).select_from(LegalProvision)),
        notice='Candidate source metadata is not verified statutory text. Imports remain gated until official access, rights and legal version are verified.')

@router.post('/research/search')
def search(body:Search,db:Session=Depends(session_dependency)):
    try:return legal_retrieval.search(db,body.query,body.limit,**body.model_dump(mode='json',exclude={'query','limit'},exclude_none=True))
    except vectors.QueryTooLong as exc:raise HTTPException(422,str(exc)) from exc
    except Exception as exc:raise HTTPException(503,'Pinned local legal search is unavailable') from exc

class Selection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    evidence_id:UUID
    page_id:UUID
    char_start:int=Field(ge=0)
    char_end:int=Field(gt=0)

class ResearchRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    selections:list[Selection]=Field(default_factory=list,max_length=8)
    reviewed_input:str=Field(default='',max_length=2000)
    reviewed_input_confirmed:bool=False
    limit:int=Field(default=3,ge=1,le=5)
    filters:Filters=Field(default_factory=Filters)
    reanalyze:bool=False
    @model_validator(mode='after')
    def reviewed(self):
        if self.reviewed_input.strip() and not self.reviewed_input_confirmed:raise ValueError('Confirm that factual input has been human reviewed')
        for item in self.selections:
            if not item.char_start<item.char_end or item.char_end-item.char_start>4000:raise ValueError('Select at most 4000 characters per source span')
        if len({(x.page_id,x.char_start,x.char_end) for x in self.selections})!=len(self.selections):raise ValueError('Duplicate source spans')
        return self

def scoped_job(db,user,case_id,job_id):
    authorized_case(db,user,case_id)
    job=db.get(ProcessingJob,job_id)
    if not job or job.kind!=research_jobs.KIND or job.details.get('case_id')!=str(case_id):raise HTTPException(404,'Research job not found')
    return job

def scoped_run(db,user,case_id,run_id,complete=False):
    authorized_case(db,user,case_id)
    run=db.get(ResearchRun,run_id)
    if not run or run.case_id!=case_id:raise HTTPException(404,'Research run not found')
    if complete and run.status!='completed':raise HTTPException(409,'Only completed attempts publish research inputs/results')
    return run

def job_fields(job):return dict(id=job.id,status=job.status,attempts=job.attempts,max_attempts=job.max_attempts,processed=job.processed,total=job.total,
    error_code=job.error_code,message=research_jobs.ERRORS.get(job.error_code),created_at=job.created_at,finished_at=job.finished_at)

def run_fields(run):return dict(id=run.id,case_id=run.case_id,job_id=run.job_id,attempt=run.attempt,status=run.status,outcome=run.outcome,
    provenance=run.provenance,limitations=run.limitations,error_code=run.error_code,created_at=run.created_at,finished_at=run.finished_at)

def capacity(db,user):
    query=select(func.count()).select_from(ProcessingJob).where(ProcessingJob.kind==research_jobs.KIND,ProcessingJob.status.in_(['queued','processing']))
    if db.scalar(query)>=100 or db.scalar(query.where(ProcessingJob.requested_by==user.id))>=3:raise HTTPException(429,'Research queue capacity reached')

@router.get('/cases/{case_id}/research-inputs')
def selectable(case_id:UUID,limit:int=Query(20,ge=1,le=30),offset:int=Query(0,ge=0),user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    authorized_case(db,user,case_id)
    query=select(AnalysisPage,EvidenceAnalysis,Evidence).join(EvidenceAnalysis,AnalysisPage.analysis_id==EvidenceAnalysis.id).join(Evidence,Evidence.id==EvidenceAnalysis.evidence_id).where(
        Evidence.case_id==case_id,EvidenceAnalysis.status=='completed',EvidenceAnalysis.original_sha256==Evidence.sha256)
    records=db.execute(query.order_by(Evidence.created_at,EvidenceAnalysis.created_at.desc(),AnalysisPage.page_number).offset(offset).limit(limit))
    return dict(items=[dict(page_id=p.id,evidence_id=e.id,analysis_id=a.id,filename=e.original_filename,page_number=p.page_number,
        text=p.text[:4000],total_chars=len(p.text),preview_chars=min(4000,len(p.text)),text_sha256=p.text_sha256,classification='unverified_extracted_evidence') for p,a,e in records],
        total=db.scalar(select(func.count()).select_from(query.subquery())),offset=offset,limit=limit)

@router.post('/cases/{case_id}/research-jobs',status_code=202)
def trigger(case_id:UUID,body:ResearchRequest,response:Response,user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    research_jobs.access(db,user,case_id)
    payload=body.model_dump(mode='json',exclude={'reanalyze'});payload['case_id']=str(case_id);payload['reviewed_by']=str(user.id)
    payload['pipeline_version']=research_jobs.PIPELINE;payload['model_revision']=get_settings().embedding_revision
    try:research_jobs.inputs(db,case_id,payload['selections'],body.reviewed_input,user.id)
    except research_jobs.ResearchFailure as exc:raise HTTPException(422,research_jobs.ERRORS[exc.code]) from exc
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    existing=db.scalar(select(ProcessingJob).where(ProcessingJob.kind==research_jobs.KIND,
        ProcessingJob.details['case_id'].astext==str(case_id),ProcessingJob.details['request_sha256'].astext==fingerprint,
        ProcessingJob.status.in_(['queued','processing'] if body.reanalyze else ['queued','processing','completed'])).order_by(ProcessingJob.created_at.desc()))
    if existing:
        response.status_code=200 if existing.status=='completed' else 202
        return job_fields(existing)
    capacity(db,user)
    job=ProcessingJob(kind=research_jobs.KIND,requested_by=user.id,details={**payload,'request_sha256':fingerprint,'pipeline_version':research_jobs.PIPELINE})
    db.add(job);db.flush();audit(db,user,'research.queued','case',case_id,job_id=str(job.id));db.commit()
    return job_fields(job)

@router.get('/cases/{case_id}/research-jobs')
def jobs(case_id:UUID,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    authorized_case(db,user,case_id)
    records=db.scalars(select(ProcessingJob).where(ProcessingJob.kind==research_jobs.KIND,ProcessingJob.details['case_id'].astext==str(case_id)).order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit))
    return dict(items=[job_fields(j) for j in records])

@router.get('/cases/{case_id}/research-jobs/{job_id}')
def job_detail(case_id:UUID,job_id:UUID,user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    job=scoped_job(db,user,case_id,job_id)
    return {**job_fields(job),'runs':[run_fields(r) for r in db.scalars(select(ResearchRun).where(ResearchRun.job_id==job.id).order_by(ResearchRun.attempt.desc()))]}

@router.post('/cases/{case_id}/research-jobs/{job_id}/retry',status_code=202)
def retry(case_id:UUID,job_id:UUID,user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    research_jobs.access(db,user,case_id);job=scoped_job(db,user,case_id,job_id)
    if job.status!='failed' or job.attempts>=job.max_attempts:raise HTTPException(409,'Only failed jobs below the attempt cap can retry')
    duplicate=db.scalar(select(ProcessingJob.id).where(ProcessingJob.kind==research_jobs.KIND,
        ProcessingJob.details['case_id'].astext==str(case_id),
        ProcessingJob.details['request_sha256'].astext==job.details['request_sha256'],ProcessingJob.status.in_(['queued','processing'])))
    if duplicate:raise HTTPException(409,'An identical research request is already active')
    capacity(db,user)
    job.requested_by,job.status,job.next_attempt_at,job.finished_at=user.id,'queued',None,None
    job.processed,job.total=0,0
    audit(db,user,'research.retry','case',case_id,job_id=str(job.id));db.commit()
    return job_fields(job)

@router.get('/cases/{case_id}/research-runs/{run_id}')
def result(case_id:UUID,run_id:UUID,limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0),user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    run=scoped_run(db,user,case_id,run_id,True)
    query=select(ResearchResult).where(ResearchResult.run_id==run.id)
    records=list(db.scalars(query.order_by(ResearchResult.rank).offset(offset).limit(limit)))
    try:
        for r in records:research_jobs.validate_citation(db,r.citation)
    except research_jobs.ResearchFailure as exc:raise HTTPException(409,'Saved source citation failed integrity checks') from exc
    input_ids={r.input_id for r in records}
    if not input_ids:input_ids=set(db.scalars(select(ResearchInput.id).where(ResearchInput.run_id==run.id).limit(16)))
    inputs=list(db.scalars(select(ResearchInput).where(ResearchInput.id.in_(input_ids))))
    for item in inputs:
        if legal_retrieval.digest(item.text)!=item.sha256:raise HTTPException(409,'Saved research input failed integrity checks')
        start,end=item.provenance.get('query_char_start'),item.provenance.get('query_char_end')
        if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(item.text) or item.query!=item.text[start:end]:
            raise HTTPException(409,'Saved query is not the exact recorded input span')
    audit(db,user,'research.read','case',case_id,run_id=str(run.id));db.commit()
    return {**run_fields(run),'inputs':[dict(id=i.id,evidence_id=i.evidence_id,page_id=i.page_id,text=i.text,sha256=i.sha256,query=i.query,provenance=i.provenance) for i in inputs],
        'items':[dict(id=r.id,input_id=r.input_id,rank=r.rank,distance=r.distance,source=r.citation,
            suggestion='Review the cited passage for relevance; no legal conclusion has been generated.',interpretation='deterministic research prompt, not a factual or legal finding',
            reviews=[dict(id=v.id,reviewer_id=v.reviewer_id,disposition=v.disposition,note=v.note,created_at=v.created_at,classification='human_review_annotation') for v in db.scalars(select(ResearchReview).where(ResearchReview.result_id==r.id).order_by(ResearchReview.created_at))]) for r in records],
        'total':db.scalar(select(func.count()).select_from(query.subquery())),
        'review_checklist':['Verify incident date and applicable legal version.','Check exact original passages and OCR errors.','Check later binding authority and subsequent amendments.','Verify any missing context before forming a legal issue or conclusion.']}

class Review(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    disposition:Literal['relevant','not_relevant','needs_verification']
    note:str=Field(min_length=3,max_length=3000)

@router.post('/cases/{case_id}/research-runs/{run_id}/results/{result_id}/reviews',status_code=201)
def review(case_id:UUID,run_id:UUID,result_id:UUID,body:Review,user:User=Depends(current_user),db:Session=Depends(session_dependency)):
    research_jobs.access(db,user,case_id);scoped_run(db,user,case_id,run_id,True)
    item=db.get(ResearchResult,result_id)
    if not item or item.run_id!=run_id:raise HTTPException(404,'Research result not found')
    entry=ResearchReview(result_id=item.id,reviewer_id=user.id,**body.model_dump());db.add(entry);db.flush()
    audit(db,user,'research.reviewed','case',case_id,result_id=str(item.id),review_id=str(entry.id));db.commit()
    return dict(id=entry.id,result_id=item.id,reviewer_id=user.id,disposition=entry.disposition,note=entry.note,classification='human_review_annotation')
