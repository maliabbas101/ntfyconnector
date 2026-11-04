import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.agent_auth import sign_command
from app.command_queue import CommandQueue
from app.main import app

KEY = b"t" * 32


def test_dev_submission_enforces_tenant_and_agent(monkeypatch, tmp_path):
    tenant, agent, other = str(uuid4()), str(uuid4()), str(uuid4())
    path = str(tmp_path / "queue.sqlite")
    monkeypatch.setenv("DEMO_COMMAND_TENANT_ID", tenant)
    monkeypatch.setenv("DEMO_COMMAND_SUBMIT_TOKEN_SHA256",
                       hashlib.sha256(b"submit-secret").hexdigest())
    monkeypatch.setenv("DEMO_COMMAND_SIGNING_KEY_HEX", KEY.hex())
    monkeypatch.setenv("DEMO_COMMAND_QUEUE_PATH", path)
    with CommandQueue(path) as queue:
        queue.enroll_agent(agent, tenant)
        queue.enroll_agent(other, str(uuid4()))
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"agent_id": agent, "tenant_id": tenant,
               "command_id": cid, "expires_at": expiry.isoformat()}
    envelope = {"command_id": cid, "expires_at": expiry.isoformat(),
                "payload": payload,
                "signature": sign_command(KEY, cid, expiry, payload)}
    client = TestClient(app)
    url = "/v1/dev/tenants/commands"
    body = {"agent_id": agent, "envelope": envelope}
    auth = {"Authorization": "Bearer submit-secret"}
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body,
                       headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post(url, json=dict(body, agent_id=other),
                       headers=auth).status_code == 409
    altered = dict(envelope, payload=dict(payload, tenant_id=str(uuid4())))
    assert client.post(url, json=dict(body, envelope=altered),
                       headers=auth).status_code == 409
    assert client.post(url, json=body, headers=auth).status_code == 202
    assert client.post(url, json=body, headers=auth).status_code == 202
    with CommandQueue(path) as queue:
        assert queue.next_for_agent(other) is None
        assert queue.next_for_agent(agent) == envelope
