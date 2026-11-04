"""ACK retry after a lost HTTP response is safe and idempotent."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent_api import router
from app.command_queue import CommandQueue

def test_ack_retry_after_response_loss(monkeypatch, tmp_path):
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_AGENT_ID", "agent-a")
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", hashlib.sha256(b"token").hexdigest())
    item = {
        "command_id": str(uuid4()),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "payload": {"demo": True}, "signature": "a" * 64,
    }
    with CommandQueue(path) as queue:
        queue.enqueue("agent-a", item)
        assert queue.next_for_agent("agent-a") == item

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    url = "/v1/agent/commands/" + item["command_id"] + "/ack"
    headers = {"Authorization": "Bearer token"}
    assert client.post(url, headers=headers).status_code == 200
    # Pretend the first response was lost: retrying must still return success.
    assert client.post(url, headers=headers).json()["status"] == "ACKNOWLEDGED"
    with CommandQueue(path) as queue:
        assert queue.status(item["command_id"]) == "ACKNOWLEDGED"
        assert queue.next_for_agent("agent-a") is None

def test_ack_rejects_pending_and_other_agent(monkeypatch, tmp_path):
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_AGENT_ID", "agent-a")
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", hashlib.sha256(b"token").hexdigest())
    item = {
        "command_id": str(uuid4()),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "payload": {}, "signature": "a" * 64,
    }
    with CommandQueue(path) as queue:
        queue.enqueue("agent-b", item)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.post("/v1/agent/commands/" + item["command_id"] + "/ack",
                       headers={"Authorization": "Bearer token"}).status_code == 404
    with CommandQueue(path) as queue:
        assert queue.status(item["command_id"]) == "PENDING"
