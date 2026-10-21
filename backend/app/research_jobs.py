"""Case-authorized, fenced extractive research. No external service or generated claims."""
from datetime import timedelta
import math,json,importlib.metadata
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis_jobs import lease_job,LeaseLost
from app.auth import audit,now
from app.case_api import authorized_case
from app.config import get_settings
from app.database import get_engine
from app.documents import chunk_pages
from app import legal_retrieval,vectors
from app.models import User,Case,Evidence,EvidenceAnalysis,AnalysisPage,ResearchRun,ResearchInput,ResearchResult,ProcessingJob,Judgment,JudgmentPassage,ProvisionPassage,StatuteVersion,LegalProvision,EvidenceArtifact,AnalysisModel
from app.storage import PrivateStorage,StorageError

KIND='legal_research'
PIPELINE='extractive-research-v1'
ERRORS={'access_revoked':'Research authorization is no longer valid.','integrity_failed':'Source integrity verification failed.',
 'invalid_input':'A selected completed extraction or source span is unavailable.', 'processing_failed':'Local research failed; private details are not exposed.',
 'worker_interrupted':'Research worker was interrupted; bounded retry can create a retained new attempt.',
 'job_timeout':'Research exceeded its processing deadline.','index_unavailable':'The pinned local retrieval model or index is unavailable.'}

class ResearchFailure(ValueError):
    def __init__(self,code,retryable=False):self.code,self.retryable=code,retryable

def registry(db):
    vectors.verify_model()
    config=get_settings()
    manifest=json.loads((vectors.model_path()/'download-manifest.json').read_text())
    item=db.scalar(select(AnalysisModel).where(AnalysisModel.name==config.embedding_model,AnalysisModel.revision==config.embedding_revision))
    if not item:
        item=AnalysisModel(name=config.embedding_model,revision=config.embedding_revision,task='semantic_retrieval',license_id='Apache-2.0',
            source_url=f'https://huggingface.co/{config.embedding_model}/tree/{config.embedding_revision}',
            byte_size=sum(f['bytes'] for f in manifest['files'].values()),file_hashes={name:f['sha256'] for name,f in manifest['files'].items()},
            software={name:importlib.metadata.version(name) for name in ['sentence-transformers','chromadb','torch']})
        db.add(item);db.flush()
    return item

def access(db,user,case_id,write=True):
    if not user or not user.is_active:raise HTTPException(404,'Case not found')
    case=authorized_case(db,user,case_id,write=write)
    if write and user.role not in {'administrator','investigator','lawyer'}:
        raise HTTPException(403,'Research initiation and review require an investigator, lawyer or administrator')
    return case

def context(db,job):
    try:
        user=db.get(User,job.requested_by)
        case=access(db,user,UUID(job.details['case_id']))
        return user,case
    except (HTTPException,ValueError,KeyError) as exc:raise ResearchFailure('access_revoked') from exc

def inputs(db,case_id,selections,reviewed_input='',reviewed_by=None,verify_files=False):
    result=[]
    store=PrivateStorage(get_settings().private_root)
    checked=set()
    extraction_artifacts={}
    for item in selections:
        evidence=db.get(Evidence,UUID(str(item['evidence_id'])))
        page=db.get(AnalysisPage,UUID(str(item['page_id'])))
        analysis=db.get(EvidenceAnalysis,page.analysis_id) if page else None
        if not evidence or evidence.case_id!=case_id or not page or not analysis or analysis.evidence_id!=evidence.id or analysis.status!='completed':
            raise ResearchFailure('invalid_input')
        if analysis.original_sha256!=evidence.sha256 or legal_retrieval.digest(page.text)!=page.text_sha256:
            raise ResearchFailure('integrity_failed')
        start,end=item['char_start'],item['char_end']
        if not 0<=start<end<=len(page.text) or end-start>4000:raise ResearchFailure('invalid_input')
        if verify_files and evidence.id not in checked:
            try:store.read_verified(evidence.storage_key,evidence.sha256)
            except (OSError,StorageError) as exc:raise ResearchFailure('integrity_failed') from exc
            checked.add(evidence.id)
        if verify_files:
            if analysis.id not in extraction_artifacts:
                artifact=db.get(EvidenceArtifact,analysis.artifact_id) if analysis.artifact_id else None
                if not artifact or artifact.evidence_id!=evidence.id:raise ResearchFailure('integrity_failed')
                try:
                    content=json.loads(store.read_verified(artifact.storage_key,artifact.sha256))
                    if content['analysis_id']!=str(analysis.id) or content['original_sha256']!=evidence.sha256:raise ValueError('Extraction provenance differs')
                    extraction_artifacts[analysis.id]={p['page_number']:p for p in content['pages']}
                except (OSError,StorageError,ValueError,KeyError,TypeError) as exc:raise ResearchFailure('integrity_failed') from exc
            original_page=extraction_artifacts[analysis.id].get(page.page_number)
            if not original_page or original_page['text']!=page.text or original_page['text_sha256']!=page.text_sha256:raise ResearchFailure('integrity_failed')
        text=page.text[start:end]
        if text.strip():result.append(dict(evidence_id=evidence.id,page_id=page.id,text=text,
            provenance=dict(classification='unverified_extracted_evidence',analysis_id=str(analysis.id),page_number=page.page_number,
                extraction_method=page.extraction_method,page_sha256=page.text_sha256,original_sha256=evidence.sha256,
                char_start=start,char_end=end,automatic_entities_and_visual_detections_used=False)))
    if reviewed_input.strip():result.append(dict(evidence_id=None,page_id=None,text=reviewed_input,
        provenance=dict(classification='human_reviewed_input',reviewer_id=str(reviewed_by),
            notice='User-attested reviewed factual input, not independently established truth.')))
    return result

