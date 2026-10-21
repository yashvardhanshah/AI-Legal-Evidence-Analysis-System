"""Real-source report/PDF/authorization tests in rolled-back PostgreSQL transactions."""
from datetime import timedelta
import hashlib
import io
import json
import os
from pathlib import Path
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_phase3 import workspace, real_media, csrf, create
from app import analysis_worker, report_jobs, report_sources, research_jobs
from app.auth import now
from app.models import CaseMember, Evidence, ReportVersion, ReportReview, ProcessingJob, AuditLog, ResearchResult
from app.storage import PrivateStorage, StorageError
from pypdf import PdfReader


@pytest.fixture
def reports(workspace, monkeypatch):
    db, new_user, _, _ = workspace
    root = Path(os.environ['PRIVATE_ROOT'])
    private = report_jobs.get_settings().private_root
    class SourceStore(PrivateStorage):
        def read_verified(self, key, expected):
            if self.path(key).exists():
                return super().read_verified(key, expected)
            return PrivateStorage(root).read_verified(key, expected)
    monkeypatch.setattr(report_sources, 'PrivateStorage', lambda _: SourceStore(private))
    monkeypatch.setattr(research_jobs, 'PrivateStorage', lambda _: SourceStore(private))
    monkeypatch.setattr(report_jobs, 'get_engine', lambda: db.bind)
    monkeypatch.setattr(report_jobs, 'Session', lambda bind: Session(bind=bind, join_transaction_mode='create_savepoint'))
    client, user = new_user('investigator')
    evidence = db.scalar(select(Evidence).order_by(Evidence.created_at).limit(1))
    db.add(CaseMember(case_id=evidence.case_id, user_id=user.id)); db.commit()
    try:
        yield db, new_user, client, user, f'/api/v1/cases/{evidence.case_id}', evidence
    finally:
        db.bind.execute(text('SELECT pg_advisory_unlock_all()'))


def enqueue(reports, **kwargs):
    _, _, client, _, base, _ = reports
    # Isolate each rollback fixture from preserved real demonstration reports.
    # Repeated requests within the same fixture still exercise actual reuse.
    kwargs.setdefault('title', 'Authorized report verification '+str(reports[3].id))
    response = client.post(base+'/report-jobs', json=kwargs, headers=csrf(client))
    assert response.status_code in {200, 202}, response.text
    return UUID(response.json()['id'])


def execute(reports, job_id):
    db = reports[0]
    claimed = analysis_worker.claim(db, db.bind, 'case_report')
    assert claimed and claimed[0] == job_id
    success = report_jobs.run_analysis(claimed[0], claimed[1])
    db.expire_all()
    return success, claimed


def completed(reports):
    job_id = enqueue(reports)
    success, _ = execute(reports, job_id)
    job = reports[0].get(ProcessingJob, job_id)
    assert success, job.error_code
    return reports[0].scalar(select(ReportVersion).where(ReportVersion.job_id == job_id, ReportVersion.status == 'completed'))


def test_genuine_case_report_pdf_source_hashes_and_readability(reports):
    db, _, client, _, base, evidence = reports
    report = completed(reports)
    response = client.get(base+f'/reports/{report.id}/pdf')
    assert response.status_code == 200 and response.headers['content-type'] == 'application/pdf'
    assert hashlib.sha256(response.content).hexdigest() == report.pdf_sha256
    pdf = PdfReader(io.BytesIO(response.content))
    contents = '\n'.join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) == report.page_count and len(pdf.pages) > 2
    assert 'Evidence Integrity Appendix' in contents and 'Verified statutory analysis is unavailable' in contents
    assert 'not a finalized investigation' in contents
    assert str(evidence.id) in contents and evidence.sha256 in contents.replace('\n', '')
    source = client.get(base+f'/reports/{report.id}/snapshot')
    assert hashlib.sha256(source.content).hexdigest() == report.snapshot_sha256
    body = source.json()
    assert body['case']['id'] == str(evidence.case_id) and body['llm_enabled'] is False
    assert body['statutory_analysis'] == 'unavailable' and body['imported_statutory_provisions'] == 0
    for doc in body['documents']:
        for page in doc['pages']:
            assert hashlib.sha256(page['text'].encode()).hexdigest() == page['text_sha256']
            for entity in page['entities']:
                assert page['text'][entity['char_start']:entity['char_end']] == entity['text']
    for run in body['research']:
        for item in run['results']:
            original = db.get(ResearchResult, UUID(item['id']))
            assert item['citation'] == original.citation and item['citation']['kind'] == 'judgment'
    for key in ['storage_key', 'pdf_key', 'password_hash']:
        assert key not in source.text
    assert client.get(base+f'/reports/{report.id}/pdf?preview=true').headers['content-disposition'].startswith('inline')


