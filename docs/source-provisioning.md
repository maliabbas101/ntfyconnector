# Development source provisioning

Run this CLI on a trusted administrator machine with database access. Do not expose it as a public endpoint.

1. Set `DATABASE_URL` to the correct database connection.
2. For a new **development-only** SQLite database, run:
   `python -m app.provision_source --tenant-id <tenant-uuid> --init-dev-schema`
3. For an already initialized database, omit `--init-dev-schema`.
4. Capture the one-time `SOURCE_ID` and `SOURCE_TOKEN` values in a secret manager. Configure the ntfy bridge using those values.

A random 48-byte token is generated for each source; only its SHA-256 digest is persisted. The tenant UUID is an administrative input, not proof of authorization. This CLI assumes its operator is trusted.

**Production warning:** The schema does not yet have tenant membership checks, row-level security, migrations, or auditable provisioning. Do not use this CLI to onboard untrusted customers or live trading accounts.
