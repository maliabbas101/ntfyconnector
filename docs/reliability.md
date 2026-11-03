# Ingestion reliability

The ingestion API acknowledges a signal only after committing its raw event. Repeated source/event IDs return the original event ID. Concurrent duplicate inserts are recovered only when the database reports an integrity constraint violation; unexpected database exceptions are not silently treated as duplicates.

The ntfy bridge persists its last acknowledged notification ID. Temporary HTTP failures retry without advancing the cursor, while permanent authentication or validation errors stop the bridge.

**Remaining gaps:** The ntfy server's retention period can expire during an outage. There is no dead-letter queue, durable delivery metrics, automatic operator alerting, or PostgreSQL end-to-end integration test yet. The PostgreSQL RLS migration requires a properly designed source-authentication role and tenant transaction wiring before deployment. This system must not execute live trades.
