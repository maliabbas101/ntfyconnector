# Agent acknowledgment recovery

The development queue treats POST acknowledgment as idempotent for the **same authenticated agent and already-acknowledged command**. A client that loses the first successful HTTP response can retry the ACK without modifying state or producing a 404. Commands in PENDING or EXPIRED states and commands owned by another agent cannot be acknowledged.

This only fixes **lost ACK responses**. It does not recover a command marked DELIVERED when its initial GET response never reaches the agent. That requires a bounded lease/reconciliation protocol and must never blindly resubmit broker orders. No broker execution is enabled.
