from app.execution.paper import PaperBroker
from app.strategy import signal


def test_paper_stop_exit():
    b=PaperBroker(); assert b.buy("BTC-USDT",100,1,90,120); assert b.mark("BTC-USDT",89)["reason"]=="stop_or_target"
def test_strategy_fails_closed(): assert signal({},0,.001)["action"]=="hold"
def test_paper_snapshot_restores():
    b=PaperBroker(); b.buy("BTC-USDT",100,1,90,120); restored=PaperBroker.restore(b.snapshot()); assert "BTC-USDT" in restored.positions


def test_paper_context_helpers_include_missing_domains():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.settings = type("Settings", (), {"max_position_pct": 0.1})()
    worker.close_history = {}
    assert worker._orderbook_context({}, 100)["data_quality"] == "missing"
    context = worker._portfolio_context({"BTC-USDT": 100.0})
    assert context["positions"] == {}
    assert context["data_quality"] == "good"
    assert context["correlation"]["data_quality"] == "unavailable"
    assert context["execution"]["count"] == 0


def test_regime_and_structure_contexts():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    regime = worker._regime_context({
        "close": 120.0, "ema20": 110.0, "ema50": 100.0, "ema200": 90.0,
        "rsi": 65.0, "macd": 1.0, "macd_signal": 0.5, "atr": 2.0, "volatility": 0.0008,
    })
    assert regime["trend"] == "strong_uptrend"
    assert regime["momentum"] == "bullish"
    assert regime["volatility"] == "low"
    assert regime["data_quality"] == "good"
    assert worker._regime_context({})["data_quality"] == "missing"

    import pandas as pd

    frame = pd.DataFrame({
        "high": [100.0, 105.0, 103.0], "low": [90.0, 92.0, 95.0],
        "close": [95.0, 104.0, 100.0], "volume": [2.0, 3.0, 5.0],
    })
    snapshot = type("Snapshot", (), {"last": 100.0})()
    structure = worker._structure_context(frame, snapshot, {"bb_upper": 110.0, "bb_lower": 90.0})
    assert structure["data_quality"] == "good"
    assert structure["support"] == 90.0
    assert structure["resistance"] == 105.0
    assert structure["bollinger_position_pct"] == 0.5
    assert structure["vwap"] is not None
    assert worker._structure_context(None, snapshot, {})["data_quality"] == "missing"


def test_correlation_uses_close_history():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.close_history = {"BTC-USDT": [100.0 + i for i in range(40)], "ETH-USDT": [200.0 + 2 * i for i in range(40)]}
    correlation = worker._correlation()
    assert correlation["data_quality"] == "good"
    assert correlation["value"] == 1.0
    assert correlation["pair"] == "BTC-USDT_ETH-USDT"
    worker.close_history = {"BTC-USDT": [1.0, 1.0, 1.0]}
    assert worker._correlation()["data_quality"] == "unavailable"


def test_realized_pnl_and_proposal_context():
    from app.paper_worker import PaperWorker

    fills = [
        {"symbol": "BTC-USDT", "side": "buy", "price": 100.0, "quantity": 1.0, "fee": 0.0},
        {"symbol": "BTC-USDT", "side": "sell", "price": 110.0, "quantity": 1.0, "fee": 0.0},
    ]
    assert PaperWorker._realized_pnl(fills) == 10.0
    assert PaperWorker._realized_pnl([{"bad": "row"}]) is None

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.settings = type("Settings", (), {"max_position_pct": 0.1, "risk_per_trade_pct": 0.005, "enable_paper_execution": False})()
    snapshot = type("Snapshot", (), {"last": 100.0})()
    proposal = worker._proposal_context(snapshot, {"action": "buy", "reason": "trend_momentum", "stop_loss": 95.0, "take_profit": 115.0}, 10000.0, 0.0002)
    assert proposal["data_quality"] == "good"
    assert proposal["risk_reward_ratio"] == 3.0
    assert proposal["quantity"] == 10.0
    assert proposal["position_pct"] == 0.1
    assert worker._proposal_context(snapshot, {"action": "hold", "reason": "no_conservative_setup"}, 10000.0, None)["data_quality"] == "not_applicable"
