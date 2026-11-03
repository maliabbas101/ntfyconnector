"""HMAC authentication for cloud-to-agent command envelopes.

This verifies authenticity and expiry, not permission to execute orders.
"""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class AuthenticationError(ValueError):
    pass

class SignedEnvelope(BaseModel):
    command_id: str
    expires_at: datetime
    payload: dict[str, Any]
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_fields(self):
        self.command_id = str(UUID(self.command_id))
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Timezone-aware expiry required")
        return self

def canonical_message(command_id: str, expires_at: datetime, payload: dict) -> bytes:
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        raise ValueError("Timezone-aware expiry required")
    data = {
        "command_id": str(UUID(command_id)),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        "payload": payload,
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")

def sign_command(secret: bytes, command_id: str, expires_at: datetime,
                 payload: dict) -> str:
    if len(secret) < 32:
        raise ValueError("At least 32 bytes of secret key material required")
    message = canonical_message(command_id, expires_at, payload)
    return hmac.new(secret, message, hashlib.sha256).hexdigest()

def verify_envelope(envelope: SignedEnvelope, secret: bytes, *,
                    now: datetime | None = None) -> dict:
    if len(secret) < 32:
        raise AuthenticationError("Invalid signing key")
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Timezone-aware current time required")
    if envelope.expires_at <= current:
        raise AuthenticationError("Expired command")
    expected = sign_command(secret, envelope.command_id,
                            envelope.expires_at, envelope.payload)
    if not hmac.compare_digest(expected, envelope.signature):
        raise AuthenticationError("Invalid command signature")
    return envelope.payload
