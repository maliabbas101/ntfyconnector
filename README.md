# ntfyconnector

Multi-tenant signal-to-MetaTrader 5 automation platform.

## Status
Early development. **Dry-run and demo-only design; live execution is not implemented.**

## Architecture
- FastAPI control plane for ingestion and signal parsing
- Versioned, broker-neutral signal contracts
- Customer-hosted MT5 execution agent (planned)
- Tenant isolation, durable events, and risk controls (planned)

See the `feature/mvp-foundation` branch for initial development.

## Safety
Never connect a live trading account to experimental builds. Notification payloads are untrusted and must not directly execute broker orders.
