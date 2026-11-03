# Authenticated ingestion (development)

The `POST /v1/ingest/sources/{source_id}` endpoint accepts a source-scoped bearer token and an `external_id` plus notification `text`. It persists each event before acknowledging it and rejects unauthorized callers. Duplicate IDs per source return the existing event ID.

## Local setup

Set `DATABASE_URL` to a PostgreSQL SQLAlchemy URL (for example `postgresql+psycopg://...`) or use the default local SQLite file for development. Initialize tables explicitly:

```python
from app.ingestion import Base, engine
Base.metadata.create_all(engine)
```

Provision source IDs, tenant IDs, and cryptographically random bearer tokens using a protected administrative process. Insert only SHA-256 token digests via `token_digest` into `sources`; never store raw tokens. No source provisioning API exists yet.

## Limitations

This is a development foundation, not production-ready: no Alembic migrations, PostgreSQL RLS, admin authorization, rate limiting, retention policies, source attestation, or full audit log. The ingestion endpoint is not a direct ntfy subscription. It can receive forwarded ntfy notification content when a trusted companion client is implemented.

No MT5 orders can be placed.
