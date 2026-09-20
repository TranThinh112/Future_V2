import time

from app.agents.base import hold
from app.consensus.engine import aggregate

ORDER = ("TIDAL", "NORO", "LUMEN", "ZEPHR", "OKAPI", "RUNE", "VESKA", "MARIN")

async def analyze(snapshot, agents, on_agent_decision=None):
    votes = []
    for name in ORDER:
        started = time.time()
        agent = agents.get(name)
        decision = await agent.decide(snapshot) if agent else hold(name, snapshot.get("symbol", ""))
        votes.append(decision)
        if on_agent_decision:
            on_agent_decision({
                "ts": time.time(),
                "agent_name": decision.agent_name,
                "symbol": decision.symbol,
                "action": decision.action,
                "confidence": decision.confidence,
                "time_horizon": decision.time_horizon,
                "entry_price": decision.entry_price,
                "stop_loss_price": decision.stop_loss_price,
                "take_profit_price": decision.take_profit_price,
                "suggested_position_pct": decision.suggested_position_pct,
                "reason_codes": decision.reason_codes,
                "invalidators": decision.invalidators,
                "data_quality": decision.data_quality,
                "veto": decision.veto,
                "latency_ms": round((time.time() - started) * 1000, 2),
                "status": "fallback" if "malformed_or_timeout" in decision.reason_codes or "openai_key_missing" in decision.reason_codes else "ok",
            })
    return aggregate(votes, snapshot["symbol"])
