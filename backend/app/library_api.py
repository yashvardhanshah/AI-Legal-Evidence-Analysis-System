"""Read-only public legal corpus endpoints; private cases/evidence have no routes."""
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import DatasetSource, Judgment, JudgmentPassage, LegalProvision, ProcessingJob

router = APIRouter(prefix="/api/v1", tags=["Public legal library"])
logger = logging.getLogger(__name__)


def session_dependency():
    with Session(get_engine()) as session:
        yield session


def judgment_fields(row):
    return {"id": row.id, "source_id": row.source_id, "external_id": row.external_id, "title": row.title, "court": row.court,
            "judgment_date": row.judgment_date, "citation": row.citation, "source_url": row.source_url, "metadata_url": row.metadata_url,
            "sha256": row.sha256, "page_count": row.page_count, "extraction_method": row.extraction_method, "pipeline_version": row.pipeline_version}


@router.get("/dataset-sources")
def sources(session: Session = Depends(session_dependency)):
    output = []
    for row in session.scalars(select(DatasetSource).order_by(DatasetSource.slug)):
        count = session.scalar(select(func.count()).select_from(Judgment).where(Judgment.source_id == row.id))
        indexed = session.scalar(select(func.count()).select_from(JudgmentPassage).join(Judgment).where(Judgment.source_id == row.id, JudgmentPassage.indexed_at.is_not(None)))
        output.append({"id": row.id, "slug": row.slug, "name": row.name, "publisher": row.publisher, "source_url": row.source_url,
                       "upstream_url": row.upstream_url, "license_id": row.license_id, "license_url": row.license_url, "attribution": row.attribution,
                       "status": row.status, "verified_at": row.verified_at, "notes": row.notes, "judgments": count, "indexed_passages": indexed})
    return {"items": output}


PUBLIC_JOBS = {"judgment_ingestion", "embedding_index"}


def job_fields(row):
    return {"id": row.id, "source_id": row.source_id, "kind": row.kind, "status": row.status, "attempts": row.attempts,
            "processed": row.processed, "total": row.total, "error_code": row.error_code, "started_at": row.started_at,
            "finished_at": row.finished_at, "created_at": row.created_at}


@router.get("/ingestion-jobs")
def jobs(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(session_dependency)):
    rows = session.scalars(select(ProcessingJob).where(ProcessingJob.kind.in_(PUBLIC_JOBS)).order_by(ProcessingJob.created_at.desc()).offset(offset).limit(limit))
    return {"items": [job_fields(row) for row in rows], "limit": limit, "offset": offset}


@router.get("/ingestion-jobs/{job_id}")
def job_detail(job_id: UUID, session: Session = Depends(session_dependency)):
    row = session.get(ProcessingJob, job_id)
    if not row or row.kind not in PUBLIC_JOBS:
        raise HTTPException(404, "Public corpus job not found")
    return job_fields(row)


@router.get("/judgments")
def judgments(q: str | None = Query(None, max_length=200), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(session_dependency)):
    query = select(Judgment)
    if q:
        query = query.where(Judgment.title.icontains(q, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Judgment.external_id, Judgment.id).offset(offset).limit(limit))
    return {"items": [judgment_fields(row) for row in rows], "total": total, "limit": limit, "offset": offset}


@router.get("/judgments/{judgment_id}")
def judgment_detail(judgment_id: UUID, passage_limit: int = Query(20, ge=1, le=100), passage_offset: int = Query(0, ge=0), session: Session = Depends(session_dependency)):
    row = session.get(Judgment, judgment_id)
    if not row:
        raise HTTPException(404, "Judgment not found")
    source = session.get(DatasetSource, row.source_id)
    query = select(JudgmentPassage).where(JudgmentPassage.judgment_id == row.id)
    passages = session.scalars(query.order_by(JudgmentPassage.ordinal).offset(passage_offset).limit(passage_limit))
    return {**judgment_fields(row), "license_id": source.license_id, "attribution": source.attribution,
            "passage_count": session.scalar(select(func.count()).select_from(query.subquery())), "passage_offset": passage_offset,
            "passages": [{"id": p.id, "ordinal": p.ordinal, "page_number": p.page_number, "text": p.text, "text_sha256": p.text_sha256,
                          "char_start": p.char_start, "char_end": p.char_end, "token_count": p.token_count, "indexed": p.indexed_at is not None} for p in passages]}


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Query must contain at least three non-whitespace characters")
        return value.strip()


@router.post("/search/judgments")
def search(request: SearchRequest, session: Session = Depends(session_dependency)):
    from app.vectors import QueryTooLong, semantic_search
    try:
        results = semantic_search(session, request.query, request.limit)
    except QueryTooLong as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        logger.warning("Semantic search unavailable (%s)", type(exc).__name__)
        raise HTTPException(503, "Semantic index or pinned local model is unavailable; run the operator indexing commands") from exc
    return {"query": request.query, "metric": "cosine_distance", "lower_is_better": True, "retrieval_unit": "distinct judgment with its best matching retrieved passage", "items": results,
            "notice": "Semantic proximity is a retrieval signal, not a legal conclusion or measured relevance score."}


@router.get("/legal-provisions")
def provisions(q: str = Query(..., min_length=2, max_length=200), act: str | None = Query(None, max_length=255), version: str | None = Query(None, max_length=255), limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(session_dependency)):
    query = select(LegalProvision).where(LegalProvision.text.icontains(q, autoescape=True))
    if act:
        query = query.where(LegalProvision.act_identifier == act)
    if version:
        query = query.where(LegalProvision.version == version)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(LegalProvision.act_identifier, LegalProvision.version, LegalProvision.provision_identifier).offset(offset).limit(limit))
    return {"items": [{"id": row.id, "act_identifier": row.act_identifier, "act_title": row.act_title, "version": row.version,
                       "provision_identifier": row.provision_identifier, "heading": row.heading, "text": row.text, "source_url": row.source_url,
                       "source_document_sha256": row.source_document_sha256, "page_number": row.page_number,
                       "effective_from": row.effective_from, "effective_to": row.effective_to} for row in rows],
            "total": total, "limit": limit, "offset": offset, "search_method": "literal substring; exact act/version filters; no inferred statute crosswalk"}
