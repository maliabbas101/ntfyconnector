"""Initial ingestion schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_ingestion"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False))
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"])
    op.create_table("raw_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("text", sa.String(8192), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "external_id", name="uq_source_external_id"))
    op.create_index("ix_raw_events_tenant_id", "raw_events", ["tenant_id"])

def downgrade():
    op.drop_index("ix_raw_events_tenant_id", table_name="raw_events")
    op.drop_table("raw_events")
    op.drop_index("ix_sources_tenant_id", table_name="sources")
    op.drop_table("sources")
