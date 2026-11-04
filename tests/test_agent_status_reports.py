import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.agent_api import router
from app.command_queue import CommandQueue

def test_authenticated_monotonic_reports(monkeypatch, tmp_path):
    path = str(tmp_path / "queue.db")
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    monkeypatch.setenv("DEMO_AGENT_ID", "agent-a")
    monkeypatch.setenv("DEMO_AGENT_TOKEN_SHA256", hashlib.sha256(b"token").hexdigest())
    item = {"command_id": str(uuid4()),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "payload": {}, "signature": "a" * 64}
    with CommandQueue(path) as q:
        q.enqueue("agent-a", item)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    url = "/v1/agent/commands/" + item["command_id"] + "/journal-state"
    auth = {"Authorization": "Bearer token"}
    assert client.post(url, json={"state": "REJECTED"}, headers=auth).status_code == 404
    assert client.get("/v1/agent/commands/next", headers=auth).status_code == 200
    assert client.post(url, json={"state": "REJECTED"}).status_code == 401
    assert client.post(url, json={"state": "REJECTED"}, headers=auth).status_code == 200
    assert client.post(url, json={"state": "REJECTED"}, headers=auth).status_code == 200
    assert client.post(url, json={"state": "RECONCILED"}, headers=auth).status_code == 409
    with CommandQueue(path) as q:
        assert q.reported_state("agent-a", item["command_id"]) == "REJECTED"
        assert q.reported_state("agent-b", item["command_id"]) is None
        assert q.status(item["command_id"]) == "DELIVERED"
