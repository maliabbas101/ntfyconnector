from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from app.command_queue import CommandQueue, QueueConflict


def test_uncertain_report_blocks_ack_until_reconciliation(tmp_path):
    path = str(tmp_path / "queue.db")
    command_id = str(uuid4())
    envelope = {
        "command_id": command_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "payload": {},
        "signature": "a" * 64,
    }
    with CommandQueue(path) as queue:
        queue.enqueue("agent-a", envelope)
        assert queue.next_for_agent("agent-a") == envelope
        with pytest.raises(QueueConflict):
            queue.report_journal_state("agent-a", command_id, "RECONCILED")
        assert queue.report_journal_state("agent-a", command_id, "EXECUTION_UNKNOWN")
        assert not queue.acknowledge_reported("agent-a", command_id)
        assert queue.status(command_id) == "DELIVERED"
        assert queue.report_journal_state("agent-a", command_id, "RECONCILED")
        assert queue.acknowledge_reported("agent-a", command_id)
        assert queue.acknowledge_reported("agent-a", command_id)
