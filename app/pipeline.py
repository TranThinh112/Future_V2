import time

from app.agents.base import hold
from app.consensus.engine import aggregate
from app.schemas import AgentDecision

# Cheap/risk gates first. Expensive opportunity/critic agents run only if hard gates pass.
ORDER = ("RUNE", "OKAPI", "ZEPHR", "LUMEN", "TIDAL", "NORO", "VESKA", "MARIN")
HARD_HOLD_PATTERNS = (
    "buying_power_insufficient",
    "insufficient_buying_power",
    "notional_exceeds_available_cash",
    "proposal_not_executable",
    "not_executable",
    "liquidity_bad",
    "orderbook_liquidity_bad",
    "api_unhealthy",
)


def _event(agent, decision, started, status="ok", **extra):
    usage = getattr(agent, "last_usage", {}) if agent else {}
    payload = {
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
        "status": status if status != "ok" else ("fallback" if any(code.startswith("openai_") for code in decision.reason_codes) else "ok"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
        "estimated_cost_usd": getattr(agent, "last_cost_usd", 0.0) if agent else 0.0,
        "attempts": getattr(agent, "last_attempts", 0) if agent else 0,
        "validation_error": getattr(agent, "last_error", "") if agent else "",
        "response_preview": getattr(agent, "last_response_preview", "") if agent else "",
    }
    payload.update(extra)
    return payload


def _hard_hold(decision: AgentDecision) -> str:
    if decision.action != "hold":
        return ""
    text = " ".join(decision.reason_codes + decision.invalidators).lower()
    return next((pattern for pattern in HARD_HOLD_PATTERNS if pattern in text), "")


def _skip_decision(name: str, symbol: str, reason: str) -> AgentDecision:
    return AgentDecision(
        agent_name=name,
        symbol=symbol,
        action="hold",
        confidence=0,
        suggested_position_pct=0,
        data_quality="good",
        reason_codes=["early_stop_skipped", reason],
    )


async def analyze(snapshot, agents, on_agent_decision=None, *, early_stop=True,
                  stop_on_degraded=True, stop_on_hard_hold=True):
    votes = []
    stop_reason = ""
    stopped_by = ""
    called_agents = []
    for index, name in enumerate(ORDER):
        started = time.time()
        agent = agents.get(name)
        decision = await agent.decide(snapshot) if agent else hold(name, snapshot.get("symbol", ""))
        votes.append(decision)
        called_agents.append(name)
        if decision.veto:
            stop_reason = "veto"
        elif stop_on_degraded and decision.data_quality != "good":
            stop_reason = f"data_quality_{decision.data_quality}"
        elif stop_on_hard_hold:
            hard_reason = _hard_hold(decision)
            if hard_reason:
                stop_reason = hard_reason
        if stop_reason:
            stopped_by = name
        if on_agent_decision:
            on_agent_decision(_event(
                agent, decision, started,
                early_stop_trigger=bool(stop_reason),
                stop_reason=stop_reason,
                called_agents=called_agents.copy(),
            ))
        if early_stop and stop_reason:
            skipped = list(ORDER[index + 1:])
            for skipped_name in skipped:
                skipped_decision = _skip_decision(skipped_name, snapshot.get("symbol", ""), stop_reason)
                votes.append(skipped_decision)
                if on_agent_decision:
                    on_agent_decision(_event(
                        None,
                        skipped_decision,
                        time.time(),
                        status="skipped",
                        early_stop=True,
                        stopped_by=stopped_by,
                        stop_reason=stop_reason,
                        called_agents=called_agents.copy(),
                        skipped_agents=skipped,
                    ))
            break
    return aggregate(votes, snapshot["symbol"])
