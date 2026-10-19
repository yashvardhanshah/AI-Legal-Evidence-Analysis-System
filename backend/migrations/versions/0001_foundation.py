"""Phase 1 installation metadata; no case or evidence records are seeded."""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "system_metadata",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.bulk_insert(table, [{"key": "development_phase", "value": "1"}])


def downgrade():
    op.drop_table("system_metadata")
