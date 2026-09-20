import asyncio
import json

from app.agents.openai_adapter import OpenAIAgent, sanitize_snapshot


def test_agent_without_key_holds():
    decision=asyncio.run(OpenAIAgent("NORO","").decide({"symbol":"BTC-USDT"}))
    assert decision.action=="hold" and decision.data_quality=="bad"

def test_sanitize_snapshot_removes_secret_like_keys():
    snapshot = {
        "symbol": "BTC-USDT",
        "okx_api_key": "secret",
        "nested": {"passphrase": "hidden", "price": 100},
        "rows": [{"authorization": "bearer", "volume": 2}],
    }
    assert sanitize_snapshot(snapshot) == {
        "symbol": "BTC-USDT",
        "nested": {"price": 100},
        "rows": [{"volume": 2}],
    }

def test_agent_retries_then_validates_json(monkeypatch):
    calls = {"count": 0, "payloads": []}
    output = {
        "agent_name": "NORO",
        "symbol": "BTC-USDT",
        "action": "hold",
        "confidence": 0.1,
        "time_horizon": "15m",
        "entry_price": None,
        "stop_loss_price": None,
        "take_profit_price": None,
        "suggested_position_pct": 0,
        "reason_codes": ["test"],
        "invalidators": [],
        "data_quality": "good",
        "veto": False,
    }

    class FakeResponse:
        def raise_for_status(self): return None
        def json(self): return {"output_text": json.dumps(output), "usage": {"input_tokens": 1, "output_tokens": 1}}

    class FakeClient:
        def __init__(self, timeout): self.timeout = timeout
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): return None
        async def post(self, url, headers, json):
            calls["count"] += 1
            calls["payloads"].append(json)
            if calls["count"] == 1:
                raise TimeoutError("first call fails")
            return FakeResponse()

    monkeypatch.setattr("app.agents.openai_adapter.httpx.AsyncClient", FakeClient)
    agent = OpenAIAgent("NORO", "key", retries=1, input_cost_per_million=1, output_cost_per_million=2)
    decision = asyncio.run(agent.decide({"symbol": "BTC-USDT", "api_key": "secret"}))
    assert calls["count"] == 2
    assert decision.agent_name == "NORO"
    user_content = calls["payloads"][-1]["input"][1]["content"]
    assert "api_key" not in user_content
    assert "secret" not in user_content
    assert agent.last_usage == {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    assert agent.last_cost_usd == 0.000003

def test_agent_timeout_is_classified(monkeypatch):
    class FakeClient:
        def __init__(self, timeout): pass
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): return None
        async def post(self, url, headers, json):
            raise TimeoutError("timed out")

    monkeypatch.setattr("app.agents.openai_adapter.httpx.AsyncClient", FakeClient)
    decision = asyncio.run(OpenAIAgent("VESKA", "key", retries=0).decide({"symbol": "ETH-USDT"}))
    assert decision.reason_codes == ["openai_timeout"]

def test_agent_invalid_json_is_classified(monkeypatch):
    class FakeResponse:
        def raise_for_status(self): return None
        def json(self): return {"output_text": "{not-json"}

    class FakeClient:
        def __init__(self, timeout): pass
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): return None
        async def post(self, url, headers, json): return FakeResponse()

    monkeypatch.setattr("app.agents.openai_adapter.httpx.AsyncClient", FakeClient)
    decision = asyncio.run(OpenAIAgent("VESKA", "key", retries=0).decide({"symbol": "ETH-USDT"}))
    assert decision.reason_codes == ["openai_invalid_json"]
