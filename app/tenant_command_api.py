"""Opt-in development command submission; no broker execution.

Not a production tenant authorization service. The caller's tenant is
pinned by server-side configuration, never trusted from request JSON.
"""
import hashlib
import hmac
import os
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.command_queue import CommandQueue, QueueConflict

router = APIRouter(prefix="/v1/dev/tenants", tags=["dev-command-submission"])


def authenticate_tenant(authorization: str | None) -> str:
    tenant = os.getenv("DEMO_COMMAND_TENANT_ID", "")
    token_hash = os.getenv("DEMO_COMMAND_SUBMIT_TOKEN_SHA256", "")
    if not tenant or len(token_hash) != 64:
        raise HTTPException(status_code=503, detail="Command submission disabled")
    try:
        tenant = str(UUID(tenant))
        bytes.fromhex(token_hash)
    except ValueError:
        raise HTTPException(status_code=503, detail="Command submission misconfigured") from None
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid submission credentials")
    token = authorization[7:]
    if not token or not hmac.compare_digest(
        hashlib.sha256(token.encode("utf-8")).hexdigest(), token_hash.lower()
    ):
        raise HTTPException(status_code=401, detail="Invalid submission credentials")
    return tenant


def signing_secret() -> bytes:
    secret_hex = os.getenv("DEMO_COMMAND_SIGNING_KEY_HEX", "")
    try:
        secret = bytes.fromhex(secret_hex)
    except ValueError:
        secret = b""
    if len(secret) < 32:
        raise HTTPException(status_code=503, detail="Signing key not configured")
    return secret


class SubmitCommand(BaseModel):
    agent_id: str
    envelope: dict = Field(min_length=4)


@router.post("/commands", status_code=status.HTTP_202_ACCEPTED)
def submit_command(body: SubmitCommand,
                   authorization: str | None = Header(default=None)):
    tenant_id = authenticate_tenant(authorization)
    secret = signing_secret()
    path = os.getenv("DEMO_COMMAND_QUEUE_PATH")
    if not path:
        raise HTTPException(status_code=503, detail="Command queue not configured")
    try:
        with CommandQueue(path) as queue:
            queue.enqueue_bound(body.agent_id, tenant_id, body.envelope, secret)
    except (QueueConflict, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=409, detail="Command rejected") from exc
    return {"status": "QUEUED", "execution_enabled": False}
