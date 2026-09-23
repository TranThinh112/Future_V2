import asyncio

from app.config import Settings
from app.orchestrator import Orchestrator


def test_orchestrator_without_key_fails_closed():
    result=asyncio.run(Orchestrator(Settings()).decision({"symbol":"BTC-USDT"}))
    assert not result.approved and result.action=="hold" and len(result.votes)==8


def test_orchestrator_emits_agent_audit_events():
    events = []
    result=asyncio.run(Orchestrator(Settings()).decision({"symbol":"BTC-USDT"}, events.append))
    assert len(events) == 8
    assert {event["agent_name"] for event in events} == {"TIDAL", "NORO", "LUMEN", "ZEPHR", "OKAPI", "RUNE", "VESKA", "MARIN"}
    assert all("latency_ms" in event and event["symbol"] == "BTC-USDT" for event in events)
    assert all("input_tokens" in event and "estimated_cost_usd" in event for event in events)
    assert len(result.votes) == 8


def test_agent_prompt_requires_domain_context():
    from app.agents.prompts import PROMPTS, SYSTEM_SUFFIX

    assert "news" in PROMPTS["LUMEN"]
    assert "portfolio" in PROMPTS["OKAPI"]
    assert "positions" in PROMPTS["MARIN"] or "open positions" in PROMPTS["MARIN"]
    assert "orderbook" in PROMPTS["ZEPHR"]
    assert "risk" in PROMPTS["RUNE"]
    assert "data_quality" in SYSTEM_SUFFIX

def test_pipeline_early_stops_after_veto_and_audits_skips():
    from app.pipeline import ORDER, analyze
    from app.schemas import AgentDecision

    class FakeAgent:
        def __init__(self, name, decision):
            self.name = name
            self.decision = decision
            self.calls = 0
            self.last_usage = {"input_tokens": 11, "output_tokens": 3, "total_tokens": 14}
            self.last_cost_usd = 0.01
            self.last_attempts = 1
            self.last_error = ""
            self.last_response_preview = "{}"

        async def decide(self, snapshot):
            self.calls += 1
            return self.decision

    first = AgentDecision(agent_name="RUNE", symbol="BTC-USDT", action="hold", confidence=0.9, suggested_position_pct=0, veto=True, reason_codes=["risk_veto"])
    agents = {"RUNE": FakeAgent("RUNE", first)}
    for name in ORDER[1:]:
        agents[name] = FakeAgent(name, AgentDecision(agent_name=name, symbol="BTC-USDT", action="buy", confidence=0.9, suggested_position_pct=0.1))
    events = []
    result = asyncio.run(analyze({"symbol": "BTC-USDT"}, agents, events.append))
    assert result.action == "hold" and not result.approved
    assert agents["RUNE"].calls == 1
    assert all(agents[name].calls == 0 for name in ORDER[1:])
    assert len(events) == 8
    assert events[0]["early_stop_trigger"] is True
    assert events[1]["status"] == "skipped"
    assert events[1]["stopped_by"] == "RUNE"
    assert events[1]["stop_reason"] == "veto"
