"""Opt-in local operator demonstration, preservation and authorized saved-result checks.

--run-flow registers one dedicated integration account and locally grants investigator
role and membership of the existing genuine-source verification case. No existing user,
case, evidence or analysis row is edited. Credentials and outputs remain private.
Default/--verify-existing only retrieves a previously completed demonstration.
"""
import argparse,hashlib,json,secrets,time
from uuid import uuid4,UUID
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models,research_jobs,vectors
from app.auth import audit
from app.config import get_settings
from app.database import get_engine
from app.storage import PrivateStorage

def preservation():
    root=get_settings().private_root
    baseline=json.loads((root/'auth/phase6-baseline.json').read_text())
    counts={}
    with Session(get_engine()) as db:
        for name,expected in baseline.items():
            model=getattr(models,name)
            def identity(row):return str(row.id) if hasattr(row,'id') else str(row.case_id)+':'+str(row.user_id)
            current={identity(row):hashlib.sha256(json.dumps({c.name:getattr(row,c.name) for c in model.__table__.columns},sort_keys=True,default=str).encode()).hexdigest() for row in db.scalars(select(model))}
            assert all(current.get(key)==value for key,value in expected.items()),'Existing row changed: '+name
            counts[name]=dict(baseline=len(expected),current=len(current))
        originals=list(db.scalars(select(models.Judgment)))+list(db.scalars(select(models.Evidence)))
        artifacts=list(db.scalars(select(models.EvidenceArtifact)))
        store=PrivateStorage(root)
        for row in originals+artifacts:store.read_verified(row.storage_key,row.sha256)
        assert counts['Judgment']['current']==50 and counts['JudgmentPassage']['current']==3834 and vectors.collection().count()==3834
    return dict(baseline_rows_unchanged=counts,verified_original_hashes=len(originals),verified_artifact_hashes=len(artifacts),chroma_embeddings=vectors.collection().count())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-flow',action='store_true');parser.add_argument('--verify-existing',action='store_true');parser.add_argument('--preservation-only',action='store_true')
    args=parser.parse_args();root=get_settings().private_root
    if args.preservation_only:print(json.dumps(preservation(),indent=2));return
    receipt=root/'auth/phase6-flow.json'
    if receipt.exists():state=json.loads(receipt.read_text())
    elif args.run_flow:
        owner=json.loads((root/'auth/phase3-flow.json').read_text())
        state=dict(email='phase6-'+uuid4().hex+'@example.org',password=secrets.token_urlsafe(30),case_id=owner['case_id'])
        receipt.write_text(json.dumps(state,indent=2))
    else:parser.error('No Phase 6 flow receipt; run --run-flow explicitly once with trusted local operator access')
    with httpx.Client(base_url='http://frontend:3000/api/backend/',timeout=120) as client:
        def request(method,path,**kwargs):
            response=client.request(method,path,headers={'X-CSRF-Token':client.cookies.get('legal_csrf','')},**kwargs)
            if not response.is_success:raise RuntimeError(f'Phase 6 local HTTP {method}: {response.status_code}')
            return response
        request('GET','auth/csrf')
        if 'user_id' not in state:
            if not args.run_flow:raise RuntimeError('Flow setup incomplete; explicit --run-flow required')
            with Session(get_engine()) as db:user=db.scalar(select(models.User).where(models.User.email==state['email']))
            if not user:
                created=request('POST','auth/register',json=dict(email=state['email'],password=state['password'],display_name='Authorized Phase 6 integration reviewer')).json()
                identifier=UUID(created['id'])
            else:identifier=user.id
            with Session(get_engine()) as db:
                user=db.get(models.User,identifier)
                # Trusted local operator grant; registration never accepts a privileged role.
                if user.role!='legal_researcher':raise RuntimeError('Unexpected role for dedicated verification account')
                user.role='investigator'
                db.add(models.CaseMember(case_id=UUID(state['case_id']),user_id=user.id))
                audit(db,user,'research.verification_operator_grant','user',user.id,operator='explicit local verify_phase6 --run-flow')
                db.commit()
            state['user_id']=str(identifier);receipt.write_text(json.dumps(state,indent=2))
        request('POST','auth/login',json=dict(email=state['email'],password=state['password']))
        try:
            base=f"cases/{state['case_id']}"
            if 'job_id' not in state:
                if not args.run_flow:raise RuntimeError('No saved job; explicit --run-flow required')
                available=request('GET',base+'/research-inputs').json()['items']
                chosen=next(p for p in available if p['text'].strip())
                selected=dict(evidence_id=chosen['evidence_id'],page_id=chosen['page_id'],char_start=0,char_end=min(700,len(chosen['text'])))
                state['selection']=selected
                state['job_id']=request('POST',base+'/research-jobs',json=dict(selections=[selected],limit=3)).json()['id']
                receipt.write_text(json.dumps(state,indent=2))
            deadline=time.monotonic()+650;transitions=[]
            while True:
                job=request('GET',base+'/research-jobs/'+state['job_id']).json()
                current=[job['status'],job['processed'],job['total']]
                if not transitions or transitions[-1]!=current:transitions.append(current)
                if job['status'] in ['completed','failed']:break
                if time.monotonic()>deadline:raise RuntimeError('Research verification deadline exceeded')
                time.sleep(2)
            assert job['status']=='completed',job['error_code']
            run=next(r for r in job['runs'] if r['status']=='completed')
            result=request('GET',base+'/research-runs/'+run['id'],params={'limit':100}).json()
            assert result['outcome']=='sources_retrieved' and result['inputs'] and result['items']
            with Session(get_engine()) as db:
                for item in result['items']:
                    research_jobs.validate_citation(db,item['source'],True)
            if args.run_flow and 'review_id' not in state:
                item=result['items'][0]
                review=request('POST',base+f"/research-runs/{run['id']}/results/{item['id']}/reviews",json=dict(disposition='needs_verification',note='Authorized integration check: passage provenance verified; legal relevance and applicability require independent human review.')).json()
                state['review_id']=review['id']
            state['run_id']=run['id'];receipt.write_text(json.dumps(state,indent=2))
            search=request('POST','research/search',json=dict(query='fundamental rights and equality before the law',limit=5)).json()
            report=dict(job_id=job['id'],run_id=run['id'],status=job['status'],attempts=job['attempts'],transitions=transitions,
                started_at=run['created_at'],finished_at=run['finished_at'],actual_research=result,actual_public_search=search,preservation=preservation())
            (root/'auth/phase6-evaluation.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(dict(status=report['status'],attempts=job['attempts'],job_id=job['id'],run_id=run['id'],transitions=transitions,
                inputs=len(result['inputs']),source_results=len(result['items']),statutory_results=sum(x['source']['kind']=='statute' for x in result['items']),
                original_hashes=report['preservation']['verified_original_hashes'],judgment_embeddings=report['preservation']['chroma_embeddings'],
                public_search=[dict(title=i['title'],source_url=i['source_url'],page_number=i['page_number'],distance=i['distance']) for i in search['judgments']]),indent=2))
        finally:request('POST','auth/logout')

if __name__=='__main__':main()
