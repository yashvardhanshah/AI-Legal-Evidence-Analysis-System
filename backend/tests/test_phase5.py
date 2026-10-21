"""Actual licensed-media/model tests, transactional SQL and private visual boundaries."""
from datetime import timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
from uuid import UUID,uuid4

import pytest
from PIL import Image
from sqlalchemy import func,select,text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from test_phase3 import workspace,real_media,csrf,create,upload
from app import visual_model,visual_inference,visual_jobs,analysis_worker
from app.auth import now
from app.config import get_settings
from app.models import VisualAnalysis,VisualFrame,VisualDetection,ProcessingJob,Evidence,EvidenceArtifact,AuditLog
from app.storage import PrivateStorage


@pytest.fixture(scope='module')
def visual_media(real_media):
    folder=Path(os.environ['PRIVATE_ROOT'])/'visual-test-media'
    receipt=json.loads((folder/'provenance.json').read_text())
    jpg=(folder/'labrador.jpg').read_bytes()
    video=(folder/'jijiga-960.mp4').read_bytes()
    assert hashlib.sha256(jpg).hexdigest()==receipt['labrador.jpg']['sha256']
    assert hashlib.sha256(video).hexdigest()==receipt['jijiga-960.mp4']['sha256']
    with Image.open(io.BytesIO(jpg)) as image:
        buffer=io.BytesIO()
        image.save(buffer,'PNG')
    return dict(jpg=jpg,jpeg=jpg,png=buffer.getvalue(),mp4=video,
        provenance='Authorized licensed public-source test: Elf/Carla Nunziata Labrador CC BY-SA 3.0; Brian Dell Jijiga traffic CC0 1.0. PNG/MP4 are declared derivatives, not private allegations.')


@pytest.fixture
def vision(workspace,visual_media,monkeypatch):
    db,new_user,_,_=workspace
    connection=db.bind
    model_file=Path(os.environ['PRIVATE_ROOT'])/'models'/'vision'/visual_model.REVISION/visual_model.NAME
    monkeypatch.setattr(visual_model,'path',lambda root:model_file)
    monkeypatch.setattr(visual_jobs,'get_engine',lambda:connection)
    monkeypatch.setattr(visual_jobs,'Session',lambda bind:Session(bind=connection,join_transaction_mode='create_savepoint'))
    try:
        yield db,new_user,visual_media
    finally:
        connection.execute(text('SELECT pg_advisory_unlock_all()'))


def saved(vision,kind='jpg'):
    db,new_user,media=vision
    client,user=new_user()
    case=create(client)
    response=upload(client,case['id'],media[kind],kind,media['provenance'])
    assert response.status_code==201,response.text
    return db,new_user,media,client,case,response.json()


def enqueue(client,case,evidence):
    base=f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}"
    response=client.post(base+'/visual-analysis',json={},headers=csrf(client))
    assert response.status_code==202,response.text
    return base,UUID(response.json()['id'])


def execute(db,job_id):
    claimed=analysis_worker.claim(db,db.bind,'visual_analysis')
    assert claimed and claimed[0]==job_id
    result=visual_jobs.run_analysis(claimed[0],claimed[1])
    db.expire_all()
    return result


@pytest.mark.parametrize('kind',['jpg','jpeg','png'])
def test_actual_image_detection_bounds_and_artifact_integrity(vision,kind):
    db,_,media,client,case,evidence=saved(vision,kind)
    base,job_id=enqueue(client,case,evidence)
    assert execute(db,job_id),db.get(ProcessingJob,job_id).error_code
    run=db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id))
    frame=db.scalar(select(VisualFrame).where(VisualFrame.analysis_id==run.id))
    assert (frame.width,frame.height)==(700,577) and frame.timestamp_ms==0
    detections=list(db.scalars(select(VisualDetection).where(VisualDetection.frame_id==frame.id)))
    assert any(d.label=='dog' for d in detections)  # One genuine visible dog anchor, not general accuracy.
    for d in detections:
        assert 0<=d.x1<d.x2<=frame.width and 0<=d.y1<d.y2<=frame.height
        assert visual_model.CLASSES[d.class_id]==d.label and .35<=d.confidence<=1
        assert d.confidence==pytest.approx(d.provenance['objectness']*d.provenance['class_probability'],abs=1e-6)
    for annotated in ['true','false']:
        response=client.get(base+f'/visual-analyses/{run.id}/frames/{frame.id}/artifact?annotated={annotated}')
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert hashlib.sha256(response.content).hexdigest()==response.headers['x-content-sha256']
        assert Image.open(io.BytesIO(response.content)).size==(frame.width,frame.height)
    assert run.original_sha256==evidence['sha256']==hashlib.sha256(media[kind]).hexdigest()
    completed=list(db.scalars(select(AuditLog).where(AuditLog.action=='visual.completed',
        AuditLog.resource_type=='case',AuditLog.resource_id==UUID(case['id']),
        AuditLog.details['analysis_id'].astext==str(run.id))))
    assert len(completed)==1
    assert completed[0].details['evidence_id']==evidence['id']
    assert completed[0].details['sha256']==evidence['sha256']


