from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.command_queue import CommandQueue


def test_expiry_at_exact_second_is_not_delivered(tmp_path):
    at = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    command_id = str(uuid4())
    envelope = {
        "command_id": command_id,
        "expires_at": at.isoformat(),
        "payload": {},
        "signature": "a" * 64,
    }
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        queue.enqueue("agent", envelope)
        assert queue.next_for_agent(
            "agent", now=at - timedelta(microseconds=1)) == envelope
        assert queue.status(command_id) == "DELIVERED"


def test_exact_expiry_and_recovery_cutoff(tmp_path):
    at = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)
    command_id = str(uuid4())
    envelope = {
        "command_id": command_id,
        "expires_at": at.isoformat(),
        "payload": {},
        "signature": "a" * 64,
    }
    with CommandQueue(str(tmp_path / "queue.db")) as queue:
        queue.enqueue("agent", envelope)
        assert queue.next_for_agent("agent", now=at) is None
        assert queue.status(command_id) == "EXPIRED"
