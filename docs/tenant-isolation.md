# PostgreSQL tenant isolation

Migration `0002` enforces tenant/source integrity with a composite foreign key
and enables **FORCE row-level security** on `sources` and `raw_events`.

## RLS-compatible ingestion path

Use:

```
POST /v1/ingest/tenants/{tenant_uuid}/sources/{source_id}
Authorization: Bearer <source-secret>
Content-Type: application/json

{"external_id":"ntfy-message-id","text":"BUY XAUUSD CMP 4042.8\\nSL: 4037\\nTP-1: 4056\\nTP-2: 4082"}
```

The route validates the tenant UUID, sets the PostgreSQL transaction-local
`app.tenant_id` context, and only then reads the source row under RLS.
**The caller-supplied tenant ID is a lookup scope, not authentication.**
Access is granted only when the source ID belongs to that scoped tenant and
the SHA-256 digest of the supplied secret matches the stored source token hash.
Other-tenant requests fail without exposing source records.

After an insert conflict, the handler rolls back and re-establishes the
transaction-local tenant context before querying for an existing duplicate.

The old `/v1/ingest/sources/{source_id}` route remains available for local
SQLite testing only and returns HTTP 503 on PostgreSQL. Configure
`SOURCE_TENANT_ID` on the ntfy bridge to use the new tenant-scoped URL.

## Production prerequisites

- Run database migrations using a separate migration account.
- Run API requests under a role that **does not own the tables**, is not a
  superuser, and lacks `BYPASSRLS`.
- Never accept a tenant ID as authorization on its own.
- Keep source tokens high-entropy, rotate them safely, add rate limiting and
  abuse monitoring, and restrict database privileges.
- Validate this flow against a **real PostgreSQL instance** with FORCE RLS.
  Current automated tests exercise tenant checks on SQLite but **do not prove
  PostgreSQL RLS behavior**.
- A user-facing multi-tenant auth system and source provisioning UI remain
  outstanding.

The `set_tenant(session, tenant_id)` helper uses transaction-local
`set_config(..., true)`. Other tenant-scoped database operations must follow
equivalent authentication and transaction rules.
