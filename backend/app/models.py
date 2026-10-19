from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
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
    """Storage foundation only; no case routes until Phase 3 authorization."""
    __tablename__ = "cases"
    __table_args__ = (CheckConstraint("status IN ('active', 'archived')", name="ck_case_status"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)


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


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(100))
    resource_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    actor: Mapped[str] = mapped_column(String(255))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