@pytest.mark.parametrize('path', ['reports', 'report-jobs', 'reports/{id}', 'reports/{id}/pdf', 'reports/{id}/snapshot', 'reports/{id}/provenance', 'reports/{id}/audit', 'report-jobs/{job}'])
def test_all_report_reads_require_case_access(reports, path):
    _, new_user, _, _, base, _ = reports
    report = completed(reports)
    other, _ = new_user('lawyer')
    response = other.get(base+'/'+path.format(id=report.id, job=report.job_id))
    assert response.status_code == 404
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anonymous:
        assert anonymous.get(base+'/'+path.format(id=report.id, job=report.job_id)).status_code == 401


def test_duplicate_and_new_versions_are_immutable(reports):
    db, _, client, _, base, _ = reports
    job_id = enqueue(reports)
    assert enqueue(reports) == job_id
    assert execute(reports, job_id)[0]
    report = db.scalar(select(ReportVersion).where(ReportVersion.job_id == job_id))
    original = (report.pdf_sha256, report.snapshot_sha256, report.snapshot)
    assert enqueue(reports) == job_id
    new_id = enqueue(reports, new_version=True)
    assert new_id != job_id and execute(reports, new_id)[0]
    history = client.get(base+'/reports').json()['items']
    assert history[0]['version'] == report.version+1
    db.refresh(report)
    assert (report.pdf_sha256, report.snapshot_sha256, report.snapshot) == original
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text('UPDATE report_versions SET title=:title WHERE id=:id'), {'title': 'Forbidden published edit', 'id': report.id})


def review_body(report, disposition='note'):
    return dict(disposition=disposition, note='Authorized integration review: source references inspected; no finding of guilt or legal applicability.', pdf_sha256=report.pdf_sha256, snapshot_sha256=report.snapshot_sha256)


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_explicit_reviewer_decision_and_append_only_history(reports, decision):
    db, new_user, client, user, base, evidence = reports
    report = completed(reports)
    path = base+f'/reports/{report.id}/reviews'
    assert client.post(path, json=review_body(report, decision), headers=csrf(client)).status_code == 403
    assert client.post(path, json=review_body(report), headers=csrf(client)).status_code == 201
    reviewer, lawyer = new_user('lawyer')
    db.add(CaseMember(case_id=evidence.case_id, user_id=lawyer.id)); db.commit()
    assert reviewer.post(path, json=review_body(report, decision)).status_code == 403
    body = review_body(report, decision)
    body['pdf_sha256'] = '0'*64
    assert reviewer.post(path, json=body, headers=csrf(reviewer)).status_code == 409
    approved = reviewer.post(path, json=review_body(report, decision), headers=csrf(reviewer))
    assert approved.status_code == 201, approved.text
    assert approved.json()['reviewer_id'] == str(lawyer.id)
    assert reviewer.post(path, json=review_body(report, decision), headers=csrf(reviewer)).status_code == 409
    meta = reviewer.get(base+f'/reports/{report.id}').json()
    assert meta['review_status'] == decision and meta['is_approved'] == (decision == 'approved')
    assert len(meta['reviews']) == 2 and meta['approval_embedded_in_pdf'] is False
    with pytest.raises(DBAPIError):
        with db.begin_nested():
            db.execute(text('UPDATE report_reviews SET note=:note WHERE id=:id'), dict(note='Forbidden note rewrite', id=UUID(approved.json()['id'])))


def test_unprivileged_owner_readonly_member_archival_and_cross_case(reports):
    db, new_user, client, _, base, evidence = reports
    report = completed(reports)
    reader, user = new_user()
    owned = create(reader)
    assert reader.post(f'/api/v1/cases/{owned["id"]}/report-jobs', json={}, headers=csrf(reader)).status_code == 403
    db.add(CaseMember(case_id=evidence.case_id, user_id=user.id)); db.commit()
    assert reader.get(base+f'/reports/{report.id}').status_code == 200
    assert reader.post(base+'/report-jobs', json={}, headers=csrf(reader)).status_code == 403
    assert reader.post(base+f'/reports/{report.id}/reviews', json=review_body(report), headers=csrf(reader)).status_code == 403
    other = create(client)
    assert client.get(f'/api/v1/cases/{other["id"]}/reports/{report.id}').status_code == 404
    from app.models import Case
    db.get(Case, evidence.case_id).status = 'archived'; db.commit()
    assert client.get(base+f'/reports/{report.id}/pdf').status_code == 200
    assert client.post(base+'/report-jobs', json={}, headers=csrf(client)).status_code == 409


