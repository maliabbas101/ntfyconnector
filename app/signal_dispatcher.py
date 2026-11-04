"""Validated ntfy event -> signed demo command dispatcher.

This worker NEVER opens broker orders. Each raw event maps to a stable command
UUID, and queue insertion is idempotent across worker restarts.
"""
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.agent_auth import sign_command
from app.command_queue import CommandQueue
from app.ingestion import RawEvent, SessionLocal
from app.parser import parse_signal
from app.risk import RiskPolicy
from app.tenant_context import set_tenant


def dispatch_once(session, queue, *, tenant_id: str, agent_id: str,
                  expected_login: int, expected_server: str,
                  signing_secret: bytes, policy: RiskPolicy,
                  now: datetime | None = None) -> dict:
    """Dispatch recent validated events for exactly one enrolled tenant agent.

    Do not acknowledge/mark events handled without an atomic outbox. Instead,
    deterministically re-issue the SAME signed envelope; queue uniqueness
    protects against duplicate commands after a crash or process restart.
    """
    tenant_id, agent_id = str(UUID(tenant_id)), str(UUID(agent_id))
    if len(signing_secret) < 32:
        raise ValueError("Signing key is too short")
    if expected_login <= 0 or not expected_server.strip():
        raise ValueError("Expected demo account pin required")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("Timezone-aware clock required")
    current = current.astimezone(timezone.utc)
    if session.bind.dialect.name == "postgresql":
        set_tenant(session, tenant_id)
    events = session.scalars(
        select(RawEvent).where(
            RawEvent.tenant_id == tenant_id, RawEvent.status == "VALIDATED")
        .order_by(RawEvent.received_at.desc()).limit(100)
    ).all()
    queued = expired = 0
    for event in events:
        received = event.received_at
        if received.tzinfo is None or received.utcoffset() is None:
            received = received.replace(tzinfo=timezone.utc)
        expiry = received.astimezone(timezone.utc) + timedelta(minutes=5)
        if expiry <= current:
            expired += 1
            continue
        signal = parse_signal(event.text)
        cid = str(uuid5(NAMESPACE_URL, tenant_id + ":" + agent_id + ":" + event.id))
        payload = {
            "agent_id": agent_id, "tenant_id": tenant_id,
            "command_id": cid, "expires_at": expiry.isoformat(),
            "expected_login": expected_login, "expected_server": expected_server,
            "signal": signal.model_dump(mode="json"),
            "policy": policy.model_dump(mode="json"),
            # The MT5 agent MUST ignore these inert, untrusted placeholders.
            "broker": {"is_demo": False, "trading_enabled": False,
                       "equity": "1", "volume_min": "1", "volume_max": "1",
                       "volume_step": "1", "spread": "0",
                       "loss_per_lot_at_stop": "1"},
        }
        envelope = {
            "command_id": cid, "expires_at": expiry.isoformat(),
            "payload": payload,
            "signature": sign_command(signing_secret, cid, expiry, payload),
        }
        queue.enqueue_bound(agent_id, tenant_id, envelope, signing_secret)
        queued += 1
    return {"validated_processed": queued, "expired_skipped": expired,
            "execution_enabled": False}


def main() -> None:
    """Run a separately deployed worker with server-owned signing credentials."""
    tenant = str(UUID(os.environ["DEMO_COMMAND_TENANT_ID"]))
    agent = str(UUID(os.environ["DEMO_COMMAND_AGENT_ID"]))
    login = int(os.environ["DEMO_COMMAND_AGENT_LOGIN"])
    server = os.environ["DEMO_COMMAND_AGENT_SERVER"]
    secret = bytes.fromhex(os.environ["DEMO_COMMAND_SIGNING_KEY_HEX"])
    path = os.environ["DEMO_COMMAND_QUEUE_PATH"]
    policy = RiskPolicy(
        max_risk_fraction=os.getenv("DEMO_COMMAND_MAX_RISK_FRACTION", "0.005"),
        max_volume=os.getenv("DEMO_COMMAND_MAX_VOLUME", "0.1"),
        max_spread=os.getenv("DEMO_COMMAND_MAX_SPREAD", "0.5"))
    with CommandQueue(path) as queue:
        # Enrollment is provisioned independently; do not auto-enroll agents.
        while True:
            with SessionLocal() as session:
                dispatch_once(
                    session, queue, tenant_id=tenant, agent_id=agent,
                    expected_login=login, expected_server=server,
                    signing_secret=secret, policy=policy)
            time.sleep(2)


if __name__ == "__main__":
    main()
