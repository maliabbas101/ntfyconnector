import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.parser import parse_signal

SAMPLE = """@Mohid @Forex Alert
BUY XAUUSD CMP 4042.8
SL : 4037.0 (-58 pips)
TP-1 : 4056.0 (+132 pips)
TP-2 : 4082.0 (+392 pips)"""

def test_parse_buy():
    result = parse_signal(SAMPLE)
    assert result.symbol == "XAUUSD"
    assert result.side == "BUY"
    assert str(result.stop_loss) == "4037.0"

def test_reject_bad_levels():
    with pytest.raises(ValueError):
        parse_signal(SAMPLE.replace("4037.0", "4050.0"))

def test_reject_missing_target():
    with pytest.raises(ValueError):
        parse_signal(SAMPLE.replace("TP-2", "TARGET"))

def test_dry_run_api():
    response = TestClient(app).post("/v1/signals/validate", json={"text": SAMPLE})
    assert response.status_code == 200
    assert response.json()["execution_enabled"] is False
    assert response.json()["signal"]["side"] == "BUY"
