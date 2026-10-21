from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SystemMetadata(Base):
    """Non-sensitive installation metadata; domain schema belongs to Phase 2."""

    __tablename__ = "system_metadata"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DatasetSource(Timestamped, Base):
    __tablename__ = "dataset_sources"
    __table_args__ = (CheckConstraint("status IN ('verified', 'pending', 'blocked')", name="ck_source_status"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text)
    upstream_url: Mapped[str | None] = mapped_column(Text)
    license_id: Mapped[str | None] = mapped_column(String(100))
    license_url: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Judgment(Timestamped, Base):
    __tablename__ = "judgments"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_judgment_source_external"),
        CheckConstraint("byte_size > 0 AND page_count > 0", name="ck_judgment_size"),
        CheckConstraint("length(sha256) = 64", name="ck_judgment_hash"),
        Index("ix_judgments_court_date", "court", "judgment_date"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_sources.id", ondelete="RESTRICT"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    court: Mapped[str | None] = mapped_column(String(255))
    judgment_date: Mapped[date | None] = mapped_column(Date)
    citation: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    metadata_url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_key: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    page_count: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(100))
    pipeline_version: Mapped[str] = mapped_column(String(100))
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)


class JudgmentPassage(Timestamped, Base):
    __tablename__ = "judgment_passages"
    __table_args__ = (
        UniqueConstraint("judgment_id", "ordinal", name="uq_passage_ordinal"),
        CheckConstraint("page_number > 0 AND char_start >= 0 AND char_end > char_start AND token_count > 0", name="ck_passage_offsets"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    judgment_id: Mapped[UUID] = mapped_column(ForeignKey("judgments.id", ondelete="RESTRICT"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    vector_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    embedding_revision: Mapped[str | None] = mapped_column(String(100))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LegalProvision(Timestamped, Base):
    __tablename__ = "legal_provisions"
    __table_args__ = (
        UniqueConstraint("source_id", "act_identifier", "version", "provision_identifier", name="uq_provision_version"),
        CheckConstraint("length(sha256) = 64 AND page_number > 0", name="ck_provision_source"),
        Index("ix_provision_act_version", "act_identifier", "version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("dataset_sources.id", ondelete="RESTRICT"), index=True)
    act_identifier: Mapped[str] = mapped_column(String(255))
    act_title: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(255))
    provision_identifier: Mapped[str] = mapped_column(String(100))
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    source_document_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int] = mapped_column(Integer)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    sha256: Mapped[str] = mapped_column(String(64))


class Case(Timestamped, Base):
    """Private workspace; legacy unowned rows are inaccessible except to admins."""
    __tablename__ = "cases"
    __table_args__ = (CheckConstraint("status IN ('active', 'archived')", name="ck_case_status"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    opened_on: Mapped[date | None] = mapped_column(Date)
    incident_on: Mapped[date | None] = mapped_column(Date)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Evidence(Timestamped, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("case_id", "sha256", name="uq_evidence_case_hash"),
        CheckConstraint("byte_size > 0 AND length(sha256) = 64", name="ck_evidence_size_hash"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text)
    uploader_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    captured_on: Mapped[date | None] = mapped_column(Date)


class EvidenceArtifact(Timestamped, Base):
    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        UniqueConstraint("evidence_id", "kind", "sha256", name="uq_artifact_content"),
        CheckConstraint("byte_size > 0 AND length(sha256) = 64", name="ck_artifact_size_hash"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    storage_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(BigInteger)
    producer_version: Mapped[str] = mapped_column(String(255))


class ProcessingJob(Timestamped, Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="ck_job_status"),
        CheckConstraint("attempts >= 0 AND processed >= 0 AND total >= processed", name="ck_job_progress"),
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("uq_active_evidence_analysis", "evidence_id", unique=True, postgresql_where=text("kind = 'evidence_analysis' AND status IN ('queued', 'processing')")),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("dataset_sources.id", ondelete="RESTRICT"), index=True)
    judgment_id: Mapped[UUID | None] = mapped_column(ForeignKey("judgments.id", ondelete="RESTRICT"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    processed: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_id: Mapped[UUID | None] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"), index=True)
    requested_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, server_default="3")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    actor: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class User(Timestamped, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('administrator', 'investigator', 'lawyer', 'legal_researcher')", name="ck_user_role"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(30), default="legal_researcher")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CaseMember(Base):
    __tablename__ = "case_members"
    case_id: Mapped[UUID] = mapped_column(ForeignKey("cases.id", ondelete="RESTRICT"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisModel(Timestamped, Base):
    __tablename__ = "analysis_models"
    __table_args__ = (UniqueConstraint("name", "revision", name="uq_analysis_model_revision"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255))
    revision: Mapped[str] = mapped_column(String(128))
    task: Mapped[str] = mapped_column(String(50))
    license_id: Mapped[str] = mapped_column(String(100))
    source_url: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    file_hashes: Mapped[dict] = mapped_column(JSONB)
    software: Mapped[dict] = mapped_column(JSONB)


class EvidenceAnalysis(Timestamped, Base):
    __tablename__ = "evidence_analyses"
    __table_args__ = (UniqueConstraint("job_id", "attempt", name="uq_analysis_job_attempt"),
                     CheckConstraint("status IN ('processing', 'completed', 'failed', 'interrupted')", name="ck_analysis_status"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("processing_jobs.id", ondelete="RESTRICT"), index=True)
    evidence_id: Mapped[UUID] = mapped_column(ForeignKey("evidence.id", ondelete="RESTRICT"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    original_sha256: Mapped[str] = mapped_column(String(64))
    pipeline_version: Mapped[str] = mapped_column(String(100))
    ner_model_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysis_models.id", ondelete="RESTRICT"))
    ocr_model_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysis_models.id", ondelete="RESTRICT"))
    artifact_id: Mapped[UUID | None] = mapped_column(ForeignKey("evidence_artifacts.id", ondelete="RESTRICT"))
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(100))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisPage(Base):
    __tablename__ = "analysis_pages"
    __table_args__ = (UniqueConstraint("analysis_id", "page_number", name="uq_analysis_page"),
                     CheckConstraint("page_number > 0 AND (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 100))", name="ck_analysis_page_confidence"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("evidence_analyses.id", ondelete="RESTRICT"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(50))
    text: Mapped[str] = mapped_column(Text)
    text_sha256: Mapped[str] = mapped_column(String(64))
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    ocr_words: Mapped[list] = mapped_column(JSONB, default=list)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)


class AnalysisEntity(Base):
    __tablename__ = "analysis_entities"
    __table_args__ = (UniqueConstraint("page_id", "label", "char_start", "char_end", "extractor", name="uq_analysis_entity_span"),
                     CheckConstraint("char_start >= 0 AND char_end > char_start AND (score IS NULL OR (score >= 0 AND score <= 1))", name="ck_entity_span_score"),
                     CheckConstraint("label IN ('PERSON', 'ORGANIZATION', 'LOCATION', 'DATE', 'TIME', 'DOCUMENT_REFERENCE')", name="ck_entity_label"))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    page_id: Mapped[UUID] = mapped_column(ForeignKey("analysis_pages.id", ondelete="RESTRICT"), index=True)
    model_id: Mapped[UUID | None] = mapped_column(ForeignKey("analysis_models.id", ondelete="RESTRICT"))
    label: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    extractor: Mapped[str] = mapped_column(String(30))
    score: Mapped[float | None] = mapped_column(Float)
    provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
