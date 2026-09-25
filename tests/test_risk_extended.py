from app.config import Settings
from app.risk.engine import check_trade
from app.risk.state import RiskState


def test_risk_refuses_cooldown_and_data_failure():
    result=check_trade(equity=10000,entry=100,stop_loss=90,current_exposure=0,settings=Settings(),cooling_down=True,api_healthy=False)
    assert result.status=="REJECTED" and "stop_loss_cooldown" in result.reasons
def test_risk_state():
    s=RiskState(100,100); assert s.drawdown(90)==.1 and s.daily_loss(90)==.1
def test_risk_state_rebases_to_funded_account():
    from datetime import UTC, datetime
    s=RiskState(10000,10000)
    assert round(s.drawdown(21.9),5)==0.99781 and round(s.daily_loss(21.9),5)==0.99781
    s.rebase(21.9,"exchange",now=datetime(2026,9,25,12,0,tzinfo=UTC))
    assert s.drawdown(21.9)==0 and s.daily_loss(21.9)==0 and s.source=="exchange"
    s.rebase(21.0,"exchange",now=datetime(2026,9,25,13,0,tzinfo=UTC))
    assert round(s.drawdown(21.0),4)==round((21.9-21.0)/21.9,4) and round(s.daily_loss(21.0),4)==0.0411
    s.rebase(20.0,"exchange",now=datetime(2026,9,26,1,0,tzinfo=UTC))
    assert s.daily_loss(20.0)==0 and round(s.drawdown(20.0),4)==round((21.9-20.0)/21.9,4)
def test_risk_state_rebase_ignores_bad_equity():
    s=RiskState(100,100)
    for bad in (None,"x",0,-5):
        s.rebase(bad,"exchange")
    assert s.peak_equity==100 and s.daily_start_equity==100 and s.source=="paper"
