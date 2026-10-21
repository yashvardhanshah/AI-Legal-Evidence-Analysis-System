"""Bounded, source-verified private report snapshots; no inferred findings or LLM."""
import hashlib
import json
import math
from uuid import UUID
from sqlalchemy import select
from app import models as m, research_jobs
from app.config import get_settings
from app.storage import PrivateStorage, StorageError

PIPELINE = 'case-report-v1'
LIMITATIONS = [
    'Verified statutory analysis is unavailable: zero BNS, BNSS, BSA and legacy provisions were imported in Phase 6. No statutory recommendations are made.',
    'This report does not establish guilt, intent, legal liability or admissibility. Human approval is an attributed review decision, not legal certification.',
    'OCR text and NLP entities are unverified automated observations; check exact original pages. Phase 4 found 1 of 6 checked person mentions, not general model accuracy.',
    'Object detections are unverified model outputs, not facial identification or proof of criminal activity. Sampled video frames are not continuous tracking.',
    'Retrieved judgments are historical English source passages, not an exhaustive or current-law applicability assessment. Similarity is not legal correctness; repeated passages are not independent corroboration.',
    'Deterministic summaries only count and attribute retained source records. No external AI service or LLM is used.',
    'This immutable review-copy PDF does not embed later approval. Verify the external report metadata and matching PDF/snapshot hashes; unapproved copies are not finalized investigations.',
    'Exact Unicode source text is preserved in the downloadable snapshot. PDF glyphs unsupported by the bundled font are printed as [U+XXXX]; complex-script shaping is not supported.',
]


class ReportFailure(ValueError):
    def __init__(self, code, retryable=False):
        self.code, self.retryable = code, retryable


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str).encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fields(row, names):
    return json.loads(canonical({name: getattr(row, name) for name in names.split()}).decode())


def bounded(db, statement, limit):
    rows = list(db.scalars(statement.limit(limit+1)))
    if len(rows) > limit:
        raise ReportFailure('report_limit_exceeded')
    return rows


