import pytest

from app.market_data.okx import OKXClient


def test_okx_restricts_symbol_and_spot_order_mode():
    client=OKXClient()
    with pytest.raises(ValueError): client.validate_symbol("SOL-USDT")
    with pytest.raises(ValueError): __import__("asyncio").run(client.create_order({"instId":"BTC-USDT","tdMode":"cross"}))

def test_okx_private_ws_login_and_redaction():
    client = OKXClient("api", "secret", "pass")
    login = client.private_ws_login_message(timestamp=1)
    assert login["op"] == "login"
    assert login["args"][0]["apiKey"] == "api"
    assert login["args"][0]["sign"]
    redacted = client.redacted_headers({"OK-ACCESS-KEY": "api", "OK-ACCESS-SIGN": "sig", "Content-Type": "json"})
    assert redacted["OK-ACCESS-KEY"] == "***"
    assert redacted["OK-ACCESS-SIGN"] == "***"
    assert redacted["Content-Type"] == "json"
