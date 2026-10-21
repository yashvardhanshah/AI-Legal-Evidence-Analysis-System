"""Add source-versioned statutes and private research; never rewrite prior data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision='0006_legal_research'
down_revision='0005_visual_analysis'
branch_labels=None
depends_on=None

def identity(): return sa.Column('id',sa.Uuid(),primary_key=True)
def fk(name,target,nullable=False): return sa.Column(name,sa.Uuid(),sa.ForeignKey(target,ondelete='RESTRICT'),nullable=nullable)
def col(name,kind,nullable=False): return sa.Column(name,kind,nullable=nullable)
def timestamps(): return [
    sa.Column(n,sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False) for n in ['created_at','updated_at']]

def upgrade():
    op.create_table('statute_versions',identity(),fk('source_id','dataset_sources.id'),col('act_identifier',sa.String(255)),
        col('version',sa.String(255)),col('source_url',sa.Text()),col('storage_key',sa.Text()),col('sha256',sa.String(64)),
        col('publication_on',sa.Date()),col('consolidated_on',sa.Date()),col('metadata_record',JSONB()),*timestamps(),
        sa.UniqueConstraint('source_id','act_identifier','version',name='uq_statute_version'))
    op.create_table('provision_passages',identity(),fk('version_id','statute_versions.id'),fk('provision_id','legal_provisions.id'),
        col('ordinal',sa.Integer()),col('page_number',sa.Integer()),col('char_start',sa.Integer()),col('char_end',sa.Integer()),
        col('text',sa.Text()),col('sha256',sa.String(64)),col('vector_id',sa.String(100),True),col('embedding_revision',sa.String(100),True),
        sa.UniqueConstraint('vector_id'),sa.UniqueConstraint('provision_id','ordinal',name='uq_provision_passage'),
        sa.CheckConstraint('page_number > 0 AND char_start >= 0 AND char_end > char_start',name='ck_statute_span'))
    op.create_table('research_runs',identity(),fk('case_id','cases.id'),fk('job_id','processing_jobs.id'),
        col('attempt',sa.Integer()),col('status',sa.String(20)),col('outcome',sa.String(50),True),col('provenance',JSONB()),
        col('limitations',JSONB()),col('error_code',sa.String(100),True),col('finished_at',sa.DateTime(timezone=True),True),*timestamps(),
        sa.UniqueConstraint('job_id','attempt',name='uq_research_attempt'),
        sa.CheckConstraint("status IN ('processing','completed','failed','interrupted')",name='ck_research_status'))
    op.create_table('research_inputs',identity(),fk('run_id','research_runs.id'),fk('evidence_id','evidence.id',True),
        fk('page_id','analysis_pages.id',True),col('text',sa.Text()),col('sha256',sa.String(64)),col('query',sa.Text()),col('provenance',JSONB()))
    op.create_table('research_results',identity(),fk('run_id','research_runs.id'),fk('input_id','research_inputs.id'),
        fk('judgment_passage_id','judgment_passages.id',True),fk('provision_passage_id','provision_passages.id',True),
        col('rank',sa.Integer()),col('distance',sa.Float()),col('citation',JSONB()),
        sa.CheckConstraint('(judgment_passage_id IS NOT NULL) != (provision_passage_id IS NOT NULL)',name='ck_research_source'))
    op.create_table('research_reviews',identity(),fk('result_id','research_results.id'),fk('reviewer_id','users.id'),
        col('disposition',sa.String(30)),col('note',sa.Text()),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("disposition IN ('relevant','not_relevant','needs_verification')",name='ck_research_review'))
    for table,names in [('research_runs',['case_id','job_id']),('research_inputs',['run_id']),('research_results',['run_id']),('research_reviews',['result_id'])]:
        for name in names: op.create_index('ix_'+table+'_'+name,table,[name])
    op.execute("INSERT INTO system_metadata (key,value) VALUES ('legal_research_schema','6')")

def downgrade():
    raise RuntimeError('Destructive downgrade disabled; use an approved forward migration.')
