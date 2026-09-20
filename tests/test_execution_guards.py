from app.config import TradingMode
from app.execution.guards import assert_execution_mode


def test_live_needs_confirmation():
    try: assert_execution_mode(TradingMode.live,True,False)
    except PermissionError: assert True
    else: assert False
