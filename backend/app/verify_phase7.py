"""Opt-in local report demonstration and read-only preservation verification.

--run-flow uses the existing Phase 6 integration investigator and creates a dedicated
new reviewer account, locally grants it lawyer role/case membership, then exercises
real HTTP report generation, annotation, approval and rejection. No existing role,
case, evidence or analysis record is changed. Credentials/PDFs stay in private storage.
--verify-existing retrieves saved reports only; --preservation-only checks the baseline.
"""
import argparse
import hashlib
import io
import json
import secrets
import time
from datetime import datetime
from uuid import UUID, uuid4
import httpx
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import models, vectors
from app.auth import audit
from app.config import get_settings
from app.database import get_engine
from app.storage import PrivateStorage


def preservation():
    root = get_settings().private_root
    baseline = json.loads((root/'auth/phase7-baseline.json').read_text())
    counts = {}
    with Session(get_engine()) as db:
        for name, expected in baseline['rows'].items():
            table = models.Base.metadata.tables[name]
            current = {':'.join(str(row[c.name]) for c in table.primary_key.columns): hashlib.sha256(json.dumps(dict(row), sort_keys=True, default=str).encode()).hexdigest()
                for row in db.execute(select(table)).mappings()}
            assert all(current.get(key) == value for key, value in expected.items()), 'Existing row changed: '+name
            counts[name] = dict(baseline=len(expected), current=len(current))
        originals = list(db.scalars(select(models.Judgment)))+list(db.scalars(select(models.Evidence)))
        artifacts = list(db.scalars(select(models.EvidenceArtifact)))
        store = PrivateStorage(root)
        for row in originals+artifacts:
            store.read_verified(row.storage_key, row.sha256)
    data = vectors.collection().get(include=['embeddings', 'metadatas'])
    digest = hashlib.sha256()
    for key, embedding, metadata in sorted(zip(data['ids'], data['embeddings'], data['metadatas']), key=lambda x: x[0]):
        digest.update(key.encode()+b'\0'); digest.update(embedding.astype('<f4').tobytes()); digest.update(json.dumps(metadata, sort_keys=True).encode())
    assert len(data['ids']) == baseline['embedding_count'] == 3834
    assert digest.hexdigest() == baseline['embedding_sha256']
    assert len(originals) == 57 and counts['judgments']['current'] == 50
    return dict(baseline_rows_unchanged=counts, original_hashes=len(originals), artifact_hashes=len(artifacts),
        embedding_count=len(data['ids']), embedding_sha256=digest.hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-flow', action='store_true')
    parser.add_argument('--verify-existing', action='store_true')
    parser.add_argument('--preservation-only', action='store_true')
    args = parser.parse_args()
    root = get_settings().private_root
    if args.preservation_only:
        print(json.dumps(preservation(), indent=2)); return
    receipt = root/'auth/phase7-flow.json'
    existing = json.loads((root/'auth/phase6-flow.json').read_text())
    if receipt.exists():
        state = json.loads(receipt.read_text())
    elif args.run_flow:
        state = dict(case_id=existing['case_id'], email='phase7-review-'+uuid4().hex+'@example.org', password=secrets.token_urlsafe(32), reports=[])
        receipt.write_text(json.dumps(state, indent=2))
    else:
        parser.error('No saved Phase 7 receipt; explicit --run-flow is required once')
    base = 'cases/'+state['case_id']
    summary = []
    with httpx.Client(base_url='http://frontend:3000/api/backend/', timeout=120) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, headers={'X-CSRF-Token': client.cookies.get('legal_csrf', '')}, **kwargs)
            if not response.is_success:
                raise RuntimeError(f'Phase 7 local HTTP {method}: {response.status_code}')
            return response
        request('GET', 'auth/csrf')
        if args.run_flow and 'reviewer_id' not in state:
            response = request('POST', 'auth/register', json=dict(email=state['email'], password=state['password'], display_name='Authorized Phase 7 report reviewer'))
            uid = UUID(response.json()['id'])
            with Session(get_engine()) as db:
                user = db.get(models.User, uid)
                assert user.role == 'legal_researcher'
                user.role = 'lawyer'
                db.add(models.CaseMember(case_id=UUID(state['case_id']), user_id=uid))
                audit(db, user, 'report.verification_operator_grant', 'user', uid, operator='explicit local verify_phase7 --run-flow')
                db.commit()
            state['reviewer_id'] = str(uid); receipt.write_text(json.dumps(state, indent=2))
        if args.run_flow:
            request('POST', 'auth/login', json=dict(email=existing['email'], password=existing['password']))
            try:
                for ordinal, decision in enumerate(['approved', 'rejected']):
                    if len(state['reports']) <= ordinal:
                        job = request('POST', base+'/report-jobs', json=dict(title='Evidence-grounded investigation report', new_version=True)).json()
                        state['reports'].append(dict(job_id=job['id'], decision=decision))
                        receipt.write_text(json.dumps(state, indent=2))
                    saved = state['reports'][ordinal]
                    deadline = time.monotonic()+650
                    while True:
                        job = request('GET', base+'/report-jobs/'+saved['job_id']).json()
                        if job['status'] in ['completed', 'failed']:
                            break
                        if time.monotonic() > deadline:
                            raise RuntimeError('Report demonstration deadline exceeded')
                        time.sleep(2)
                    assert job['status'] == 'completed', job['error_code']
                    report = next(r for r in job['reports'] if r['status'] == 'completed')
                    saved['report_id'] = report['id']; receipt.write_text(json.dumps(state, indent=2))
                    if not report['reviews']:
                        request('POST', base+f'/reports/{report["id"]}/reviews', json=dict(disposition='note', note='Source references inspected in the authorized local integration demonstration. Automated observations require independent human verification; no guilt or statutory applicability finding is made.', pdf_sha256=report['pdf_sha256'], snapshot_sha256=report['snapshot_sha256']))
            finally:
                request('POST', 'auth/logout')
        # Logout deliberately clears the previous identity's CSRF cookie.
        request('GET', 'auth/csrf')
        request('POST', 'auth/login', json=dict(email=state['email'], password=state['password']))
        try:
            for saved in state['reports']:
                path = base+'/reports/'+saved['report_id']
                report = request('GET', path).json()
                pdf = request('GET', path+'/pdf').content
                source = request('GET', path+'/snapshot').content
                assert hashlib.sha256(pdf).hexdigest() == report['pdf_sha256']
                assert hashlib.sha256(source).hexdigest() == report['snapshot_sha256']
                pages = PdfReader(io.BytesIO(pdf)).pages
                pdf_text = '\n'.join(page.extract_text() for page in pages)
                snapshot = json.loads(source)
                assert len(pages) == report['page_count'] and len(pages) > 2
                assert snapshot['case']['id'] == state['case_id'] and snapshot['imported_statutory_provisions'] == 0
                assert 'Verified statutory analysis is unavailable' in pdf_text
                for item in snapshot['evidence']:
                    assert item['sha256'] in pdf_text.replace('\n', '')
                if args.run_flow and report['review_status'] == 'draft':
                    request('POST', path+'/reviews', json=dict(disposition=saved['decision'], note='Authorized integration workflow decision: reviewed the source snapshot and PDF hashes. This attributed decision does not establish legal guilt, admissibility or current statutory applicability.', pdf_sha256=report['pdf_sha256'], snapshot_sha256=report['snapshot_sha256']))
                    report = request('GET', path).json()
                assert report['review_status'] == saved['decision']
                assert request('GET', path+'/pdf').content == pdf
                audit_rows = request('GET', path+'/audit').json()['items']
                assert any(x['action'] == 'report.completed' for x in audit_rows)
                assert any(x['action'] == 'report.reviewed' for x in audit_rows)
                summary.append(dict(report_id=report['id'], job_id=report['job_id'], version=report['version'], pages=len(pages), bytes=len(pdf),
                    pdf_sha256=report['pdf_sha256'], snapshot_sha256=report['snapshot_sha256'], review_status=report['review_status'],
                    coverage=snapshot['coverage'], generation_seconds=(datetime.fromisoformat(report['finished_at'])-datetime.fromisoformat(report['created_at'])).total_seconds()))
        finally:
            request('POST', 'auth/logout')
    result = dict(reports=summary, preservation=preservation())
    (root/'auth/phase7-evaluation.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
