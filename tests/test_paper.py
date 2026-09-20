from app.execution.paper import PaperBroker
from app.strategy import signal


def test_paper_stop_exit():
    b=PaperBroker(); assert b.buy("BTC-USDT",100,1,90,120); assert b.mark("BTC-USDT",89)["reason"]=="stop_or_target"
def test_strategy_fails_closed(): assert signal({},0,.001)["action"]=="hold"
def test_paper_snapshot_restores():
    b=PaperBroker(); b.buy("BTC-USDT",100,1,90,120); restored=PaperBroker.restore(b.snapshot()); assert "BTC-USDT" in restored.positions
