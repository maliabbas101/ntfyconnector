"""Enforce source/event tenant consistency and PostgreSQL row policies.

Revision ID: 0002_tenants
Revises: 0001_ingestion
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_tenants"
down_revision = "0001_ingestion"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # Existing rows must be consistent before applying a composite foreign key.
    mismatch = bind.execute(sa.text(
        "SELECT 1 FROM raw_events e JOIN sources s ON e.source_id = s.id "
        "WHERE e.tenant_id <> s.tenant_id LIMIT 1"
    )).first()
    if mismatch:
        raise RuntimeError("Tenant mismatch in existing events; repair before migration")
    op.create_unique_constraint("uq_sources_tenant_id_id", "sources", ["tenant_id", "id"])
    op.drop_constraint("raw_events_source_id_fkey", "raw_events", type_="foreignkey")
    op.create_foreign_key("fk_events_tenant_source", "raw_events", "sources",
                          ["tenant_id", "source_id"], ["tenant_id", "id"])
    for table in ("sources", "raw_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_scope ON {table} "
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), ''))"
        )

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in ("raw_events", "sources"):
        op.execute(f"DROP POLICY tenant_scope ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint("fk_events_tenant_source", "raw_events", type_="foreignkey")
    op.create_foreign_key("raw_events_source_id_fkey", "raw_events", "sources",
                          ["source_id"], ["id"])
    op.drop_constraint("uq_sources_tenant_id_id", "sources", type_="unique")
