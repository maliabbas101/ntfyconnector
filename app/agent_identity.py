"""Local agent identity pinning; no broker credentials or order submission."""
from dataclasses import dataclass
from uuid import UUID
from app.agent_auth import SignedEnvelope, verify_envelope
from app.agent_processor import DemoCommand

class AgentIdentityError(ValueError):
    pass

@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    tenant_id: str
    expected_login: int
    expected_server: str

    def __post_init__(self):
        object.__setattr__(self, "agent_id", str(UUID(self.agent_id)))
        object.__setattr__(self, "tenant_id", str(UUID(self.tenant_id)))
        if self.expected_login <= 0 or not self.expected_server.strip():
            raise AgentIdentityError("Pinned demo account identity required")

def verify_bound_command(envelope: SignedEnvelope, secret: bytes,
                         identity: AgentIdentity) -> DemoCommand:
    """Validate signature and local pins before any journal or terminal access.

    Requires signed tenant_id and agent_id in the command payload.
    """
    payload = verify_envelope(envelope, secret)
    if payload.get("agent_id") != identity.agent_id:
        raise AgentIdentityError("Signed command targets another agent")
    if payload.get("tenant_id") != identity.tenant_id:
        raise AgentIdentityError("Signed command targets another tenant")
    command = DemoCommand.model_validate(payload)
    if command.command_id != envelope.command_id or command.expires_at != envelope.expires_at:
        raise AgentIdentityError("Signed command identity mismatch")
    if (command.expected_login != identity.expected_login or
            command.expected_server != identity.expected_server):
        raise AgentIdentityError("Signed command account differs from local pin")
    return command
