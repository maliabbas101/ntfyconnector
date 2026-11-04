from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from app.agent_auth import SignedEnvelope, sign_command
from app.agent_identity import AgentIdentity, AgentIdentityError, verify_bound_command

KEY = b"q" * 32

def test_signed_agent_tenant_and_account_pins():
    agent, tenant, cid = str(uuid4()), str(uuid4()), str(uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(minutes=2)
    identity = AgentIdentity(agent, tenant, 123, "Demo")
    payload = {
        "agent_id": agent, "tenant_id": tenant, "command_id": cid,
        "expires_at": expiry.isoformat(), "expected_login": 123,
        "expected_server": "Demo",
        "signal": {"symbol": "XAUUSD", "side": "BUY",
                   "reference_price": "4042.8", "stop_loss": "4037",
                   "take_profit_1": "4056", "take_profit_2": "4082"},
        "policy": {"max_risk_fraction": "0.01", "max_volume": "1", "max_spread": "0.5"},
        "broker": {"is_demo": True, "trading_enabled": True, "equity": "1000",
                   "volume_min": "0.01", "volume_max": "10", "volume_step": "0.01",
                   "spread": "0.2", "loss_per_lot_at_stop": "580"},
    }
    def signed(data):
        return SignedEnvelope(command_id=cid, expires_at=expiry, payload=data,
                              signature=sign_command(KEY, cid, expiry, data))
    assert verify_bound_command(signed(payload), KEY, identity).expected_login == 123
    for field, value in (("agent_id", str(uuid4())),
                         ("tenant_id", str(uuid4())),
                         ("expected_login", 456),
                         ("expected_server", "Other")):
        modified = dict(payload, **{field: value})
        with pytest.raises(AgentIdentityError):
            verify_bound_command(signed(modified), KEY, identity)
    with pytest.raises(ValueError):
        verify_bound_command(signed(payload), b"wrong" * 8, identity)
