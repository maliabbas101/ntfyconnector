# Agent outbound transport scaffold

`poll_once` makes one outbound HTTPS request to a configured agent command endpoint. It requires a bearer token, refuses HTTP and credential-bearing URLs, refuses redirects, and accepts only a signed command envelope or HTTP 204 (no command). Signature verification and the fail-closed command processor run before any terminal interaction. It never sends broker orders.

**Not yet a working cloud channel:** the server endpoint, enrollment/token issuance, per-agent identity binding, acknowledgment delivery, TLS pinning policy, polling loop, operational telemetry, and recovery strategy are not implemented. Use an HTTPS endpoint with trusted certificate validation and avoid logging credentials. Do not enable real trading.
