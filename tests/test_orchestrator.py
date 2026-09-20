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
    assert len(result.votes) == 8
