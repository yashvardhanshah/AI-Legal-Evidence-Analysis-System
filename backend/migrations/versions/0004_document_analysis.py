"""Add private document analyses and durable job leases, preserving all prior data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_document_analysis"
down_revision = "0003_private_workspace"
branch_labels = None
depends_on = None


def fk(name, target, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    for name, target in [("evidence_id", "evidence.id"), ("requested_by", "users.id")]:
        op.add_column("processing_jobs", fk(name, target, True))
        op.create_index("ix_processing_jobs_"+name, "processing_jobs", [name])
    op.add_column("processing_jobs", sa.Column("lease_token", sa.Uuid()))
    op.add_column("processing_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
    op.add_column("processing_jobs", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.add_column("processing_jobs", sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False))
    op.create_index("uq_active_evidence_analysis", "processing_jobs", ["evidence_id"], unique=True,
                    postgresql_where=sa.text("kind = 'evidence_analysis' AND status IN ('queued', 'processing')"))
    op.create_table("analysis_models", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("revision", sa.String(128), nullable=False),
        sa.Column("task", sa.String(50), nullable=False), sa.Column("license_id", sa.String(100), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False), sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("file_hashes", JSONB(), nullable=False), sa.Column("software", JSONB(), nullable=False), *timestamps(),
        sa.UniqueConstraint("name", "revision", name="uq_analysis_model_revision"))
    op.create_table("evidence_analyses", sa.Column("id", sa.Uuid(), primary_key=True),
        fk("job_id", "processing_jobs.id"), fk("evidence_id", "evidence.id"),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False), sa.Column("pipeline_version", sa.String(100), nullable=False),
        fk("ner_model_id", "analysis_models.id", True), fk("ocr_model_id", "analysis_models.id", True), fk("artifact_id", "evidence_artifacts.id", True),
        sa.Column("settings", JSONB(), nullable=False), sa.Column("warnings", JSONB(), nullable=False),
        sa.Column("error_code", sa.String(100)), sa.Column("finished_at", sa.DateTime(timezone=True)), *timestamps(),
        sa.UniqueConstraint("job_id", "attempt", name="uq_analysis_job_attempt"),
        sa.CheckConstraint("status IN ('processing', 'completed', 'failed', 'interrupted')", name="ck_analysis_status"))
    for field in ["job_id", "evidence_id"]:
        op.create_index("ix_evidence_analyses_"+field, "evidence_analyses", [field])
    op.create_table("analysis_pages", sa.Column("id", sa.Uuid(), primary_key=True), fk("analysis_id", "evidence_analyses.id"),
        sa.Column("page_number", sa.Integer(), nullable=False), sa.Column("extraction_method", sa.String(50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False), sa.Column("text_sha256", sa.String(64), nullable=False), sa.Column("ocr_confidence", sa.Float()),
        sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("ocr_words", JSONB(), nullable=False), sa.Column("warnings", JSONB(), nullable=False),
        sa.UniqueConstraint("analysis_id", "page_number", name="uq_analysis_page"),
        sa.CheckConstraint("page_number > 0 AND (ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 100))", name="ck_analysis_page_confidence"))
    op.create_index("ix_analysis_pages_analysis_id", "analysis_pages", ["analysis_id"])
    op.create_table("analysis_entities", sa.Column("id", sa.Uuid(), primary_key=True), fk("page_id", "analysis_pages.id"), fk("model_id", "analysis_models.id", True),
        sa.Column("label", sa.String(30), nullable=False), sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False), sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(30), nullable=False), sa.Column("score", sa.Float()), sa.Column("provenance", JSONB(), nullable=False),
        sa.UniqueConstraint("page_id", "label", "char_start", "char_end", "extractor", name="uq_analysis_entity_span"),
        sa.CheckConstraint("char_start >= 0 AND char_end > char_start AND (score IS NULL OR (score >= 0 AND score <= 1))", name="ck_entity_span_score"),
        sa.CheckConstraint("label IN ('PERSON', 'ORGANIZATION', 'LOCATION', 'DATE', 'TIME', 'DOCUMENT_REFERENCE')", name="ck_entity_label"))
    op.create_index("ix_analysis_entities_page_id", "analysis_entities", ["page_id"])
    op.execute("INSERT INTO system_metadata (key, value) VALUES ('document_analysis_schema', '4')")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use an approved forward migration.")
