"""Opt-in real visual flow through authenticated HTTP; licensed media only, no acquisition."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import httpx
from sqlalchemy import select,func
from sqlalchemy.orm import Session

from app import models,visual_model
from app.config import get_settings
from app.database import get_engine
from app.storage import PrivateStorage


def preservation():
    root=get_settings().private_root
    baseline=json.loads((root/'auth/phase5-baseline.json').read_text())
    classes={getattr(models,name).__tablename__:getattr(models,name) for name in ['Judgment','JudgmentPassage','Case','Evidence','EvidenceArtifact','ProcessingJob','AnalysisModel','EvidenceAnalysis','AnalysisPage','AnalysisEntity']}
    counts={}
    with Session(get_engine()) as db:
        for table,expected in baseline.items():
            model=classes[table]
            current={str(row.id):hashlib.sha256(json.dumps({c.name:getattr(row,c.name) for c in model.__table__.columns},sort_keys=True,default=str).encode()).hexdigest() for row in db.scalars(select(model))}
            assert all(current.get(key)==digest for key,digest in expected.items()),'An existing baseline row changed: '+table
            counts[table]=dict(baseline=len(expected),current=len(current))
        originals=list(db.scalars(select(models.Judgment)))+list(db.scalars(select(models.Evidence)))
        store=PrivateStorage(root)
        for item in originals: store.read_verified(item.storage_key,item.sha256)
        artifacts=list(db.scalars(select(models.EvidenceArtifact)))
        for item in artifacts: store.read_verified(item.storage_key,item.sha256)
        from app.vectors import collection
        vectors=collection().count()
        assert vectors==3834 and counts['judgments']['current']==50 and counts['judgment_passages']['current']==3834
    return dict(baseline_rows_unchanged=counts,verified_original_hashes=len(originals),verified_derived_hashes=len(artifacts),chroma_embeddings=vectors)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing',action='store_true')
    parser.add_argument('--preservation-only',action='store_true')
    args=parser.parse_args()
    if args.preservation_only:
        print(json.dumps(preservation(),indent=2))
        return
    root=get_settings().private_root
    store=PrivateStorage(root)
    visual_model.verify(root)
    owner=json.loads(store.path('auth/phase3-flow.json').read_text())
    media_folder=root/'visual-test-media'
    media=json.loads((media_folder/'provenance.json').read_text())
    receipt=store.path('auth/phase5-flow.json')
    if args.verify_existing and not receipt.exists():
        parser.error('Run the opt-in authorized flow once before verifying existing results')
    state=json.loads(receipt.read_text()) if receipt.exists() else dict(case_id=owner['case_id'],samples={})
    with httpx.Client(base_url='http://frontend:3000/api/backend/',timeout=90) as client:
        def request(method,path,**kwargs):
            response=client.request(method,path,headers={'X-CSRF-Token':client.cookies.get('legal_csrf','')},**kwargs)
            if not response.is_success:
                raise RuntimeError(f'Local visual verification HTTP {method}: {response.status_code}')
            return response
        request('GET','auth/csrf')
        request('POST','auth/login',json={'email':owner['email'],'password':owner['password']})
        try:
            if not args.verify_existing:
                for kind,filename in [('image','labrador.jpg'),('video','jijiga-960.mp4')]:
                    if kind not in state['samples']:
                        content=(media_folder/filename).read_bytes()
                        assert hashlib.sha256(content).hexdigest()==media[filename]['sha256']
                        provenance=('Authorized public-source visual verification. '+
                            (media[filename]['attribution']+' '+media[filename]['page']+' Annotation derivatives retain CC BY-SA 3.0.' if kind=='image' else
                             media['jijiga.ogv']['attribution']+' '+media['jijiga.ogv']['page']+' '+media[filename]['transformation']+' Source OGV SHA-256: '+media['jijiga.ogv']['sha256']))
                        saved=request('POST',f"cases/{state['case_id']}/evidence",params={'filename':'phase5-licensed-'+('labrador.jpg' if kind=='image' else 'jijiga.mp4'),'provenance':provenance},content=content).json()
                        assert saved['sha256']==media[filename]['sha256']
                        state['samples'][kind]=dict(evidence_id=saved['id'],sha256=saved['sha256'])
                        receipt.write_text(json.dumps(state,indent=2))
                    sample=state['samples'][kind]
                    base=f"cases/{state['case_id']}/evidence/{sample['evidence_id']}"
                    result=request('POST',base+'/visual-analysis',json={}).json()
                    sample['job_id']=result['id']
                    receipt.write_text(json.dumps(state,indent=2))
            report=dict(samples={},model=dict(name=visual_model.MODEL,revision=visual_model.REVISION,sha256=visual_model.SHA256,bytes=visual_model.SIZE),
                interpretation='Actual sampled object candidates. Not facial identification, unique-person counts, tracking, criminal activity findings or general accuracy. Timings are observations on this local CPU.')
            for kind,sample in state['samples'].items():
                base=f"cases/{state['case_id']}/evidence/{sample['evidence_id']}"
                deadline=time.monotonic()+720
                transitions=[]
                while True:
                    job=request('GET',base+'/visual-jobs/'+sample['job_id']).json()
                    progress=[job['status'],job['processed'],job['total']]
                    if not transitions or transitions[-1]!=progress: transitions.append(progress)
                    if job['status'] in ['completed','failed']: break
                    if time.monotonic()>deadline: raise RuntimeError('Visual worker exceeded verification budget')
                    time.sleep(2)
                assert job['status']=='completed',job['error_code']
                run=next(r for r in job['runs'] if r['status']=='completed')
                sample['analysis_id']=run['id']
                assert run['model']['file_hashes'][visual_model.NAME]==visual_model.SHA256
                original=request('GET',base+'/download').content
                assert hashlib.sha256(original).hexdigest()==sample['sha256']==run['original_sha256']
                saved_frames=[]
                offset=0
                while True:
                    result=request('GET',base+f"/visual-analyses/{run['id']}/frames",params={'limit':25,'offset':offset}).json()
                    saved_frames.extend(result['items'])
                    offset+=len(result['items'])
                    if offset>=result['total']: break
                    assert result['items']
                labels={}
                import cv2
                import numpy as np
                for frame in saved_frames:
                    path=base+f"/visual-analyses/{run['id']}/frames/{frame['id']}/artifact"
                    for annotated in [False,True]:
                        response=request('GET',path,params={'annotated':str(annotated).lower()})
                        assert hashlib.sha256(response.content).hexdigest()==response.headers['x-content-sha256']
                        image=cv2.imdecode(np.frombuffer(response.content,dtype=np.uint8),cv2.IMREAD_COLOR)
                        assert image.shape[:2]==(frame['height'],frame['width'])
                        if not annotated: assert hashlib.sha256(image.tobytes()).hexdigest()==frame['pixel_sha256']
                    for d in frame['detections']:
                        assert 0<=d['x1']<d['x2']<=frame['width'] and 0<=d['y1']<d['y2']<=frame['height']
                        assert visual_model.CLASSES[d['class_id']]==d['label']
                        assert abs(d['confidence']-d['provenance']['objectness']*d['provenance']['class_probability'])<1e-6
                        labels[d['label']]=labels.get(d['label'],0)+1
                if kind=='video':
                    path=media_folder/'jijiga-960.mp4'
                    result=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)],capture_output=True,check=True,timeout=20)
                    timestamps=[float(f['best_effort_timestamp_time'])*1000 for f in json.loads(result.stdout)['frames']]
                    for frame in saved_frames: assert abs(frame['timestamp_ms']-timestamps[frame['frame_index']])<.05
                report['samples'][kind]=dict(evidence_id=sample['evidence_id'],job_id=sample['job_id'],analysis_id=sample['analysis_id'],
                    original_sha256=sample['sha256'],attempts=job['attempts'],started_at=job['started_at'],finished_at=job['finished_at'],
                    transitions=transitions,media=run['media'],settings=run['settings'],
                    frames=[{key:f[key] for key in ['frame_index','timestamp_ms','width','height','pixel_sha256','inference_ms']} for f in saved_frames],
                    candidate_counts=labels,first_frame_candidates=[{key:d[key] for key in ['class_id','label','confidence','x1','y1','x2','y2']} for d in saved_frames[0]['detections']])
            receipt.write_text(json.dumps(state,indent=2))
            report['preservation']=preservation()
            store.path('auth/phase5-evaluation.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        finally:
            request('POST','auth/logout')


if __name__=='__main__':
    main()