def _validate_citation(db,citation,verify_file=False):
    if citation['kind']=='judgment':
        page=db.get(JudgmentPassage,UUID(citation['passage_id']))
        doc=db.get(Judgment,page.judgment_id) if page else None
        text=page.text if page else None
        key=doc.storage_key if doc else None
        sha=doc.sha256 if doc else None
        expected=dict(source_url=doc.source_url,source_id=str(doc.source_id),title=doc.title,court=doc.court,citation=doc.citation,
            judgment_date=doc.judgment_date.isoformat() if doc.judgment_date else None) if doc else {}
    elif citation['kind']=='statute':
        page=db.get(ProvisionPassage,UUID(citation['passage_id']))
        doc=db.get(StatuteVersion,page.version_id) if page else None
        text=page.text if page else None
        key=doc.storage_key if doc else None
        sha=doc.sha256 if doc else None
        law=db.get(LegalProvision,page.provision_id) if page else None
        expected=dict(source_url=law.source_url,source_id=str(law.source_id),title=law.act_title,provision_id=str(law.id),
            act_identifier=law.act_identifier,section=law.provision_identifier,heading=law.heading,version=law.version,
            effective_from=law.effective_from.isoformat() if law.effective_from else None,
            effective_to=law.effective_to.isoformat() if law.effective_to else None,version_metadata=doc.metadata_record) if doc and law else {}
    else:raise ResearchFailure('integrity_failed')
    if not doc or str(doc.id)!=citation['document_id'] or text!=citation['excerpt'] or legal_retrieval.digest(text)!=citation['text_sha256'] or sha!=citation['document_sha256']:
        raise ResearchFailure('integrity_failed')
    expected.update(page_number=page.page_number,char_start=page.char_start,char_end=page.char_end,
        model=get_settings().embedding_model,model_revision=get_settings().embedding_revision,metric='cosine_distance',classification='verified_source_text')
    if any(citation.get(key)!=value for key,value in expected.items()) or not math.isfinite(citation['distance']) or not -0.0001<=citation['distance']<=2.0001:
        raise ResearchFailure('integrity_failed')
    if verify_file:
        try:PrivateStorage(get_settings().private_root).read_verified(key,sha)
        except (OSError,StorageError) as exc:raise ResearchFailure('integrity_failed') from exc

def validate_citation(db,citation,verify_file=False):
    try:return _validate_citation(db,citation,verify_file)
    except (KeyError,TypeError,ValueError,AttributeError) as exc:raise ResearchFailure('integrity_failed') from exc

