from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["buy", "sell", "hold", "reduce", "emergency_exit"]
class AgentDecision(BaseModel):
    agent_name: Literal["VESKA","NORO","LUMEN","TIDAL","ZEPHR","RUNE","OKAPI","MARIN"]
    symbol: str; action: Action; confidence: float = Field(ge=0, le=1)
    time_horizon: Literal["5m","15m","1h"] = "15m"
    entry_price: float | None = None; stop_loss_price: float | None = None; take_profit_price: float | None = None
    suggested_position_pct: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list)
    invalidators: list[str] = Field(default_factory=list)
    data_quality: Literal["good","degraded","bad"] = "good"; veto: bool = False

class Consensus(BaseModel):
    symbol: str; action: Action; score: float = Field(ge=0, le=1); approved: bool
    votes: list[AgentDecision]
    reason_codes: list[str] = Field(default_factory=list)
