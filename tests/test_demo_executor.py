"""Offline safety tests: no real MetaTrader installation or account required."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from app.agent_journal import CommandJournal
from app.demo_executor import execute_demo_once


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    TRADE_ACTION_DEAL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self, *, live=False, check_retcode=0):
        self.live = live
        self.check_retcode = check_retcode
        self.sends = []
        self.checks = []

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True)

    def account_info(self):
        return SimpleNamespace(
            login=123, server="Demo", trade_mode=1 if self.live else 0,
            trade_allowed=True, trade_expert=True, equity=10000.0,
            currency="USD")

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=4042.6, ask=4042.8)

    def order_calc_profit(self, order_type, symbol, lots, entry, sl):
        return -580.0 * lots

    def order_check(self, request):
        self.checks.append(request)
        return SimpleNamespace(retcode=self.check_retcode)

    def order_send(self, request):
        self.sends.append(request)
        return SimpleNamespace(retcode=10009)


def sample_command():
    cid = str(uuid4())
    return SimpleNamespace(
        command_id=cid, expected_login=123, expected_server="Demo",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        signal=SimpleNamespace(
            symbol="XAUUSD", side="BUY", reference_price=Decimal("4042.8"),
            stop_loss=Decimal("4037"), take_profit_1=Decimal("4056")),
        policy=SimpleNamespace(max_spread=Decimal("0.5"),
                               max_risk_fraction=Decimal("0.01")),
        model_dump=lambda mode: {"command_id": cid, "fixture": True})


def approve(monkeypatch):
    from app import demo_executor
    monkeypatch.setattr(demo_executor, "preflight_demo_signal",
                        lambda *args, **kwargs: SimpleNamespace(
                            approved_for_review=True, volume="0.1"))


def test_disarmed_never_journals_or_touches_broker(tmp_path):
    mt5 = FakeMT5()
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5)
        assert result["state"] == "NOT_ARMED"
        assert journal.get(cmd.command_id) is None
        assert mt5.sends == []


def test_live_account_rejected_even_when_armed(monkeypatch, tmp_path):
    approve(monkeypatch)
    mt5 = FakeMT5(live=True)
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["state"] == "REJECTED"
        assert journal.get(cmd.command_id)["state"] == "REJECTED"
    assert mt5.sends == []
    assert mt5.checks == []


def test_demo_send_is_once_and_must_be_manually_reconciled(monkeypatch, tmp_path):
    approve(monkeypatch)
    mt5 = FakeMT5()
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["state"] == "EXECUTION_UNKNOWN"
        assert journal.get(cmd.command_id)["state"] == "EXECUTION_UNKNOWN"
        assert len(mt5.sends) == 1
        assert mt5.sends[0]["sl"] == 4037
        assert mt5.sends[0]["tp"] == 4056
        again = execute_demo_once(cmd, journal, mt5, armed=True)
        assert again["duplicate"] is True
        assert len(mt5.sends) == 1


def test_failed_order_check_never_sends(monkeypatch, tmp_path):
    approve(monkeypatch)
    mt5 = FakeMT5(check_retcode=10013)
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["reason"] == "BROKER_ORDER_CHECK_FAILED"
        assert journal.get(cmd.command_id)["state"] == "REJECTED"
        assert mt5.sends == []


def test_expired_command_never_sends(monkeypatch, tmp_path):
    approve(monkeypatch)
    mt5 = FakeMT5()
    cmd = sample_command()
    cmd.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["reason"] == "EXPIRED"
        assert mt5.sends == []


def test_real_broker_preflight_path_submits_demo_only(tmp_path):
    from app.parser import parse_signal
    from app.risk import RiskPolicy

    class BrokerFake(FakeMT5):
        def symbol_info(self, symbol):
            return SimpleNamespace(visible=True, volume_min=0.01,
                                   volume_max=10.0, volume_step=0.01)

        def order_calc_profit(self, order_type, symbol, lots, entry, sl):
            return -580.0 * lots

    mt5 = BrokerFake()
    cmd = sample_command()
    cmd.signal = parse_signal(
        "BUY XAUUSD CMP 4042.8\nSL: 4037\nTP-1: 4056\nTP-2: 4082")
    cmd.policy = RiskPolicy(
        max_risk_fraction="0.01", max_volume="1", max_spread="0.5")
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["state"] == "EXECUTION_UNKNOWN"
        assert len(mt5.sends) == 1
        assert mt5.sends[0]["volume"] == 0.17
        assert journal.get(cmd.command_id)["state"] == "EXECUTION_UNKNOWN"


def test_order_send_exception_is_not_retried(monkeypatch, tmp_path):
    approve(monkeypatch)

    class RaisingBroker(FakeMT5):
        def order_send(self, request):
            self.sends.append(request)
            raise ConnectionError("simulated uncertain MT5 response")

    mt5 = RaisingBroker()
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        assert execute_demo_once(cmd, journal, mt5, armed=True)[
            "state"] == "EXECUTION_UNKNOWN"
        assert execute_demo_once(cmd, journal, mt5, armed=True)[
            "duplicate"] is True
        assert journal.get(cmd.command_id)["state"] == "EXECUTION_UNKNOWN"
    assert len(mt5.sends) == 1


def test_signed_reference_price_drift_blocks_execution(monkeypatch, tmp_path):
    approve(monkeypatch)
    mt5 = FakeMT5()
    cmd = sample_command()
    cmd.signal.reference_price = Decimal("4000")
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["reason"] == "PRICE_DRIFT"
        assert journal.get(cmd.command_id)["state"] == "REJECTED"
        assert mt5.sends == []


def test_final_broker_risk_recheck_prevents_order(monkeypatch, tmp_path):
    approve(monkeypatch)

    class IncreasedLossBroker(FakeMT5):
        def order_calc_profit(self, order_type, symbol, lots, entry, sl):
            return -1500.0

    mt5 = IncreasedLossBroker()
    cmd = sample_command()
    with CommandJournal(str(tmp_path / "journal.db")) as journal:
        result = execute_demo_once(cmd, journal, mt5, armed=True)
        assert result["reason"] == "FINAL_RISK_EXCEEDED"
        assert journal.get(cmd.command_id)["state"] == "REJECTED"
        assert mt5.sends == []
