"""Opt-in local-development agent polling API. Never creates or executes trades."""
import hashlib
import hmac
import os
from contextlib import contextmanager
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel
from typing import Literal
from app.command_queue import QueueConflict
from app.command_queue import CommandQueue

router = APIRouter(prefix="/v1/agent", tags=["agent"])

def authenticate_agent(authorization: str | None) -> str:
    """Use a pre-provisioned single-agent token; disabled unless configured."""
    agent_id = os.getenv("DEMO_AGENT_ID", "")
    token_hash = os.getenv("DEMO_AGENT_TOKEN_SHA256", "")
    if not agent_id or not token_hash or len(token_hash) != 64:
        raise HTTPException(status_code=503, detail="Agent polling not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid agent credentials")
    token = authorization[7:]
    supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if not token or not hmac.compare_digest(supplied, token_hash):
        raise HTTPException(status_code=401, detail="Invalid agent credentials")
    return agent_id

@contextmanager
def open_queue():
    path = os.getenv("DEMO_COMMAND_QUEUE_PATH")
    if not path:
        raise HTTPException(status_code=503, detail="Agent queue not configured")
    with CommandQueue(path) as queue:
        yield queue

@router.get("/commands/next")
def next_command(response: Response, authorization: str | None = Header(default=None)):
    agent_id = authenticate_agent(authorization)
    with open_queue() as queue:
        envelope = queue.next_for_agent(agent_id)
    if envelope is None:
        response.status_code = 204
        return None
    return envelope

@router.get("/commands/recovery")
def recovery_candidates(authorization: str | None = Header(default=None),
                        min_age_seconds: int = 60):
    """List only this agent's stale deliveries; never resend or mutate."""
    agent_id = authenticate_agent(authorization)
    if not 1 <= min_age_seconds <= 86400:
        raise HTTPException(status_code=422, detail="Invalid recovery age")
    with open_queue() as queue:
        ids = queue.recover_unacknowledged(
            agent_id, min_age_seconds=min_age_seconds)
    return {"command_ids": ids, "execution_enabled": False}


@router.get("/commands/{command_id}/receipt")
def command_receipt(command_id: str, authorization: str | None = Header(default=None)):
    """Read-only reconciliation aid; does not redeliver uncertain commands."""
    agent_id = authenticate_agent(authorization)
    try:
        with open_queue() as queue:
            receipt = queue.delivery_receipt(agent_id, command_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Command not found") from None
    if receipt is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return receipt

@router.post("/commands/{command_id}/ack")
def acknowledge_command(command_id: str, authorization: str | None = Header(default=None)):
    agent_id = authenticate_agent(authorization)
    try:
        with open_queue() as queue:
            acknowledged = queue.acknowledge_reported(agent_id, command_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Command not found") from None
    if not acknowledged:
        raise HTTPException(status_code=404, detail="Command not found")
    return {"status": "ACKNOWLEDGED", "execution_enabled": False}

class JournalStateReport(BaseModel):
    state: Literal["RECEIVED", "REJECTED", "EXECUTION_UNKNOWN", "RECONCILED"]

@router.post("/commands/{command_id}/journal-state")
def report_journal_state(command_id: str, body: JournalStateReport,
                         authorization: str | None = Header(default=None)):
    agent_id = authenticate_agent(authorization)
    try:
        with open_queue() as queue:
            recorded = queue.report_journal_state(agent_id, command_id, body.state)
    except ValueError:
        raise HTTPException(status_code=409, detail="Invalid journal report") from None
    if not recorded:
        raise HTTPException(status_code=404, detail="Command not found")
    return {"status": "RECORDED", "execution_enabled": False}
