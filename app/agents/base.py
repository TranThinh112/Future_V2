from app.schemas import AgentDecision

AGENT_NAMES=("VESKA","NORO","LUMEN","TIDAL","ZEPHR","RUNE","OKAPI","MARIN")
def hold(agent_name,symbol,reason="insufficient_data"): return AgentDecision(agent_name=agent_name,symbol=symbol,action="hold",confidence=0,suggested_position_pct=0,data_quality="bad",reason_codes=[reason])
