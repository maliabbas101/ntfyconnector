from uuid import uuid4
import pytest
from app.agent_journal import CommandJournal, CommandConflict

def test_command_is_durable_and_idempotent(tmp_path):
    path = str(tmp_path / "agent.sqlite")
    command_id = str(uuid4())
    with CommandJournal(path) as journal:
        assert journal.receive(command_id, {"symbol": "XAUUSD"}) == "RECEIVED"
        journal.mark_execution_unknown(command_id)
    with CommandJournal(path) as journal:
        assert journal.receive(command_id, {"symbol": "XAUUSD"}) == "EXECUTION_UNKNOWN"
        with pytest.raises(CommandConflict):
            journal.mark_execution_unknown(command_id)
        journal.reconcile(command_id, "broker deal 123")
        assert journal.get(command_id)["state"] == "RECONCILED"

def test_reused_command_id_with_different_payload_is_rejected(tmp_path):
    command_id = str(uuid4())
    with CommandJournal(str(tmp_path / "agent.sqlite")) as journal:
        journal.receive(command_id, {"side": "BUY"})
        with pytest.raises(CommandConflict):
            journal.receive(command_id, {"side": "SELL"})

def test_rejected_command_cannot_be_retried(tmp_path):
    command_id = str(uuid4())
    with CommandJournal(str(tmp_path / "agent.sqlite")) as journal:
        journal.receive(command_id, {"side": "BUY"})
        journal.reject(command_id, "demo account required")
        assert journal.receive(command_id, {"side": "BUY"}) == "REJECTED"
        with pytest.raises(CommandConflict):
            journal.mark_execution_unknown(command_id)

def test_reconciliation_requires_broker_evidence(tmp_path):
    command_id = str(uuid4())
    with CommandJournal(str(tmp_path / "agent.sqlite")) as journal:
        journal.receive(command_id, {"side": "BUY"})
        with pytest.raises(ValueError):
            journal.reconcile(command_id, "")
        with pytest.raises(CommandConflict):
            journal.reconcile(command_id, "no execution found")
