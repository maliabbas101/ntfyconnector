"""Outbound-only HTTPS polling transport for a future Windows demo agent.

No MT5 orders are placed. Caller owns enrollment and secret provisioning.
"""
from urllib.parse import urlsplit
import httpx
from app.agent_auth import SignedEnvelope
from app.agent_identity import AgentIdentity, verify_bound_command
from app.agent_processor import process_demo_command

class TransportConfigurationError(ValueError):
    pass

def validate_agent_endpoint(url: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise TransportConfigurationError("Invalid agent endpoint URL") from exc
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment or parts.query
            or port not in (None, 443)):
        raise TransportConfigurationError("Agent endpoint must be a plain HTTPS URL on port 443")
    return url.rstrip("/")

def poll_once(*, endpoint: str, agent_token: str, signing_secret: bytes,
              journal, mt5, client: httpx.Client,
              identity: AgentIdentity | None = None) -> dict:
    """Fetch one signed command; no auto-retry and no broker execution.

    Token must be provisioned out of band; never log token or signed payload.
    """
    base = validate_agent_endpoint(endpoint)
    if not agent_token or not agent_token.strip():
        raise TransportConfigurationError("Agent token required")
    if identity is None:
        raise TransportConfigurationError("Pinned agent identity required before polling")
    if len(signing_secret) < 32:
        raise TransportConfigurationError("Command signing key must contain at least 32 bytes")
    response = client.get(
        base + "/v1/agent/commands/next",
        headers={"Authorization": "Bearer " + agent_token, "Accept": "application/json"},
        timeout=15.0,
        follow_redirects=False,
    )
    if response.status_code == 204:
        return {"status": "EMPTY", "execution_enabled": False}
    response.raise_for_status()
    if response.status_code != 200:
        raise RuntimeError("Unexpected command response")
    envelope = SignedEnvelope.model_validate(response.json())
    command = verify_bound_command(envelope, signing_secret, identity)
    result = process_demo_command(command, journal, mt5)
    # Report the durable journal outcome before acknowledging delivery.
    report = client.post(
        base + "/v1/agent/commands/" + envelope.command_id + "/journal-state",
        headers={"Authorization": "Bearer " + agent_token},
        json={"state": result["state"]},
        timeout=15.0,
        follow_redirects=False,
    )
    report.raise_for_status()
    if report.status_code != 200 or report.json().get("status") != "RECORDED":
        raise RuntimeError("Invalid journal status report response")
    # Acknowledge only after a durable, terminal journal state. This is a
    # delivery receipt, never a claim that a broker order was placed.
    if result["state"] not in ("REJECTED", "RECONCILED"):
        return {"status": "UNACKNOWLEDGED", "result": result,
                "execution_enabled": False}
    ack = client.post(
        base + "/v1/agent/commands/" + envelope.command_id + "/ack",
        headers={"Authorization": "Bearer " + agent_token},
        timeout=15.0,
        follow_redirects=False,
    )
    ack.raise_for_status()
    if ack.status_code != 200 or ack.json().get("status") != "ACKNOWLEDGED":
        raise RuntimeError("Invalid agent acknowledgment response")
    return {"status": "ACKNOWLEDGED", "result": result, "execution_enabled": False}
