# Authenticated journal-state reports

The development agent can POST \`/v1/agent/commands/{command_id}/journal-state\` with a JSON body such as \`{"state":"REJECTED"}\`. The endpoint uses the same configured agent bearer token as polling, verifies command ownership and prior delivery, and records a monotonic journal-state claim. Repeating the same report is idempotent; conflicting terminal-state changes are rejected.

These are **agent-reported claims**, not independently verified broker evidence. They do not change queue delivery state, authorize execution, or automatically requeue uncertain commands. The agent polling client does not yet submit these reports automatically. Production requires per-agent enrollment, tenant authorization, secure transport, and reconciliation against the broker.
