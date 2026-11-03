from types import SimpleNamespace
import pytest
from app.mt5_guard import AccountVerificationError, verify_demo_account

class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self):
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True)
        self.account = SimpleNamespace(
            login=123456, server="Demo-Server", trade_mode=0,
            trade_allowed=True, trade_expert=True,
            equity=10000.0, currency="USD",
        )

    def terminal_info(self):
        return self.terminal

    def account_info(self):
        return self.account

def test_verified_demo_account():
    result = verify_demo_account(FakeMT5(), expected_login=123456,
                                 expected_server="Demo-Server")
    assert result.login == 123456
    assert result.currency == "USD"

@pytest.mark.parametrize("change", [
    {"trade_mode": 2},
    {"trade_mode": 1},
    {"login": 999},
    {"server": "Other-Server"},
    {"trade_allowed": False},
    {"trade_expert": False},
    {"equity": 0},
    {"equity": float("nan")},
])
def test_reject_bad_account(change):
    mt5 = FakeMT5()
    for key, value in change.items():
        setattr(mt5.account, key, value)
    with pytest.raises(AccountVerificationError):
        verify_demo_account(mt5, expected_login=123456,
                            expected_server="Demo-Server")

def test_reject_disconnected_terminal():
    mt5 = FakeMT5()
    mt5.terminal.connected = False
    with pytest.raises(AccountVerificationError):
        verify_demo_account(mt5, expected_login=123456,
                            expected_server="Demo-Server")

def test_reject_missing_account():
    mt5 = FakeMT5()
    mt5.account = None
    with pytest.raises(AccountVerificationError):
        verify_demo_account(mt5, expected_login=123456,
                            expected_server="Demo-Server")
