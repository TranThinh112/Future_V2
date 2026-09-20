from typing import Literal

from app.schemas import AgentDecision, Consensus

WEIGHT_DOMAINS={
    "TIDAL": ("trend", .20),
    "NORO": ("momentum", .15),
    "RUNE": ("regime", .15),
    "ZEPHR": ("liquidity", .10),
    "LUMEN": ("sentiment", .10),
    "OKAPI": ("portfolio", .10),
    "VESKA": ("execution", .10),
    "MARIN": ("critic", .10),
}
WEIGHTS={agent: weight for agent, (_, weight) in WEIGHT_DOMAINS.items()}
def aggregate(votes: list[AgentDecision], symbol: str) -> Consensus:
    if len(votes)!=8 or any(v.data_quality!="good" or v.veto for v in votes): return Consensus(symbol=symbol,action="hold",score=0,approved=False,votes=votes,reason_codes=["invalid_or_veto"])
    score=sum(WEIGHTS[v.agent_name]*v.confidence*(1 if v.action in ("buy","sell") else 0) for v in votes)
    actions=[v.action for v in votes]
    action: Literal["buy", "sell", "hold"] = max(("buy","sell"), key=actions.count) if score>=.72 else "hold"
    return Consensus(symbol=symbol,action=action,score=score,approved=score>=.72 and action!="hold",votes=votes,reason_codes=[])
