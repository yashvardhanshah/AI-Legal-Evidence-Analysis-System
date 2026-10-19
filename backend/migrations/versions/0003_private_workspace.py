"""Add authentication and ownership without dropping or replacing existing data."""
from alembic import op
import sqlalchemy as sa

revision = "0003_private_workspace"
down_revision = "0002_legal_data"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('administrator', 'investigator', 'lawyer', 'legal_researcher')", name="ck_user_role"))
    op.create_table("auth_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    # Nullable only to retain any legacy Phase 2 rows without inventing owners.
    op.add_column("cases", sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_cases_owner", ondelete="RESTRICT")))
    op.create_index("ix_cases_owner_id", "cases", ["owner_id"])
    op.add_column("cases", sa.Column("opened_on", sa.Date()))
    op.add_column("cases", sa.Column("incident_on", sa.Date()))
    op.add_column("cases", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("evidence", sa.Column("uploader_id", sa.Uuid(), sa.ForeignKey("users.id", name="fk_evidence_uploader", ondelete="RESTRICT")))
    op.create_index("ix_evidence_uploader_id", "evidence", ["uploader_id"])
    op.add_column("evidence", sa.Column("captured_on", sa.Date()))
    op.create_table("case_members",
        sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.execute("INSERT INTO system_metadata (key, value) VALUES ('private_workspace_schema', '3')")


def downgrade():
    raise RuntimeError("Destructive downgrade disabled; use an approved data-preserving migration.")
