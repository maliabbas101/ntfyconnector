"""Outbound-only HTTPS polling transport for a future Windows demo agent.

No MT5 orders are placed. Caller owns enrollment and secret provisioning.
"""
from urllib.parse import urlsplit
import httpx
from app.agent_auth import SignedEnvelope
from app.signed_agent_processor import process_signed_demo_command

class TransportConfigurationError(ValueError):
    pass

def validate_agent_endpoint(url: str) -> str:
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment or parts.query
            or parts.port not in (None, 443)):
        raise TransportConfigurationError("Agent endpoint must be a plain HTTPS URL on port 443")
    return url.rstrip("/")

def poll_once(*, endpoint: str, agent_token: str, signing_secret: bytes,
              journal, mt5, client: httpx.Client) -> dict:
    """Fetch one signed command; no auto-retry and no broker execution.

    Token must be provisioned out of band; never log token or signed payload.
    """
    base = validate_agent_endpoint(endpoint)
    if not agent_token or not agent_token.strip():
        raise TransportConfigurationError("Agent token required")
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
    result = process_signed_demo_command(envelope, signing_secret, journal, mt5)
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
