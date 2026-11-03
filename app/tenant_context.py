"""Tenant-scoped database operations for PostgreSQL.

Only call after verifying tenant identity using trusted authentication.
The database connection must use a non-superuser, non-BYPASSRLS role.
"""
from uuid import UUID
from sqlalchemy import text

def set_tenant(session, tenant_id: str) -> None:
    validated = str(UUID(tenant_id))
    if session.bind.dialect.name != "postgresql":
        raise RuntimeError("Tenant isolation requires PostgreSQL")
    # set_config(..., true) is transaction-local; never use a session-level setting.
    session.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"),
                    {"tenant": validated})