def test_empty_authorized_case_omits_absent_sections(reports):
    _, _, client, _, _, _ = reports
    case = create(client)
    empty = (*reports[:4], f'/api/v1/cases/{case["id"]}', reports[5])
    report = completed(empty)
    text_pdf = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(client.get(empty[4]+f'/reports/{report.id}/pdf').content)).pages)
    for heading in ['Evidence Inventory', 'Document Analysis', 'Visual Evidence Analysis', 'Legal Research — actual', 'Human Review Findings']:
        assert heading not in text_pdf
    assert report.snapshot['evidence'] == [] and report.snapshot['documents'] == []
    assert report.snapshot['coverage']['evidence'] == 0


def test_revoked_requester_fenced_worker_and_retry_history(reports, monkeypatch):
    db, _, client, user, base, evidence = reports
    job_id = enqueue(reports)
    _, token, _ = analysis_worker.claim(db, db.bind, 'case_report')
    assert not report_jobs.run_analysis(job_id, uuid4())
    db.delete(db.scalar(select(CaseMember).where(CaseMember.case_id == evidence.case_id, CaseMember.user_id == user.id))); db.commit()
    assert not report_jobs.run_analysis(job_id, token)
    db.expire_all(); job = db.get(ProcessingJob, job_id)
    assert job.status == 'failed' and job.error_code == 'access_revoked'
    db.add(CaseMember(case_id=evidence.case_id, user_id=user.id)); db.commit()
    assert client.post(base+f'/report-jobs/{job_id}/retry', headers=csrf(client)).status_code == 202
    assert execute(reports, job_id)[0]
    assert db.get(ProcessingJob, job_id).attempts == 2


def test_failed_render_recovery_retains_failed_version(reports, monkeypatch):
    db, _, _, _, _, _ = reports
    real = report_jobs.render
    def fail(*args):
        raise RuntimeError('Controlled local renderer failure; not evidence')
    monkeypatch.setattr(report_jobs, 'render', fail)
    job_id = enqueue(reports)
    assert not execute(reports, job_id)[0]
    job = db.get(ProcessingJob, job_id)
    assert job.status == 'queued' and job.error_code == 'processing_failed'
    failed = db.scalar(select(ReportVersion).where(ReportVersion.job_id == job_id))
    assert failed.status == 'failed' and failed.pdf_key is None
    job.next_attempt_at = now()-timedelta(seconds=1); db.commit()
    monkeypatch.setattr(report_jobs, 'render', real)
    assert execute(reports, job_id)[0]
    rows = list(db.scalars(select(ReportVersion).where(ReportVersion.job_id == job_id).order_by(ReportVersion.version)))
    assert [r.status for r in rows] == ['failed', 'completed']
    assert [r.attempt for r in rows] == [1, 2]


def test_source_and_download_integrity_fail_closed(reports, monkeypatch):
    db, _, client, _, base, _ = reports
    original = report_sources.PrivateStorage
    class BrokenStore:
        def read_verified(self, *args):
            raise StorageError('Controlled integrity failure')
    monkeypatch.setattr(report_sources, 'PrivateStorage', lambda _: BrokenStore())
    job_id = enqueue(reports)
    assert not execute(reports, job_id)[0]
    assert db.get(ProcessingJob, job_id).error_code == 'integrity_failed'
    monkeypatch.setattr(report_sources, 'PrivateStorage', original)
    report = completed(reports)
    pdf = PrivateStorage(report_jobs.get_settings().private_root).path(report.pdf_key)
    pdf.chmod(0o600); pdf.write_bytes(b'Controlled corrupt derived PDF')
    assert client.get(base+f'/reports/{report.id}/pdf').status_code == 409
    assert client.post(base+f'/reports/{report.id}/reviews', json=review_body(report), headers=csrf(client)).status_code == 409


