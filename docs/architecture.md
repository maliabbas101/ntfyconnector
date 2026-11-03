# MVP Architecture

## Current implementation
- Stateless FastAPI endpoint for deterministic parsing and validation of a single XAUUSD alert format.
- No ntfy subscription, persistent database, tenant authentication, risk engine, agent, or MT5 connectivity yet.
- No broker order execution; every response is explicitly DRY_RUN.

## Planned boundaries
1. Ingestion: authenticated sources, immutable events, deduplication.
2. Parsing: versioned provider-specific parsers to normalized signals.
3. Tenant control plane: membership, source/account bindings, policies, audit logs.
4. Orchestration: expiring commands, idempotency, durable state transitions.
5. Windows agent: authenticated outbound connection, local journal, MT5 demo reconciliation.

## Non-negotiable safeguards
- Tenant ID derived from credentials, never accepted as authority from request payloads.
- Do not execute arbitrary instructions from notification text.
- Demo account binding, local kill switch, stop/volume/margin validation.
- Unknown broker outcome requires reconciliation before retry.
- Production ingestion must be authenticated and rate limited.
