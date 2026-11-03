from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.command_queue import CommandQueue, QueueConflict

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

def envelope(*, command_id=None, expires=None):
    return {"command_id": command_id or str(uuid4()),
            "expires_at": (expires or NOW + timedelta(minutes=5)).isoformat(),
            "payload": {"signal": "demo"}, "signature": "a" * 64}

def test_delivery_is_agent_scoped_and_durable(tmp_path):
    path = str(tmp_path / "queue.db")
    item = envelope()
    with CommandQueue(path) as queue:
        queue.enqueue("agent-a", item)
        assert queue.next_for_agent("agent-b", now=NOW) is None
        assert queue.next_for_agent("agent-a", now=NOW) == item
        assert queue.next_for_agent("agent-a", now=NOW) is None
    with CommandQueue(path) as queue:
        assert queue.status(item["command_id"]) == "DELIVERED"
        assert not queue.acknowledge("agent-b", item["command_id"])
        assert queue.acknowledge("agent-a", item["command_id"])
        assert queue.status(item["command_id"]) == "ACKNOWLEDGED"

def test_duplicate_id_conflict(tmp_path):
    item = envelope()
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        queue.enqueue("a", item)
        queue.enqueue("a", item)
        with pytest.raises(QueueConflict):
            queue.enqueue("b", item)

def test_expired_command_never_delivered(tmp_path):
    item = envelope(expires=NOW - timedelta(seconds=1))
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        queue.enqueue("a", item)
        assert queue.next_for_agent("a", now=NOW) is None
        assert queue.status(item["command_id"]) == "EXPIRED"
