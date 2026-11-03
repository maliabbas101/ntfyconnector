# Authenticated command envelopes

`app.agent_auth` provides deterministic HMAC-SHA256 signatures for command UUID, UTC-normalized expiry, and JSON payload. Verification uses constant-time signature comparison and rejects expired commands and short keys. Tests cover tampering, incorrect keys, and expiry.

This is a **cryptographic primitive**, not a complete secure command transport. A production agent needs per-agent enrollment and secret provisioning/rotation, TLS with server authentication, bounded clock skew, tenant/account binding, maximum command age, payload schema validation, replay/idempotency enforcement using the durable journal, and safe failure on compromised keys. The cloud service must never accept a user-supplied signature key. Neither this module nor the existing command processor executes trades. Live trading remains disabled.
