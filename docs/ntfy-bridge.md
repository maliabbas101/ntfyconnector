# ntfy subscriber bridge (development)

The bridge listens to a configured ntfy topic and forwards messages to the existing authenticated source-ingestion endpoint. The bridge does not trade, calculate position size, or communicate with MT5.

Install dependencies: `pip install -e .`. First create the database schema and provision a source using the development instructions in `docs/ingestion.md`.

Configure environment variables on the machine running the bridge:

```sh
export NTFY_TOPIC="your-private-topic"
export NTFY_URL="https://ntfy.sh"
export SOURCE_ID="source-id-provisioned-in-db"
export SOURCE_TOKEN="secret-provisioned-for-source"
export API_URL="https://your-api.example.com"
python -m app.ntfy_bridge
```

The bridge uses the ntfy JSON streaming endpoint. Messages are forwarded with their ntfy event IDs as deduplication keys. Connection failures cause a retry. The ingestion service validates the source token and persists events.

## Important limitations

- The bridge currently uses a live stream without replay-on-reconnect. Notifications during outages can be missed. Do not rely on it for production trading.
- The ntfy topic URL must be kept private. Public topics may be writable by others; an authenticated source token alone does not authenticate the signal publisher.
- A production bridge needs durable cursor/replay, topic access control, TLS verification, backpressure, explicit error handling for permanent API failures, and monitored delivery.
- No MT5 execution is implemented.
