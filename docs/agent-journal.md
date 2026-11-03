# MT5 agent journal foundation

The local SQLite command journal is a foundation for the customer-hosted Windows agent. Each command has a UUID and canonical JSON payload. Repeated delivery with the same UUID and payload returns the existing state; changing the payload raises an error.

The journal records `EXECUTION_UNKNOWN` **before** any future broker submission. If a process crashes, the command must be reconciled against broker orders/deals before any further action. Commands in `REJECTED`, `EXECUTION_UNKNOWN`, or `RECONCILED` are never automatically resubmitted by this component.

This is a storage primitive only. There is no MT5 connection, command signature verification, account binding, risk reevaluation, broker reconciliation implementation, or order submission yet. Never connect this module directly to live trading.