def test_audit_provenance_pagination_and_untrusted_pdf_text(reports):
    db, _, client, _, base, evidence = reports
    from app.models import Case
    case = db.get(Case, evidence.case_id)
    # User-created metadata, explicitly not a legal/evidence fixture or source claim.
    case.description = '<img src="http://127.0.0.1/private"/> & <b>User-entered literal text</b>'
    db.commit()
    report = completed(reports)
    assert client.get(base+'/reports?limit=1&offset=0').json()['total'] >= 1
    body = client.get(base+f'/reports/{report.id}/provenance').json()
    assert body['snapshot']['case']['description'] == case.description
    audit = client.get(base+f'/reports/{report.id}/audit').json()['items']
    assert any(row['action'] == 'report.completed' for row in audit)
    assert any(row['action'] == 'report.provenance_read' for row in audit)
    assert all(row['details'].get('report_id') == str(report.id) or row['details'].get('job_id') == str(report.job_id) for row in audit)
    text_pdf = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(client.get(base+f'/reports/{report.id}/pdf').content)).pages)
    assert 'http://127.0.0.1/private' in text_pdf and '<b>User-entered literal text</b>' in text_pdf


def test_stale_worker_cannot_publish_and_restart_claim_retains_history(reports, monkeypatch):
    db = reports[0]
    original = report_jobs.render
    def fenced(snapshot, digest):
        output = original(snapshot, digest)
        job = db.get(ProcessingJob, job_id)
        job.lease_token = uuid4()
        job.lease_expires_at = now()-timedelta(seconds=1)
        db.commit()
        return output
    job_id = enqueue(reports)
    monkeypatch.setattr(report_jobs, 'render', fenced)
    assert not execute(reports, job_id)[0]
    first = db.scalar(select(ReportVersion).where(ReportVersion.job_id == job_id))
    assert first.status == 'processing' and first.pdf_key is None
    monkeypatch.setattr(report_jobs, 'render', original)
    assert execute(reports, job_id)[0]
    db.refresh(first)
    assert first.status == 'interrupted'
    assert db.get(ProcessingJob, job_id).attempts == 2
    assert db.scalar(select(func.count()).select_from(ReportVersion).where(ReportVersion.job_id == job_id)) == 2


@pytest.mark.parametrize('kind', ['page', 'citation'])
def test_saved_source_tampering_blocks_publication(reports, kind):
    db = reports[0]
    if kind == 'page':
        from app.models import AnalysisPage, EvidenceAnalysis
        page = db.scalar(select(AnalysisPage).join(EvidenceAnalysis).join(Evidence, Evidence.id == EvidenceAnalysis.evidence_id).where(Evidence.case_id == reports[5].case_id, EvidenceAnalysis.status == 'completed').order_by(EvidenceAnalysis.created_at.desc(), EvidenceAnalysis.id, AnalysisPage.page_number).limit(1))
        page.text += '\nControlled negative integrity fixture; not an authentic source.'
        page.text_sha256 = hashlib.sha256(page.text.encode()).hexdigest()
    else:
        source = db.scalar(select(ResearchResult))
        source.citation = {**source.citation, 'title': 'Controlled negative citation-integrity fixture'}
    db.commit()
    job_id = enqueue(reports)
    assert not execute(reports, job_id)[0]
    job = db.get(ProcessingJob, job_id)
    assert job.status == 'failed' and job.error_code == 'integrity_failed'
    report = db.scalar(select(ReportVersion).where(ReportVersion.job_id == job_id))
    assert report.pdf_key is None and report.snapshot_key is None


def test_snapshot_download_tampering_and_retry_cap(reports):
    db, _, client, _, base, _ = reports
    report = completed(reports)
    path = PrivateStorage(report_jobs.get_settings().private_root).path(report.snapshot_key)
    path.chmod(0o600); path.write_text('{}')
    assert client.get(base+f'/reports/{report.id}/snapshot').status_code == 409
    assert client.get(base+f'/reports/{report.id}/provenance').status_code == 409
    assert client.get(base+f'/reports/{report.id}/pdf').status_code == 409
    job_id = enqueue(reports, new_version=True)
    job = db.get(ProcessingJob, job_id)
    job.status, job.attempts = 'failed', job.max_attempts
    db.commit()
    assert client.post(base+f'/report-jobs/{job_id}/retry', headers=csrf(client)).status_code == 409
    assert client.post(base+'/report-jobs', json={'llm_enabled': True}, headers=csrf(client)).status_code == 422
