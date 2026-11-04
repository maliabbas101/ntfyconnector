from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.command_queue import CommandQueue

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

def make_item():
    return {"command_id": str(uuid4()),
            "expires_at": (NOW + timedelta(minutes=30)).isoformat(),
            "payload": {"demo": True}, "signature": "a" * 64}

def test_uncertain_delivery_is_detected_but_never_requeued(tmp_path):
    path = str(tmp_path / "queue.db")
    item = make_item()
    with CommandQueue(path) as queue:
        queue.enqueue("agent-a", item)
        assert queue.next_for_agent("agent-a", now=NOW) == item
        assert queue.recover_unacknowledged(
            "agent-a", now=NOW + timedelta(seconds=59)) == []
        assert queue.recover_unacknowledged(
            "agent-b", now=NOW + timedelta(seconds=90)) == []
        assert queue.recover_unacknowledged(
            "agent-a", now=NOW + timedelta(seconds=90)) == [item["command_id"]]
        assert queue.next_for_agent(
            "agent-a", now=NOW + timedelta(seconds=90)) is None
        assert queue.status(item["command_id"]) == "DELIVERED"
        assert queue.acknowledge("agent-a", item["command_id"])
        assert queue.recover_unacknowledged(
            "agent-a", now=NOW + timedelta(seconds=120)) == []

def test_recovery_requires_valid_age_and_aware_time(tmp_path):
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        with pytest.raises(ValueError):
            queue.recover_unacknowledged("agent-a", min_age_seconds=0)
        with pytest.raises(ValueError):
            queue.recover_unacknowledged(
                "agent-a", now=datetime(2026, 1, 1))
