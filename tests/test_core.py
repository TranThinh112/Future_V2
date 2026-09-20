import pandas as pd

from app.config import Settings
from app.consensus.engine import aggregate
from app.features.indicators import ema, rsi
from app.schemas import AgentDecision


def vote(name, action="buy"): return AgentDecision(agent_name=name,symbol="BTC-USDT",action=action,confidence=1,suggested_position_pct=.01)
def test_ema_and_rsi():
    s=pd.Series(range(1,50)); assert ema(s,20).iloc[-1] > 0; assert 0 <= rsi(s).iloc[-1] <= 100
def test_consensus_requires_all_agents():
    names=["VESKA","NORO","LUMEN","TIDAL","ZEPHR","RUNE","OKAPI","MARIN"]; assert aggregate([vote(n) for n in names],"BTC-USDT").approved
def test_live_guard():
    try: Settings(trading_mode="live")
    except ValueError: assert True
    else: assert False
