"""Local complete notification -> signed queue -> broker mock flow."""
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.ingestion import Base, Source, get_db, token_digest
from app.agent_auth import SignedEnvelope, verify_envelope
from app.agent_identity import AgentIdentity
from app.agent_journal import CommandJournal
from app.agent_transport import poll_once
from app.command_queue import CommandQueue
from app.risk import RiskPolicy
from app.signal_dispatcher import dispatch_once


class DemoMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1

    def __init__(self):
        self.sends = []

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(login=123, server="Demo", trade_mode=0,
                               trade_allowed=True, trade_expert=True,
                               equity=10000.0, currency="USD")

    def symbol_info(self, symbol):
        return SimpleNamespace(visible=True, volume_min=0.01,
                               volume_max=10.0, volume_step=0.01)

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=4042.6, ask=4042.8)

    def order_calc_profit(self, order_type, symbol, lots, price, sl):
        return -580.0 * lots

    def order_check(self, request):
        return SimpleNamespace(retcode=0)

    def order_send(self, request):
        self.sends.append(request)
        return SimpleNamespace(retcode=10009)


def test_notification_to_demo_order_attempt_is_signed_and_not_replayed(
    monkeypatch, tmp_path
):
    tenant, agent = str(uuid4()), str(uuid4())
    key = b"p" * 32
    queue_path = str(tmp_path / "queue.db")
    db_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(db_engine)
    Session = sessionmaker(bind=db_engine, expire_on_commit=False)
    source_id = str(uuid4())
    with Session() as session:
        session.add(Source(id=source_id, tenant_id=tenant,
                           token_hash=token_digest("source-secret"), enabled=True))
        session.commit()
    app.dependency_overrides[get_db] = lambda: Session()
    monkeypatch.setenv("DEMO_AGENT_ID", agent)
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256",
                       hashlib.sha256(b"agent-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", queue_path)
    try:
        with TestClient(app) as server:
            incoming = server.post(
                f"/v1/ingest/tenants/{tenant}/sources/{source_id}",
                headers={"Authorization": "Bearer source-secret"},
                json={"external_id": "ntfy-notification-1",
                      "text": "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082"})
            assert incoming.status_code == 202
            assert incoming.json()["status"] == "VALIDATED"

            with CommandQueue(queue_path) as queue:
                queue.enroll_agent(agent, tenant)
                with Session() as session:
                    for _ in range(2):
                        assert dispatch_once(
                            session, queue, tenant_id=tenant, agent_id=agent,
                            expected_login=123, expected_server="Demo",
                            signing_secret=key,
                            policy=RiskPolicy(max_risk_fraction="0.005",
                                              max_volume="0.1",
                                              max_spread="0.5"))["validated_processed"] == 1

            def http_transport(request):
                response = server.request(
                    request.method, request.url.path,
                    headers=dict(request.headers),
                    content=request.content, follow_redirects=False)
                return httpx.Response(response.status_code,
                                      headers=dict(response.headers),
                                      content=response.content)

            broker = DemoMT5()
            with httpx.Client(transport=httpx.MockTransport(http_transport)) as client:
                with CommandJournal(str(tmp_path / "agent.db")) as journal:
                    options = dict(
                        endpoint="https://agent.example.com", agent_token="agent-secret",
                        signing_secret=key, journal=journal, mt5=broker, client=client,
                        identity=AgentIdentity(agent, tenant, 123, "Demo"),
                        arm_demo_execution=True)
                    result = poll_once(**options)
                    assert result["status"] == "UNACKNOWLEDGED"
                    assert result["result"]["state"] == "EXECUTION_UNKNOWN"
                    cid = result["result"]["command_id"]
                    assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"
                    assert len(broker.sends) == 1
                    assert broker.sends[0]["comment"].startswith("ntfy-")
                    assert poll_once(**options)["status"] == "EMPTY"
                    assert len(broker.sends) == 1
            with CommandQueue(queue_path) as queue:
                assert queue.reported_state(agent, cid) == "EXECUTION_UNKNOWN"
                assert queue.status(cid) == "DELIVERED"
    finally:
        app.dependency_overrides.clear()
        db_engine.dispose()