def test_real_model_boxes_match_independent_onnx_runtime(vision):
    import numpy as np
    import onnxruntime as ort
    _,_,media=vision
    image=next(visual_inference.frames(media['jpg'],'image/jpeg'))['image']
    actual,_=visual_inference.detect(image)
    blob,ratio=visual_inference.prepare(image)
    options=ort.SessionOptions()
    options.intra_op_num_threads=2
    options.inter_op_num_threads=1
    reference=ort.InferenceSession(str(visual_model.path(None)),sess_options=options,providers=['CPUExecutionProvider'])
    raw=reference.run(None,{reference.get_inputs()[0].name:blob})[0][0]
    assert actual and raw.shape==(8400,85)
    for d in actual:
        index=d['provenance']['output_index']
        stride,side,local=(8,80,index) if index<6400 else (16,40,index-6400) if index<8000 else (32,20,index-8000)
        values=raw[index]
        label=int(values[5:].argmax())
        assert label==d['class_id']
        assert float(values[4]*values[5+label])==pytest.approx(d['confidence'],abs=2e-4)
        cx=(float(values[0])+local%side)*stride
        cy=(float(values[1])+local//side)*stride
        w,h=math.exp(float(values[2]))*stride,math.exp(float(values[3]))*stride
        expected=[max(0,min(700,(cx-w/2)/ratio)),max(0,min(577,(cy-h/2)/ratio)),max(0,min(700,(cx+w/2)/ratio)),max(0,min(577,(cy+h/2)/ratio))]
        assert [d[k] for k in ['x1','y1','x2','y2']]==pytest.approx(expected,abs=.05)


def test_video_actual_frame_timestamps_match_independent_ffprobe(vision,tmp_path):
    db,_,media,client,case,evidence=saved(vision,'mp4')
    base,job_id=enqueue(client,case,evidence)
    assert execute(db,job_id),db.get(ProcessingJob,job_id).error_code
    run=db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id))
    frames=list(db.scalars(select(VisualFrame).where(VisualFrame.analysis_id==run.id).order_by(VisualFrame.frame_index)))
    assert len(frames)>=5 and frames[0].frame_index==0
    target=tmp_path/'reviewed.mp4'
    target.write_bytes(media['mp4'])
    result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(target)],capture_output=True,check=True,timeout=20)
    timestamps=[float(f['best_effort_timestamp_time'])*1000 for f in json.loads(result.stdout)['frames']]
    for frame in frames:
        assert frame.timestamp_ms==pytest.approx(timestamps[frame.frame_index],abs=.05)
        assert (frame.width,frame.height)==(960,540)
    assert all(b.timestamp_ms-a.timestamp_ms>=get_settings().visual_interval_ms-.05 for a,b in zip(frames,frames[1:]))
    assert 'no tracking' in run.media['sampling']
    assert db.get(ProcessingJob,job_id).processed==db.get(ProcessingJob,job_id).total==len(frames)


def test_visual_routes_enforce_case_scope_roles_csrf_and_private_history(vision):
    from app.main import app
    db,new_user,_,client,case,evidence=saved(vision)
    other,researcher=new_user()
    base=f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}"
    assert TestClient(app).post(base+'/visual-analysis',json={}).status_code==401
    assert client.post(base+'/visual-analysis',json={}).status_code==403
    assert other.post(base+'/visual-analysis',json={},headers=csrf(other)).status_code==404
    base,job_id=enqueue(client,case,evidence)
    assert str(job_id) not in client.get('/api/v1/ingestion-jobs').text
    assert client.get('/api/v1/ingestion-jobs/'+str(job_id)).status_code==404
    assert 'lease_token' not in client.get(base+'/visual-jobs/'+str(job_id)).text
    assert execute(db,job_id)
    run=db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id))
    frame=db.scalar(select(VisualFrame).where(VisualFrame.analysis_id==run.id))
    suffixes=['/visual-jobs',f'/visual-jobs/{job_id}','/visual-analyses',f'/visual-analyses/{run.id}',f'/visual-analyses/{run.id}/frames',f'/visual-analyses/{run.id}/frames/{frame.id}/artifact']
    for suffix in suffixes:
        assert other.get(base+suffix).status_code==404
    assert client.post(f"/api/v1/cases/{case['id']}/members",json={'email':researcher.email},headers=csrf(client)).status_code==201
    assert other.get(base+f'/visual-analyses/{run.id}/frames').status_code==200
    assert other.get(base+f'/visual-analyses/{run.id}/frames/{frame.id}/artifact').status_code==200
    assert other.post(base+'/visual-analysis',json={'reanalyze':True},headers=csrf(other)).status_code==403
    assert other.post(base+f'/visual-jobs/{job_id}/retry',headers=csrf(other)).status_code==403
    wrong=create(client)
    assert client.get(f"/api/v1/cases/{wrong['id']}/evidence/{evidence['id']}/visual-analyses/{run.id}/frames/{frame.id}/artifact").status_code==404
    assert client.get(base+f'/visual-analyses/{run.id}/frames/{uuid4()}/artifact').status_code==404