def run_analysis(job_id,token):
    run_id=None
    try:
        with Session(get_engine()) as db:
            job=lease_job(db,job_id,token)
            if job.kind!=KIND:raise LeaseLost('Wrong worker kind')
            user,case=context(db,job)
            run=ResearchRun(job_id=job.id,case_id=case.id,attempt=job.attempts,status='processing',
                provenance=dict(algorithm=PIPELINE,model=get_settings().embedding_model,revision=get_settings().embedding_revision,
                    query_method='Exact source-text token windows, 220 word pieces with 32 overlap; no generated queries or LLM',
                    filters=job.details.get('filters',{}),llm_enabled=False,requested_by=str(user.id)),
                limitations=[legal_retrieval.NOTICE,'NLP entities and visual detections are unverified and are not automatically used.',
                    'The judgment corpus is a small historical English sample; later law and authorities require independent verification.'])
            db.add(run);db.flush();run_id=run.id
            db.commit()
        with Session(get_engine()) as db:
            job=lease_job(db,job_id,token);user,case=context(db,job)
            sources=inputs(db,case.id,job.details['selections'],job.details.get('reviewed_input',''),job.details.get('reviewed_by',str(user.id)),True)
            run=db.get(ResearchRun,run_id)
            if sources:
                model=registry(db)
                run.provenance={**run.provenance,'model_registry_id':str(model.id),'model_license':model.license_id,
                    'model_file_hashes':model.file_hashes,'software':model.software}
            # Empty/visual-only evidence without reviewed text is an explicit insufficient-evidence outcome.
            windows=[]
            for source in sources:
                for chunk in chunk_pages([source['text']],vectors.tokenizer()):
                    windows.append((source,chunk))
            if len(windows)>16:raise ResearchFailure('invalid_input')
            job.total=len(windows);db.commit()
        seen=set();stored=0;statutory=0
        for source,chunk in windows:
            with Session(get_engine()) as db:
                job=lease_job(db,job_id,token);user,case=context(db,job)
                record=ResearchInput(run_id=run_id,evidence_id=source['evidence_id'],page_id=source['page_id'],text=source['text'],
                    sha256=legal_retrieval.digest(source['text']),query=chunk['text'],
                    provenance={**source['provenance'],'query_char_start':chunk['char_start'],'query_char_end':chunk['char_end']})
                db.add(record);db.flush()
                found=legal_retrieval.search(db,chunk['text'],job.details['limit'],**job.details.get('filters',{}))
                for citation in found['judgments']+found['statutes']:
                    identity=(citation['kind'],citation.get('provision_id',citation['document_id']))
                    if identity in seen:continue
                    validate_citation(db,citation,True)
                    db.add(ResearchResult(run_id=run_id,input_id=record.id,rank=stored+1,distance=citation['distance'],citation=citation,
                        judgment_passage_id=UUID(citation['passage_id']) if citation['kind']=='judgment' else None,
                        provision_passage_id=UUID(citation['passage_id']) if citation['kind']=='statute' else None))
                    stored+=1;statutory+=citation['kind']=='statute';seen.add(identity)
                job.processed+=1;db.commit()
        with Session(get_engine()) as db:
            job=lease_job(db,job_id,token);user,case=context(db,job)
            # Reverify immutable originals and extraction spans before publishing.
            inputs(db,case.id,job.details['selections'],job.details.get('reviewed_input',''),job.details.get('reviewed_by',str(user.id)),True)
            run=db.get(ResearchRun,run_id)
            run.status,run.finished_at='completed',now()
            run.outcome='insufficient_evidence' if not windows else 'insufficient_sources' if not stored else 'sources_retrieved'
            if not statutory:run.limitations=[*run.limitations,'Insufficient verified statutory sources; no statutory applicability or crosswalk is asserted.']
            job.status,job.finished_at,job.lease_expires_at='completed',now(),None
            audit(db,user,'research.completed','case',case.id,run_id=str(run.id),results=stored,outcome=run.outcome)
            db.commit()
        return True
    except LeaseLost:return False
    except ResearchFailure as exc:fail_job(job_id,token,exc.code,exc.retryable,run_id)
    except (vectors.VectorUnavailable,OSError):fail_job(job_id,token,'index_unavailable',True,run_id)
    except Exception:fail_job(job_id,token,'processing_failed',True,run_id)
    return False

def fail_job(job_id,token,code,retryable,run_id=None):
    with Session(get_engine()) as db:
        try:job=lease_job(db,job_id,token)
        except LeaseLost:return
        if job.kind!=KIND:return
        run=db.get(ResearchRun,run_id) if run_id else db.scalar(select(ResearchRun).where(ResearchRun.job_id==job.id,ResearchRun.attempt==job.attempts))
        if run:run.status,run.error_code,run.finished_at='failed',code,now()
        job.error_code=code if code in ERRORS else 'processing_failed'
        if retryable and job.attempts<job.max_attempts:
            job.status,job.processed,job.total='queued',0,0
            job.next_attempt_at=now()+timedelta(seconds=min(30,2**job.attempts))
        else:job.status,job.finished_at='failed',now()
        job.lease_expires_at=None
        audit(db,db.get(User,job.requested_by),'research.failed','case',UUID(job.details['case_id']),job_id=str(job.id),error_code=job.error_code)
        db.commit()
