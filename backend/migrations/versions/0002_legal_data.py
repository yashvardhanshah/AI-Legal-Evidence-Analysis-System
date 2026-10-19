"""Add Phase 2 data infrastructure, preserving all Phase 1 tables and rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_legal_data"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def identity():
    return sa.Column("id", sa.Uuid(), primary_key=True)


def fk(name, target, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def upgrade():
    op.create_table("dataset_sources", identity(),
        sa.Column("slug", sa.String(100), nullable=False, unique=True), sa.Column("name", sa.String(255), nullable=False),
        sa.Column("publisher", sa.String(255), nullable=False), sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("upstream_url", sa.Text()), sa.Column("license_id", sa.String(100)), sa.Column("license_url", sa.Text()),
        sa.Column("attribution", sa.Text()), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)), sa.Column("notes", sa.Text()), *timestamps(),
        sa.CheckConstraint("status IN ('verified', 'pending', 'blocked')", name="ck_source_status"))
    op.create_table("judgments", identity(), fk("source_id", "dataset_sources.id"),
        sa.Column("external_id", sa.String(255), nullable=False), sa.Column("title", sa.Text()), sa.Column("court", sa.String(255)),
        sa.Column("judgment_date", sa.Date()), sa.Column("citation", sa.Text()), sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("metadata_url", sa.Text(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("storage_key", sa.Text(), nullable=False), sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False), sa.Column("extraction_method", sa.String(100), nullable=False),
        sa.Column("pipeline_version", sa.String(100), nullable=False), sa.Column("provenance", postgresql.JSONB(), nullable=False), *timestamps(),
        sa.UniqueConstraint("source_id", "external_id", name="uq_judgment_source_external"),
        sa.CheckConstraint("byte_size > 0 AND page_count > 0", name="ck_judgment_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_judgment_hash"))
    op.create_index("ix_judgments_source_id", "judgments", ["source_id"])
    op.create_index("ix_judgments_court_date", "judgments", ["court", "judgment_date"])
    op.create_table("judgment_passages", identity(), fk("judgment_id", "judgments.id"),
        sa.Column("ordinal", sa.Integer(), nullable=False), sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False), sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False), sa.Column("vector_id", sa.String(100), unique=True),
        sa.Column("embedding_revision", sa.String(100)), sa.Column("indexed_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.UniqueConstraint("judgment_id", "ordinal", name="uq_passage_ordinal"),
        sa.CheckConstraint("page_number > 0 AND char_start >= 0 AND char_end > char_start AND token_count > 0", name="ck_passage_offsets"))
    op.create_index("ix_judgment_passages_judgment_id", "judgment_passages", ["judgment_id"])
    op.create_table("legal_provisions", identity(), fk("source_id", "dataset_sources.id"),
        sa.Column("act_identifier", sa.String(255), nullable=False), sa.Column("act_title", sa.Text(), nullable=False),
        sa.Column("version", sa.String(255), nullable=False), sa.Column("provision_identifier", sa.String(100), nullable=False),
        sa.Column("heading", sa.Text()), sa.Column("text", sa.Text(), nullable=False), sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_document_sha256", sa.String(64), nullable=False), sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("effective_from", sa.Date()), sa.Column("effective_to", sa.Date()),
        sa.Column("sha256", sa.String(64), nullable=False), *timestamps(),
        sa.UniqueConstraint("source_id", "act_identifier", "version", "provision_identifier", name="uq_provision_version"),
        sa.CheckConstraint("length(sha256) = 64 AND page_number > 0", name="ck_provision_source"))
    op.create_index("ix_legal_provisions_source_id", "legal_provisions", ["source_id"])
    op.create_index("ix_provision_act_version", "legal_provisions", ["act_identifier", "version"])
    op.create_table("cases", identity(), sa.Column("reference", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False), sa.Column("description", sa.Text()), sa.Column("jurisdiction", sa.String(255)),
        sa.Column("status", sa.String(20), nullable=False), *timestamps(),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_case_status"))
    op.create_index("ix_cases_status", "cases", ["status"])
    op.create_table("evidence", identity(), fk("case_id", "cases.id"),
        sa.Column("original_filename", sa.String(255), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False), sa.Column("provenance", sa.Text(), nullable=False), *timestamps(),
        sa.UniqueConstraint("case_id", "sha256", name="uq_evidence_case_hash"),
        sa.CheckConstraint("byte_size > 0 AND length(sha256) = 64", name="ck_evidence_size_hash"))
    op.create_index("ix_evidence_case_id", "evidence", ["case_id"])
    op.create_index("ix_evidence_sha256", "evidence", ["sha256"])
    op.create_table("evidence_artifacts", identity(), fk("evidence_id", "evidence.id"),
        sa.Column("kind", sa.String(100), nullable=False), sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("producer_version", sa.String(255), nullable=False), *timestamps(),
        sa.UniqueConstraint("evidence_id", "kind", "sha256", name="uq_artifact_content"),
        sa.CheckConstraint("byte_size > 0 AND length(sha256) = 64", name="ck_artifact_size_hash"))
    op.create_index("ix_evidence_artifacts_evidence_id", "evidence_artifacts", ["evidence_id"])
    op.create_table("processing_jobs", identity(), fk("source_id", "dataset_sources.id", True), fk("judgment_id", "judgments.id", True),
        sa.Column("kind", sa.String(100), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False), sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False), sa.Column("error_code", sa.String(100)),
        sa.Column("details", postgresql.JSONB(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.CheckConstraint("status IN ('queued', 'processing', 'completed', 'failed')", name="ck_job_status"),
        sa.CheckConstraint("attempts >= 0 AND processed >= 0 AND total >= processed", name="ck_job_progress"))
    op.create_index("ix_processing_jobs_source_id", "processing_jobs", ["source_id"])
    op.create_index("ix_processing_jobs_judgment_id", "processing_jobs", ["judgment_id"])
    op.create_index("ix_jobs_status_created", "processing_jobs", ["status", "created_at"])
    op.create_table("audit_logs", identity(), sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False), sa.Column("resource_id", sa.Uuid()),
        sa.Column("actor", sa.String(255), nullable=False), sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    for field in ["action", "resource_id", "created_at"]:
        op.create_index("ix_audit_logs_" + field, "audit_logs", [field])
    # Keep the original Phase 1 installation marker; this migration adds a separate marker.
    op.execute("INSERT INTO system_metadata (key, value) VALUES ('legal_data_schema', '2')")


def downgrade():
    raise RuntimeError("Destructive Phase 2 downgrade is disabled. Use a reviewed, explicit data-preserving migration.")
