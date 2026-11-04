# Detecting uncertain command deliveries

`CommandQueue.recover_unacknowledged(agent_id, now=..., min_age_seconds=60)` lists command IDs whose delivery was claimed by the cloud but not acknowledged after the specified interval. The query is scoped to one agent and is **read-only**. It does not change command state, automatically resend commands, or interact with MetaTrader.

A lost GET response cannot be distinguished from a delivered command whose ACK was lost. Blindly putting such commands back into the pending queue is unsafe once broker execution exists. Operators must first inspect the agent's durable command journal and broker order history, then reconcile the outcome. A future protocol may support authenticated agent journal status reports and bounded recovery leases.

The development queue and command processor remain non-trading. No production reconciliation or order execution is implemented.
