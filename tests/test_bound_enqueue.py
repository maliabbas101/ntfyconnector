from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.agent_auth import sign_command
from app.command_queue import CommandQueue, QueueConflict

KEY = b"z" * 32

def make_envelope(agent, tenant):
    cid = str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"agent_id": agent, "tenant_id": tenant,
               "command_id": cid, "expires_at": expiry.isoformat()}
    return {"command_id": cid, "expires_at": expiry.isoformat(),
            "payload": payload,
            "signature": sign_command(KEY, cid, expiry, payload)}

def test_enrollment_and_signature_required(tmp_path):
    agent, tenant, other = str(uuid4()), str(uuid4()), str(uuid4())
    with CommandQueue(str(tmp_path / "queue.db")) as q:
        env = make_envelope(agent, tenant)
        with pytest.raises(QueueConflict):
            q.enqueue_bound(agent, tenant, env, KEY)
        q.enroll_agent(agent, tenant)
        q.enroll_agent(agent, tenant)
        with pytest.raises(QueueConflict):
            q.enroll_agent(agent, other)
        with pytest.raises(QueueConflict):
            q.enqueue_bound(agent, other, env, KEY)
        with pytest.raises(QueueConflict):
            q.enqueue_bound(other, tenant, env, KEY)
        altered = dict(env, payload=dict(env["payload"], tenant_id=other))
        with pytest.raises(ValueError):
            q.enqueue_bound(agent, tenant, altered, KEY)
        q.enqueue_bound(agent, tenant, env, KEY)
        q.enqueue_bound(agent, tenant, env, KEY)
        assert q.next_for_agent(other) is None
        assert q.next_for_agent(agent) == env
