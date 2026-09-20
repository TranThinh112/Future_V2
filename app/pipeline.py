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
            usage = getattr(agent, "last_usage", {}) if agent else {}
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
                "status": "fallback" if any(code.startswith("openai_") for code in decision.reason_codes) else "ok",
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "estimated_cost_usd": getattr(agent, "last_cost_usd", 0.0) if agent else 0.0,
                "attempts": getattr(agent, "last_attempts", 0) if agent else 0,
                "validation_error": getattr(agent, "last_error", "") if agent else "",
                "response_preview": getattr(agent, "last_response_preview", "") if agent else "",
            })
    return aggregate(votes, snapshot["symbol"])
