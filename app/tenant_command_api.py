"""Opt-in development command submission; no broker execution.

Not a production tenant authorization service. The caller's tenant is
pinned by server-side configuration, never trusted from request JSON.
"""
import hashlib
import hmac
import os
from contextlib import contextmanager
from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.command_queue import CommandQueue, QueueConflict
from app.agent_auth import sign_command
from app.parser import parse_signal
from app.risk import RiskPolicy

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


class SubmitSignal(BaseModel):
    agent_id: str
    text: str = Field(min_length=1, max_length=8192)


@router.post("/commands/from-signal", status_code=status.HTTP_202_ACCEPTED)
def submit_signal(body: SubmitSignal,
                  authorization: str | None = Header(default=None)):
    """Server-side signing: tenant clients never receive the signing secret.

    Requires explicit agent enrollment. Broker snapshot fields are inert
    placeholders; the Windows agent independently fetches authoritative
    market data and account state before any optional demo order attempt.
    """
    tenant_id = authenticate_tenant(authorization)
    secret = signing_secret()
    path = os.getenv("DEMO_COMMAND_QUEUE_PATH")
    if not path:
        raise HTTPException(status_code=503, detail="Command queue not configured")
    try:
        agent_id = str(UUID(body.agent_id))
        expected_login = int(os.environ["DEMO_COMMAND_AGENT_LOGIN"])
        expected_server = os.environ["DEMO_COMMAND_AGENT_SERVER"]
        if expected_login <= 0 or not expected_server.strip():
            raise ValueError("Account pin not configured")
        policy = RiskPolicy(
            max_risk_fraction=os.getenv("DEMO_COMMAND_MAX_RISK_FRACTION", "0.005"),
            max_volume=os.getenv("DEMO_COMMAND_MAX_VOLUME", "0.1"),
            max_spread=os.getenv("DEMO_COMMAND_MAX_SPREAD", "0.5"))
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=503, detail="Command safety policy not configured") from None
    try:
        signal = parse_signal(body.text)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid signal") from exc
    command_id = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "agent_id": agent_id, "tenant_id": tenant_id,
        "command_id": command_id, "expires_at": expires_at.isoformat(),
        "expected_login": expected_login, "expected_server": expected_server,
        "signal": signal.model_dump(mode="json"),
        "policy": policy.model_dump(mode="json"),
        # These values are NEVER used as broker evidence by the MT5 agent.
        "broker": {"is_demo": False, "trading_enabled": False,
                   "equity": "1", "volume_min": "1", "volume_max": "1",
                   "volume_step": "1", "spread": "0",
                   "loss_per_lot_at_stop": "1"},
    }
    envelope = {
        "command_id": command_id, "expires_at": expires_at.isoformat(),
        "payload": payload,
        "signature": sign_command(secret, command_id, expires_at, payload),
    }
    try:
        with CommandQueue(path) as queue:
            queue.enqueue_bound(agent_id, tenant_id, envelope, secret)
    except (QueueConflict, ValueError, TypeError) as exc:
        raise HTTPException(status_code=409, detail="Command rejected") from exc
    return {"status": "QUEUED", "command_id": command_id,
            "expires_at": expires_at.isoformat(), "execution_enabled": False}
