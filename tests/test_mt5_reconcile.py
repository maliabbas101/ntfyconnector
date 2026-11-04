from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent_journal import CommandJournal
from app.mt5_reconcile import (ReconciliationUnavailable, inspect_uncertain_demo_order,
                               confirm_demo_deal)


class FakeDemo:
    ACCOUNT_TRADE_MODE_DEMO = 0
    DEAL_TYPE_BUY = 0
    DEAL_TYPE_SELL = 1
    DEAL_ENTRY_IN = 0

    def __init__(self, *, live=False, history=None):
        self.live = live
        self.history = history
        self.calls = 0

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(
            login=123, server="Demo", trade_mode=2 if self.live else 0,
            trade_allowed=True, trade_expert=True, equity=10000.0,
            currency="USD")

    def history_deals_get(self, start, end):
        self.calls += 1
        return self.history

    def order_send(self, *_args, **_kwargs):
        raise AssertionError("Reconciliation must never submit orders")


def journal_uncertain(journal, cid):
    journal.receive(cid, {
        "command_id": cid, "expected_login": 123, "expected_server": "Demo",
        "signal": {"symbol": "XAUUSD", "side": "BUY"}})
    journal.mark_execution_unknown(cid)


def test_matching_deal_is_candidate_only(tmp_path):
    cid = str(uuid4())
    comment = "ntfy-" + cid.replace("-", "")[:24]
    mt5 = FakeDemo(history=[
        SimpleNamespace(ticket=12345, order=54321,
                        symbol="XAUUSD", comment=comment,
                        type=0, entry=0, volume=0.1),
        SimpleNamespace(ticket=999, order=888,
                        symbol="EURUSD", comment=comment,
                        type=0, entry=0, volume=0.1),
        SimpleNamespace(ticket=777, order=666,
                        symbol="XAUUSD", comment="unrelated",
                        type=0, entry=0, volume=0.1),
    ])
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        result = inspect_uncertain_demo_order(
            mt5, journal, cid, expected_login=123, expected_server="Demo")
        assert result["candidate_deals"] == [
            {"deal_ticket": 12345, "order_ticket": 54321}]
        assert result["needs_operator_review"] is True
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"
        assert mt5.calls == 1


def test_empty_history_does_not_auto_reject_or_reconcile(tmp_path):
    cid = str(uuid4())
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        result = inspect_uncertain_demo_order(
            FakeDemo(history=[]), journal, cid,
            expected_login=123, expected_server="Demo")
        assert result["candidate_count"] == 0
        assert result["absence_is_not_proof_of_no_execution"]
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"


def test_live_account_denied_before_broker_history_access(tmp_path):
    cid = str(uuid4())
    mt5 = FakeDemo(live=True, history=[])
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        with pytest.raises(RuntimeError):
            inspect_uncertain_demo_order(
                mt5, journal, cid, expected_login=123, expected_server="Demo")
        assert mt5.calls == 0


def test_unavailable_history_keeps_uncertain_state(tmp_path):
    cid = str(uuid4())
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        with pytest.raises(ReconciliationUnavailable):
            inspect_uncertain_demo_order(
                FakeDemo(history=None), journal, cid,
                expected_login=123, expected_server="Demo")
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"


def test_confirmed_matching_deal_reconciles_only_after_operator_action(tmp_path):
    cid = str(uuid4())
    comment = "ntfy-" + cid.replace("-", "")[:24]
    mt5 = FakeDemo(history=[
        SimpleNamespace(ticket=9876, order=8888,
                        symbol="XAUUSD", comment=comment,
                        type=0, entry=0, volume=0.1)])
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        kwargs = dict(mt5=mt5, journal=journal, command_id=cid,
                      expected_login=123, expected_server="Demo",
                      deal_ticket=9876)
        with pytest.raises(ReconciliationUnavailable, match="operator"):
            confirm_demo_deal(**kwargs)
        with pytest.raises(ReconciliationUnavailable, match="ticket"):
            confirm_demo_deal(**dict(kwargs, deal_ticket=1234),
                              operator_confirmed=True)
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"
        result = confirm_demo_deal(**kwargs, operator_confirmed=True)
        assert result["state"] == "RECONCILED"
        assert journal.get(cid)["state"] == "RECONCILED"
        with pytest.raises(ReconciliationUnavailable):
            confirm_demo_deal(**kwargs, operator_confirmed=True)


def test_confirm_demo_deal_never_accepts_unmatched_or_missing_history(tmp_path):
    cid = str(uuid4())
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        with pytest.raises(ReconciliationUnavailable):
            confirm_demo_deal(
                FakeDemo(history=[]), journal, cid, deal_ticket=111,
                expected_login=123, expected_server="Demo",
                operator_confirmed=True)
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"


def test_opposite_direction_and_close_deals_are_not_candidates(tmp_path):
    cid = str(uuid4())
    comment = "ntfy-" + cid.replace("-", "")[:24]
    mt5 = FakeDemo(history=[
        SimpleNamespace(ticket=10, order=11, symbol="XAUUSD",
                        comment=comment, type=1, entry=0, volume=0.1),
        SimpleNamespace(ticket=20, order=21, symbol="XAUUSD",
                        comment=comment, type=0, entry=1, volume=0.1),
        SimpleNamespace(ticket=30, order=31, symbol="XAUUSD",
                        comment=comment, type=0, entry=0, volume=0),
    ])
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        journal_uncertain(journal, cid)
        result = inspect_uncertain_demo_order(
            mt5, journal, cid, expected_login=123, expected_server="Demo")
        assert result["candidate_deals"] == []
        assert journal.get(cid)["state"] == "EXECUTION_UNKNOWN"
