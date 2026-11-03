# PostgreSQL tenant isolation

Migration 0002 adds a composite tenant/source foreign key, enables and forces row-level security on sources and raw_events, and defines tenant-scoped read/write policies.

**Important:** The ingestion API currently authenticates a source token using a global lookup, so it is **not yet wired to a complete PostgreSQL RLS-safe service-role architecture**. In particular, enabling RLS without a trusted source-token lookup role and tenant-scoped transaction handling will make ingestion fail closed. Do not deploy this migration to a production environment until the authentication and database roles are configured and verified.

The `set_tenant(session, tenant_id)` helper sets transaction-local `app.tenant_id` after an authenticated tenant identity is established. Tenant IDs must never be accepted from untrusted request payloads.

Database roles must not have `BYPASSRLS`, and the runtime must not use a PostgreSQL superuser. Schema owners and migration roles must be separated from runtime roles.

SQLite development mode does not enforce these policies. No live trading.
