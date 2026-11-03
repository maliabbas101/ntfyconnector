# Local development command queue

The SQLite `CommandQueue` stores signed command envelopes for a specific agent. A transaction atomically claims a pending command, expires stale pending commands, and prevents delivery to a different agent. It rejects reuse of a command UUID with different content or agent identity.

**Important delivery limitation:** the queue marks a command DELIVERED before the agent acknowledges it. If the network response is lost, it does not automatically redeliver; this favors avoiding duplicate execution over guaranteed delivery. Recovery must reconcile with the agent journal and broker before any retry. An acknowledgment currently means only that the queue's delivery was acknowledged, not that a trade succeeded.

This is a local development primitive, not an exposed cloud endpoint. No enrollment, tenant authorization, per-agent credential verification, multi-worker PostgreSQL queue, or broker execution is implemented. Do not expose this queue without authenticated agent identity and tenant checks.
