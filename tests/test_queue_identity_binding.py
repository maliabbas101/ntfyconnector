from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.command_queue import CommandQueue, QueueConflict

def test_bound_payload_cannot_be_queued_for_another_agent(tmp_path):
    agent_id = str(uuid4())
    other_id = str(uuid4())
    command = {
        "command_id": str(uuid4()),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "payload": {"agent_id": agent_id, "tenant_id": str(uuid4())},
        "signature": "a" * 64,
    }
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        with pytest.raises(QueueConflict):
            queue.enqueue(other_id, command)
        assert queue.status(command["command_id"]) is None
        queue.enqueue(agent_id, command)
        assert queue.next_for_agent(other_id) is None
        assert queue.next_for_agent(agent_id) == command
