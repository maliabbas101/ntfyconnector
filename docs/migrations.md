# Database migrations

For a new empty database, set DATABASE_URL and run `alembic upgrade head`.

Earlier development versions created tables directly using SQLAlchemy. **Do not** apply the initial migration to an existing database without first backing it up and verifying its schema. After verification, `alembic stamp 0001_ingestion` can record the existing revision.

This migration creates the current development ingestion schema. It does not add PostgreSQL row-level security or production tenant isolation. Do not use for live trading.