def snapshot(db, case, report_id, version, title, requested_by, captured_at):
    store = PrivateStorage(get_settings().private_root)
    artifacts, model_ids, verified = {}, set(), []

    def artifact(identifier, evidence_id):
        item = db.get(m.EvidenceArtifact, identifier)
        if not item or item.evidence_id != evidence_id:
            raise ReportFailure('integrity_failed')
        content = store.read_verified(item.storage_key, item.sha256)
        artifacts[str(item.id)] = fields(item, 'id evidence_id kind sha256 byte_size producer_version')
        if len(content) != item.byte_size:
            raise ReportFailure('integrity_failed')
        return content

    evidence = bounded(db, select(m.Evidence).where(m.Evidence.case_id == case.id).order_by(m.Evidence.created_at, m.Evidence.id), 100)
    inventory, documents, visuals = [], [], []
    for item in evidence:
        raw = store.read_verified(item.storage_key, item.sha256)
        if len(raw) != item.byte_size:
            raise ReportFailure('integrity_failed')
        verified.append(dict(kind='original', id=str(item.id), sha256=item.sha256))
        inventory.append(fields(item, 'id original_filename mime_type byte_size sha256 provenance uploader_id captured_on created_at'))
        analysis = db.scalar(select(m.EvidenceAnalysis).where(m.EvidenceAnalysis.evidence_id == item.id, m.EvidenceAnalysis.status == 'completed').order_by(m.EvidenceAnalysis.created_at.desc(), m.EvidenceAnalysis.id).limit(1))
        if analysis:
            if analysis.original_sha256 != item.sha256 or not analysis.artifact_id:
                raise ReportFailure('integrity_failed')
            retained = json.loads(artifact(analysis.artifact_id, item.id))
            if retained.get('analysis_id') != str(analysis.id) or retained.get('original_sha256') != item.sha256:
                raise ReportFailure('integrity_failed')
            pages = bounded(db, select(m.AnalysisPage).where(m.AnalysisPage.analysis_id == analysis.id).order_by(m.AnalysisPage.page_number), 200)
            original_pages = {p['page_number']: p for p in retained['pages']}
            if len(pages) != len(original_pages):
                raise ReportFailure('integrity_failed')
            doc = fields(analysis, 'id evidence_id original_sha256 pipeline_version ner_model_id ocr_model_id artifact_id settings warnings created_at finished_at')
            doc['classification'], doc['pages'] = 'unverified_automated_document_observations', []
            model_ids.update(x for x in [analysis.ner_model_id, analysis.ocr_model_id] if x)
            for page in pages:
                source = original_pages.get(page.page_number)
                if not source or sha(page.text.encode()) != page.text_sha256:
                    raise ReportFailure('integrity_failed')
                for name in 'text text_sha256 extraction_method ocr_confidence width height ocr_words warnings'.split():
                    if source.get(name) != getattr(page, name):
                        raise ReportFailure('integrity_failed')
                record = fields(page, 'id page_number extraction_method text text_sha256 ocr_confidence width height warnings')
                entities = bounded(db, select(m.AnalysisEntity).where(m.AnalysisEntity.page_id == page.id).order_by(m.AnalysisEntity.char_start, m.AnalysisEntity.id), 10000)
                record['entities'] = []
                for entity in entities:
                    if not 0 <= entity.char_start < entity.char_end <= len(page.text) or entity.text != page.text[entity.char_start:entity.char_end]:
                        raise ReportFailure('integrity_failed')
                    names = 'label text char_start char_end extractor score provenance'
                    data = fields(entity, names)
                    if data not in [{k: v.get(k) for k in names.split()} for v in source['entities']]:
                        raise ReportFailure('integrity_failed')
                    if entity.model_id:
                        model_ids.add(entity.model_id)
                    record['entities'].append({**data, 'id': str(entity.id), 'model_id': str(entity.model_id) if entity.model_id else None})
                if len(entities) != len(source['entities']):
                    raise ReportFailure('integrity_failed')
                doc['pages'].append(record)
            documents.append(doc)
        visual = db.scalar(select(m.VisualAnalysis).where(m.VisualAnalysis.evidence_id == item.id, m.VisualAnalysis.status == 'completed').order_by(m.VisualAnalysis.created_at.desc(), m.VisualAnalysis.id).limit(1))
        if visual:
            if visual.original_sha256 != item.sha256:
                raise ReportFailure('integrity_failed')
            model_ids.add(visual.model_id)
            record = fields(visual, 'id evidence_id original_sha256 model_id pipeline_version settings media created_at finished_at')
            record['classification'], record['frames'] = 'unverified_sampled_frame_object_detections', []
            frames = bounded(db, select(m.VisualFrame).where(m.VisualFrame.analysis_id == visual.id).order_by(m.VisualFrame.frame_index), 300)
            for frame in frames:
                import cv2
                import numpy as np
                pixels = cv2.imdecode(np.frombuffer(artifact(frame.source_artifact_id, item.id), dtype=np.uint8), cv2.IMREAD_COLOR)
                if pixels is None or pixels.shape[:2] != (frame.height, frame.width) or sha(pixels.tobytes()) != frame.pixel_sha256 or not math.isfinite(frame.timestamp_ms):
                    raise ReportFailure('integrity_failed')
                artifact(frame.annotated_artifact_id, item.id)
                current = fields(frame, 'id frame_index timestamp_ms width height pixel_sha256 source_artifact_id annotated_artifact_id inference_ms')
                detections = bounded(db, select(m.VisualDetection).where(m.VisualDetection.frame_id == frame.id).order_by(m.VisualDetection.id), 20000)
                current['detections'] = []
                for detection in detections:
                    values = [detection.confidence, detection.x1, detection.y1, detection.x2, detection.y2]
                    if not all(math.isfinite(x) for x in values) or not (0 <= detection.confidence <= 1 and 0 <= detection.x1 < detection.x2 <= frame.width and 0 <= detection.y1 < detection.y2 <= frame.height):
                        raise ReportFailure('integrity_failed')
                    current['detections'].append(fields(detection, 'id class_id label confidence x1 y1 x2 y2 provenance'))
                record['frames'].append(current)
            visuals.append(record)
    research, human, source_ids = [], [], set()
    runs = bounded(db, select(m.ResearchRun).where(m.ResearchRun.case_id == case.id, m.ResearchRun.status == 'completed').order_by(m.ResearchRun.created_at, m.ResearchRun.id), 100)
    for run in runs:
        inputs = bounded(db, select(m.ResearchInput).where(m.ResearchInput.run_id == run.id).order_by(m.ResearchInput.id), 16)
        for entry in inputs:
            start, end = entry.provenance.get('query_char_start'), entry.provenance.get('query_char_end')
            if sha(entry.text.encode()) != entry.sha256 or not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(entry.text) or entry.text[start:end] != entry.query:
                raise ReportFailure('integrity_failed')
            if entry.evidence_id and entry.evidence_id not in {x.id for x in evidence}:
                raise ReportFailure('integrity_failed')
        record = fields(run, 'id outcome provenance limitations created_at finished_at')
        registry = run.provenance.get('model_registry_id')
        if registry:
            model_ids.add(UUID(registry))
        record['inputs'] = [fields(i, 'id evidence_id page_id text sha256 query provenance') for i in inputs]
        record['results'] = []
        results = bounded(db, select(m.ResearchResult).where(m.ResearchResult.run_id == run.id).order_by(m.ResearchResult.rank), 100)
        for result in results:
            # Phase 7 deliberately includes only actual verified judgment records.
            if not result.judgment_passage_id or result.citation.get('kind') != 'judgment' or result.input_id not in {x.id for x in inputs}:
                raise ReportFailure('integrity_failed')
            try:
                research_jobs.validate_citation(db, result.citation, True)
            except research_jobs.ResearchFailure as exc:
                raise ReportFailure('integrity_failed') from exc
            if str(result.judgment_passage_id) != result.citation['passage_id']:
                raise ReportFailure('integrity_failed')
            source_ids.add(UUID(result.citation['source_id']))
            record['results'].append(fields(result, 'id input_id rank distance citation'))
            for review in bounded(db, select(m.ResearchReview).where(m.ResearchReview.result_id == result.id).order_by(m.ResearchReview.created_at), 100):
                reviewer = db.get(m.User, review.reviewer_id)
                human.append({**fields(review, 'id result_id reviewer_id disposition note created_at'), 'reviewer_name': reviewer.display_name,
                    'classification': 'attributed_human_relevance_annotation'})
        research.append(record)
    participant_ids = {case.owner_id} | set(db.scalars(select(m.CaseMember.user_id).where(m.CaseMember.case_id == case.id)))
    participants = [fields(u, 'id display_name role is_active') for u in db.scalars(select(m.User).where(m.User.id.in_([x for x in participant_ids if x])).order_by(m.User.id))]
    registry = []
    for identifier in sorted(x for x in model_ids if x):
        model = db.get(m.AnalysisModel, identifier)
        if not model:
            raise ReportFailure('integrity_failed')
        registry.append(fields(model, 'id name revision task license_id source_url byte_size file_hashes software'))
    body = dict(schema=PIPELINE, report_id=str(report_id), version=version, title=title, captured_at=str(captured_at), requested_by=str(requested_by),
        case=fields(case, 'id reference title description jurisdiction status owner_id opened_on incident_on created_at updated_at archived_at'),
        participants=participants, evidence=inventory, documents=documents, visuals=visuals, research=research, human_reviews=human,
        artifacts=list(artifacts.values()), models=registry, verified_sources=verified, limitations=LIMITATIONS,
        dataset_sources=[fields(s, 'id slug name publisher source_url upstream_url license_id license_url attribution status verified_at')
            for s in db.scalars(select(m.DatasetSource).where(m.DatasetSource.id.in_(source_ids)).order_by(m.DatasetSource.id))],
        selection_policy='All case evidence; latest completed document and visual analysis per evidence; all completed case research runs and existing relevance annotations at snapshot time. Failed/pending analyses omitted, with coverage counts below.',
        coverage=dict(evidence=len(evidence), document_analyses=len(documents), visual_analyses=len(visuals), research_runs=len(research), human_reviews=len(human)),
        statutory_analysis='unavailable', imported_statutory_provisions=0, llm_enabled=False)
    if len(canonical(body)) > 20_000_000:
        raise ReportFailure('report_limit_exceeded')
    return body


def verify_snapshot(report):
    raw = canonical(report.snapshot)
    if sha(raw) != report.snapshot_sha256 or report.snapshot.get('report_id') != str(report.id) or report.snapshot.get('case', {}).get('id') != str(report.case_id):
        raise ReportFailure('integrity_failed')
    store = PrivateStorage(get_settings().private_root)
    if store.read_verified(report.snapshot_key, report.snapshot_sha256) != raw:
        raise ReportFailure('integrity_failed')
    return raw
