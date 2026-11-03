# Opt-in development agent polling API

The FastAPI router exposes GET `/v1/agent/commands/next` and POST `/v1/agent/commands/{command_id}/ack`. It is disabled unless all three environment variables are present: `DEMO_AGENT_ID`, `DEMO_AGENT_TOKEN_SHA256` (SHA-256 hex digest of a strong randomly generated bearer token), and `DEMO_COMMAND_QUEUE_PATH`. A configured agent sees only its own queue. Missing/invalid credentials are rejected.

This is **single-agent development configuration**, not customer enrollment or multi-tenant authentication. Never expose this endpoint publicly without TLS, rate limiting, secure secret distribution/rotation, agent-to-tenant binding, operational monitoring, and a production database. The acknowledgment is a delivery receipt, not evidence of trade execution. No command-creation API or broker order execution is provided.