def test_duplicate_active_completed_and_explicit_versioning(vision):
    db,_,_,client,case,evidence=saved(vision)
    base,job_id=enqueue(client,case,evidence)
    assert client.post(base+'/visual-analysis',json={},headers=csrf(client)).json()['id']==str(job_id)
    assert execute(db,job_id)
    response=client.post(base+'/visual-analysis',json={},headers=csrf(client))
    assert response.status_code==200 and response.json()['id']==str(job_id)
    response=client.post(base+'/visual-analysis',json={'reanalyze':True},headers=csrf(client))
    assert response.status_code==202 and response.json()['id']!=str(job_id)
    assert execute(db,UUID(response.json()['id']))
    runs=list(db.scalars(select(VisualAnalysis).where(VisualAnalysis.evidence_id==UUID(evidence['id']))))
    assert len(runs)==2 and all(r.status=='completed' and r.original_sha256==evidence['sha256'] for r in runs)


def test_integrity_failure_never_publishes_visual_results(vision):
    db,_,_,client,case,evidence=saved(vision)
    db.get(Evidence,UUID(evidence['id'])).sha256='0'*64
    db.commit()
    base,job_id=enqueue(client,case,evidence)
    assert not execute(db,job_id)
    run=db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id))
    assert run.status=='failed' and run.error_code=='integrity_failed'
    assert client.get(base+f'/visual-analyses/{run.id}/frames').status_code==409
    assert db.scalar(select(func.count()).select_from(VisualFrame).where(VisualFrame.analysis_id==run.id))==0


def test_visual_failure_retry_retains_attempts(vision,monkeypatch):
    db,_,_,client,case,evidence=saved(vision)
    base,job_id=enqueue(client,case,evidence)
    original=visual_inference.detect
    def interrupted(*args): raise visual_inference.VisualFailure('artifact_failed',True)
    monkeypatch.setattr(visual_inference,'detect',interrupted)
    assert not execute(db,job_id)
    job=db.get(ProcessingJob,job_id)
    assert job.status=='queued' and job.attempts==1
    job.next_attempt_at=now()-timedelta(seconds=1)
    db.commit()
    monkeypatch.setattr(visual_inference,'detect',original)
    assert execute(db,job_id)
    states=list(db.scalars(select(VisualAnalysis.status).where(VisualAnalysis.job_id==job_id).order_by(VisualAnalysis.attempt)))
    assert states==['failed','completed']


def test_visual_stale_fencing_retains_interrupted_attempt(vision):
    db,_,_,client,case,evidence=saved(vision)
    base,job_id=enqueue(client,case,evidence)
    old=analysis_worker.claim(db,db.bind,'visual_analysis')
    db.add(VisualAnalysis(job_id=job_id,evidence_id=UUID(evidence['id']),attempt=1,status='processing',original_sha256=evidence['sha256'],pipeline_version=visual_jobs.PIPELINE_VERSION))
    db.get(ProcessingJob,job_id).lease_expires_at=now()-timedelta(seconds=1)
    db.commit()
    db.bind.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':old[2]})
    current=analysis_worker.claim(db,db.bind,'visual_analysis')
    assert old[1]!=current[1]
    assert not visual_jobs.run_analysis(old[0],old[1])
    assert visual_jobs.run_analysis(current[0],current[1])
    db.expire_all()
    assert list(db.scalars(select(VisualAnalysis.status).where(VisualAnalysis.job_id==job_id).order_by(VisualAnalysis.attempt)))==['interrupted','completed']


def test_visual_access_revoked_before_processing(vision):
    db,new_user,_,client,case,evidence=saved(vision)
    member,user=new_user('investigator')
    url=f"/api/v1/cases/{case['id']}"
    assert client.post(url+'/members',json={'email':user.email},headers=csrf(client)).status_code==201
    base,job_id=enqueue(member,case,evidence)
    assert client.delete(url+'/members/'+str(user.id),headers=csrf(client)).status_code==200
    assert not execute(db,job_id)
    assert db.get(ProcessingJob,job_id).error_code=='access_revoked'


