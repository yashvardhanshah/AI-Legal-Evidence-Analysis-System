"""Add private visual analysis records without changing existing evidence or runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_visual_analysis"
down_revision = "0004_document_analysis"
branch_labels = None
depends_on = None


def fk(name, target, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target, ondelete="RESTRICT"), nullable=nullable)


def upgrade():
    op.create_index("uq_active_visual_analysis", "processing_jobs", ["evidence_id"], unique=True,
        postgresql_where=sa.text("kind = 'visual_analysis' AND status IN ('queued', 'processing')"))
    op.create_table("visual_analyses", sa.Column("id", sa.Uuid(), primary_key=True),
        fk("job_id", "processing_jobs.id"), fk("evidence_id", "evidence.id"), fk("model_id", "analysis_models.id", True),
        sa.Column("attempt", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
        sa.Column("original_sha256", sa.String(64), nullable=False), sa.Column("pipeline_version", sa.String(100), nullable=False),
        sa.Column("settings", JSONB(), nullable=False), sa.Column("media", JSONB(), nullable=False),
        sa.Column("error_code", sa.String(100)), sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("job_id", "attempt", name="uq_visual_attempt"),
        sa.CheckConstraint("status IN ('processing','completed','failed','interrupted')", name="ck_visual_status"))
    for name in ["job_id", "evidence_id"]:
        op.create_index("ix_visual_analyses_"+name, "visual_analyses", [name])
    op.create_table("visual_frames", sa.Column("id", sa.Uuid(), primary_key=True), fk("analysis_id", "visual_analyses.id"),
        sa.Column("frame_index", sa.Integer(), nullable=False), sa.Column("timestamp_ms", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False), sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("pixel_sha256", sa.String(64), nullable=False), fk("source_artifact_id", "evidence_artifacts.id"),
        fk("annotated_artifact_id", "evidence_artifacts.id"), sa.Column("inference_ms", sa.Float(), nullable=False),
        sa.UniqueConstraint("analysis_id", "frame_index", name="uq_visual_frame"),
        sa.CheckConstraint("frame_index >= 0 AND timestamp_ms >= 0 AND width > 0 AND height > 0 AND inference_ms >= 0", name="ck_visual_frame_bounds"))
    op.create_index("ix_visual_frames_analysis_id", "visual_frames", ["analysis_id"])
    op.create_table("visual_detections", sa.Column("id", sa.Uuid(), primary_key=True), fk("frame_id", "visual_frames.id"),
        sa.Column("class_id", sa.Integer(), nullable=False), sa.Column("label", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        *[sa.Column(name, sa.Float(), nullable=False) for name in ["x1", "y1", "x2", "y2"]],
        sa.Column("provenance", JSONB(), nullable=False),
        sa.CheckConstraint("class_id >= 0 AND class_id < 80 AND confidence >= 0 AND confidence <= 1 AND x1 >= 0 AND y1 >= 0 AND x2 > x1 AND y2 > y1", name="ck_visual_detection"))
    op.create_index("ix_visual_detections_frame_id", "visual_detections", ["frame_id"])
    op.execute("INSERT INTO system_metadata (key, value) VALUES ('visual_analysis_schema','5')")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use an approved forward migration.")
