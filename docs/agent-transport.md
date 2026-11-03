# Agent outbound HTTPS polling

`poll_once` fetches a signed command over HTTPS and validates its signature and expiry before touching MT5 or the local journal. A command that reaches a durable terminal journal state (`REJECTED` or `RECONCILED`) is acknowledged to the cloud via POST `/v1/agent/commands/{command_id}/ack`. Invalid signatures are not acknowledged. Missing acknowledgments raise errors; the command journal prevents accidental duplicate execution.

An acknowledgment confirms only local processing, **not a successful broker trade**. The command processor still rejects every command before order submission. Commands in uncertain states are not acknowledged automatically.

This is still a single-agent development scaffold. It requires proper enrollment, per-agent identity, tenant isolation, TLS deployment, credential rotation, recovery/reconciliation, and real Windows demo-terminal integration tests before use in a production service.