def test_unsupported_and_invalid_visual_inputs(vision):
    db,new_user,media=vision
    client,_=new_user()
    case=create(client)
    from app.models import Judgment
    doc=db.scalar(select(Judgment))
    raw=PrivateStorage(Path(os.environ['PRIVATE_ROOT'])).read_verified(doc.storage_key,doc.sha256)
    response=upload(client,case['id'],raw,'pdf',media['provenance'])
    assert response.status_code==201
    evidence=response.json()
    assert client.post(f"/api/v1/cases/{case['id']}/evidence/{evidence['id']}/visual-analysis",json={},headers=csrf(client)).status_code==422
    for content,mime in [(b'not an image','image/png'),(b'not a video','video/mp4')]:
        with pytest.raises(visual_inference.VisualFailure): list(visual_inference.frames(content,mime))


def test_visual_model_and_media_limits_fail_explicitly(vision,monkeypatch):
    db,_,media,client,case,evidence=saved(vision)
    base,job_id=enqueue(client,case,evidence)
    def unavailable(*args): raise visual_model.ModelUnavailable('Controlled negative fixture')
    monkeypatch.setattr(visual_model,'verify',unavailable)
    assert not execute(db,job_id)
    assert db.get(ProcessingJob,job_id).error_code=='model_unavailable'
    monkeypatch.setattr(get_settings(),'visual_max_pixels',1)
    with pytest.raises(visual_inference.VisualFailure,match='pixel_limit_exceeded'):
        list(visual_inference.frames(media['jpg'],'image/jpeg'))


def test_video_frame_and_duration_limits(vision,monkeypatch):
    _,_,media=vision
    monkeypatch.setattr(get_settings(),'visual_max_seconds',1)
    with pytest.raises(visual_inference.VisualFailure,match='duration_limit_exceeded'):
        list(visual_inference.frames(media['mp4'],'video/mp4'))
    monkeypatch.setattr(get_settings(),'visual_max_seconds',120)
    monkeypatch.setattr(get_settings(),'visual_max_frames',1)
    with pytest.raises(visual_inference.VisualFailure,match='frame_limit_exceeded'):
        list(visual_inference.frames(media['mp4'],'video/mp4'))


def test_asynchronous_queue_and_artifact_tamper_protection(vision,monkeypatch):
    db,_,_,client,case,evidence=saved(vision)
    original=visual_inference.detect
    def forbidden(*args): raise AssertionError('API must not execute model inference')
    monkeypatch.setattr(visual_inference,'detect',forbidden)
    base,job_id=enqueue(client,case,evidence)
    monkeypatch.setattr(visual_inference,'detect',original)
    assert execute(db,job_id)
    run=db.scalar(select(VisualAnalysis).where(VisualAnalysis.job_id==job_id))
    frame=db.scalar(select(VisualFrame).where(VisualFrame.analysis_id==run.id))
    db.get(EvidenceArtifact,frame.annotated_artifact_id).sha256='0'*64
    db.commit()
    assert client.get(base+f'/visual-analyses/{run.id}/frames/{frame.id}/artifact').status_code==409


def test_visual_manual_retry_exhaustion_and_attempt_history(vision,monkeypatch):
    db,_,_,client,case,evidence=saved(vision)
    base,job_id=enqueue(client,case,evidence)
    def invalid(*args): raise visual_inference.VisualFailure('invalid_media')
    monkeypatch.setattr(visual_inference,'detect',invalid)
    for attempt in range(1,4):
        assert not execute(db,job_id)
        job=db.get(ProcessingJob,job_id)
        assert job.status=='failed' and job.attempts==attempt
        response=client.post(base+f'/visual-jobs/{job_id}/retry',headers=csrf(client))
        assert response.status_code==(202 if attempt<3 else 409)
    assert db.scalar(select(func.count()).select_from(VisualAnalysis).where(VisualAnalysis.job_id==job_id))==3


def test_visual_queue_limit_and_archival(vision):
    db,new_user,media=vision
    client,user=new_user()
    case=create(client)
    for kind in ['jpg','png','mp4']:
        evidence=upload(client,case['id'],media[kind],kind,media['provenance']).json()
        enqueue(client,case,evidence)
    another=create(client)
    evidence=upload(client,another['id'],media['jpg'],'jpg',media['provenance']).json()
    base=f"/api/v1/cases/{another['id']}/evidence/{evidence['id']}"
    assert client.post(base+'/visual-analysis',json={},headers=csrf(client)).status_code==429
    assert client.post(f"/api/v1/cases/{another['id']}/archive",headers=csrf(client)).status_code==200
    assert client.post(base+'/visual-analysis',json={},headers=csrf(client)).status_code==409
