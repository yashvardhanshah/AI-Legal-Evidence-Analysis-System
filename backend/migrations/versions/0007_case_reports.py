"""Add immutable private report versions and append-only human review decisions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0007_case_reports'
down_revision = '0006_legal_research'
branch_labels = None
depends_on = None


def upgrade():
    def fk(name, target):
        return sa.Column(name, sa.Uuid(), sa.ForeignKey(target, ondelete='RESTRICT'), nullable=False)
    def col(name, kind, nullable=False):
        return sa.Column(name, kind, nullable=nullable)
    op.create_table('report_versions', sa.Column('id', sa.Uuid(), primary_key=True),
        fk('case_id', 'cases.id'), fk('job_id', 'processing_jobs.id'), fk('requested_by', 'users.id'),
        col('version', sa.Integer()), col('attempt', sa.Integer()), col('status', sa.String(20)),
        col('title', sa.String(300)), col('pipeline_version', sa.String(100)), col('snapshot', JSONB()),
        col('snapshot_sha256', sa.String(64), True), col('snapshot_key', sa.Text(), True),
        col('pdf_sha256', sa.String(64), True), col('pdf_key', sa.Text(), True),
        col('byte_size', sa.BigInteger(), True), col('page_count', sa.Integer(), True),
        col('error_code', sa.String(100), True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        col('finished_at', sa.DateTime(timezone=True), True),
        sa.UniqueConstraint('job_id', 'attempt', name='uq_report_attempt'),
        sa.UniqueConstraint('case_id', 'version', name='uq_report_case_version'),
        sa.CheckConstraint("status IN ('processing','completed','failed','interrupted')", name='ck_report_status'),
        sa.CheckConstraint('version > 0 AND attempt > 0', name='ck_report_version'),
        sa.CheckConstraint("status != 'completed' OR (pdf_sha256 IS NOT NULL AND snapshot_sha256 IS NOT NULL AND page_count IS NOT NULL AND byte_size IS NOT NULL AND length(pdf_sha256)=64 AND length(snapshot_sha256)=64 AND page_count>0 AND byte_size>0 AND pdf_key IS NOT NULL AND snapshot_key IS NOT NULL AND finished_at IS NOT NULL)", name='ck_report_completed'))
    op.create_table('report_reviews', sa.Column('id', sa.Uuid(), primary_key=True),
        fk('report_id', 'report_versions.id'), fk('reviewer_id', 'users.id'),
        col('reviewer_name', sa.String(100)), col('reviewer_role', sa.String(30)),
        col('disposition', sa.String(20)), col('note', sa.Text()),
        col('pdf_sha256', sa.String(64)), col('snapshot_sha256', sa.String(64)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("disposition IN ('note','approved','rejected')", name='ck_report_review'))
    for table, names in [('report_versions', ['case_id', 'job_id']), ('report_reviews', ['report_id'])]:
        for name in names:
            op.create_index('ix_'+table+'_'+name, table, [name])
    op.create_index('uq_report_decision', 'report_reviews', ['report_id'], unique=True,
        postgresql_where=sa.text("disposition IN ('approved','rejected')"))
    # Database guards also prevent accidental ORM/operator edits to published versions.
    op.execute("""CREATE FUNCTION protect_case_reports() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME = 'report_reviews' OR TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Report versions and review history are immutable';
      END IF;
      IF OLD.status = 'completed' THEN
        RAISE EXCEPTION 'Report versions and review history are immutable';
      END IF;
      RETURN NEW;
    END $$""")
    for table in ['report_versions', 'report_reviews']:
        op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_case_reports()')
    op.execute("INSERT INTO system_metadata (key,value) VALUES ('case_reports_schema','7')")


def downgrade():
    raise RuntimeError('Destructive downgrade disabled; use an approved forward migration.')
