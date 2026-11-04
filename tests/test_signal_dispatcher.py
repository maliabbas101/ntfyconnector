"""Durable ingestion-to-command bridge without live MT5 or network access."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.agent_auth import SignedEnvelope, verify_envelope
from app.command_queue import CommandQueue
from app.ingestion import Base, RawEvent, Source, token_digest
from app.risk import RiskPolicy
from app.signal_dispatcher import dispatch_once

KEY = b"q" * 32
SIGNAL = "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082"


def test_dispatch_validated_event_once_across_restarts(tmp_path):
    tenant, agent, other = str(uuid4()), str(uuid4()), str(uuid4())
    db = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
    Base.metadata.create_all(db)
    received = datetime.now(timezone.utc)
    with Session(db) as session:
        session.add(Source(id="source-a", tenant_id=tenant,
                           token_hash=token_digest("secret"), enabled=True))
        session.add(Source(id="source-b", tenant_id=other,
                           token_hash=token_digest("secret"), enabled=True))
        session.add(RawEvent(id=str(uuid4()), tenant_id=tenant,
                             source_id="source-a", external_id="ntfy-1",
                             text=SIGNAL, status="VALIDATED", received_at=received))
        session.add(RawEvent(id=str(uuid4()), tenant_id=other,
                             source_id="source-b", external_id="ntfy-2",
                             text=SIGNAL, status="VALIDATED", received_at=received))
        session.commit()

    queue_path = str(tmp_path / "commands.db")
    policy = RiskPolicy(max_risk_fraction="0.005",
                        max_volume="0.1", max_spread="0.5")
    with CommandQueue(queue_path) as queue:
        queue.enroll_agent(agent, tenant)
        with Session(db) as session:
            for _ in range(2):
                result = dispatch_once(
                    session, queue, tenant_id=tenant, agent_id=agent,
                    expected_login=123, expected_server="Demo",
                    signing_secret=KEY, policy=policy)
                assert result["validated_processed"] == 1
        envelope = queue.next_for_agent(agent)
        payload = verify_envelope(SignedEnvelope.model_validate(envelope), KEY)
        assert payload["tenant_id"] == tenant
        assert payload["expected_server"] == "Demo"
        assert payload["signal"]["symbol"] == "XAUUSD"
        assert payload["broker"]["is_demo"] is False
        assert queue.next_for_agent(agent) is None


def test_dispatch_skips_expired_events(tmp_path):
    tenant, agent = str(uuid4()), str(uuid4())
    db = create_engine("sqlite://", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
    Base.metadata.create_all(db)
    with Session(db) as session:
        session.add(Source(id="source-a", tenant_id=tenant,
                           token_hash=token_digest("secret"), enabled=True))
        session.add(RawEvent(id=str(uuid4()), tenant_id=tenant,
                             source_id="source-a", external_id="old",
                             text=SIGNAL, status="VALIDATED",
                             received_at=datetime.now(timezone.utc) - timedelta(hours=1)))
        session.commit()
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        queue.enroll_agent(agent, tenant)
        with Session(db) as session:
            result = dispatch_once(
                session, queue, tenant_id=tenant, agent_id=agent,
                expected_login=123, expected_server="Demo",
                signing_secret=KEY,
                policy=RiskPolicy(max_risk_fraction="0.005",
                                  max_volume="0.1", max_spread="0.5"))
        assert result["validated_processed"] == 0
        assert result["expired_skipped"] == 1
        assert queue.next_for_agent(agent) is None
