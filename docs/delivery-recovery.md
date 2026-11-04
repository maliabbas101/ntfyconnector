# Detecting uncertain command deliveries

`CommandQueue.recover_unacknowledged(agent_id, now=..., min_age_seconds=60)` lists command IDs whose delivery was claimed by the cloud but not acknowledged after the specified interval. The query is scoped to one agent and is **read-only**. It does not change command state, automatically resend commands, or interact with MetaTrader.

A lost GET response cannot be distinguished from a delivered command whose ACK was lost. Blindly putting such commands back into the pending queue is unsafe once broker execution exists. Operators must first inspect the agent's durable command journal and broker order history, then reconcile the outcome. A future protocol may support authenticated agent journal status reports and bounded recovery leases.

The development queue and command processor remain non-trading. No production reconciliation or order execution is implemented.

## Read-only delivery receipt

An authenticated development agent can call `GET /v1/agent/commands/{command_id}/receipt` to inspect its own queue status (`PENDING`, `DELIVERED`, `ACKNOWLEDGED`, or `EXPIRED`) and the last reported journal state, if any. A command owned by another agent returns 404. The endpoint does not return payloads, requeue, or mutate delivery state. A `DELIVERED` command with no terminal report still requires local journal/broker reconciliation; never assume it is safe to resend. The receipt is an authenticated agent report, not broker evidence.
