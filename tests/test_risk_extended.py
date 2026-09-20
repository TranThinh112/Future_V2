from app.config import Settings
from app.risk.engine import check_trade
from app.risk.state import RiskState


def test_risk_refuses_cooldown_and_data_failure():
    result=check_trade(equity=10000,entry=100,stop_loss=90,current_exposure=0,settings=Settings(),cooling_down=True,api_healthy=False)
    assert result.status=="REJECTED" and "stop_loss_cooldown" in result.reasons
def test_risk_state():
    s=RiskState(100,100); assert s.drawdown(90)==.1 and s.daily_loss(90)==.1
