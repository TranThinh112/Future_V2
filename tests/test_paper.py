import asyncio

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
    worker.settings = type("Settings", (), {"max_position_pct": 0.1, "position_size_headroom": 0.95, "risk_per_trade_pct": 0.005, "enable_paper_execution": False})()
    snapshot = type("Snapshot", (), {"last": 100.0})()
    funded = {"equity": 10000.0, "cash": 10000.0, "available_cash": 10000.0}
    proposal = worker._proposal_context(snapshot, {"action": "buy", "reason": "trend_momentum", "stop_loss": 95.0, "take_profit": 115.0}, funded, 0.0002)
    assert proposal["data_quality"] == "good"
    assert proposal["risk_reward_ratio"] == 3.0
    assert proposal["quantity"] == 9.5
    assert proposal["position_pct"] == 0.095
    assert worker._proposal_context(snapshot, {"action": "hold", "reason": "no_conservative_setup"}, funded, None)["data_quality"] == "not_applicable"

def test_proposal_context_sizes_against_funded_account():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.settings = type("Settings", (), {"max_position_pct": 0.1, "position_size_headroom": 0.95, "risk_per_trade_pct": 0.005, "enable_paper_execution": False})()
    snapshot = type("Snapshot", (), {"last": 84000.0})()
    account = {"equity": 15.45, "cash": 18.86, "available_cash": 6.55}
    proposal = worker._proposal_context(snapshot, {"action": "buy", "reason": "trend_momentum", "stop_loss": 83900.0, "take_profit": 84200.0}, account, 0.0)
    assert proposal["notional"] <= account["available_cash"]
    assert proposal["position_pct"] < worker.settings.max_position_pct
    risk = {"data_quality": "good", "api_healthy": True, "liquidity_ok": True}
    assert worker._ai_precheck_reason(proposal, account, {"data_quality": "good"}, risk) == ""

def test_risk_context_reports_funded_drawdown_not_paper_ledger():
    from app.paper_worker import PaperWorker
    from app.risk.state import RiskState

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.risk_state = RiskState(worker.broker.cash, worker.broker.cash)
    worker.exchange_portfolio = {"equity": 21.9, "available_cash": 12.0, "positions": {}, "position_count": 0}
    worker.settings = type("Settings", (), {
        "max_position_pct": 0.1, "position_size_headroom": 0.95, "risk_per_trade_pct": 0.005,
        "max_total_exposure_pct": 0.3, "max_slippage_pct": 0.002,
    })()
    before = worker._risk_context(21.9, "BTC-USDT", 0.0, 0.0)
    assert before["drawdown_pct"] > 0.9 and before["daily_loss_pct"] > 0.9
    worker._rebase_risk_state()
    after = worker._risk_context(21.9, "BTC-USDT", 0.0, 0.0)
    assert after["drawdown_pct"] == 0 and after["daily_loss_pct"] == 0

def test_portfolio_context_prefers_read_only_exchange_snapshot():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.settings = type("Settings", (), {"max_position_pct": 0.1})()
    worker.close_history = {}
    worker.exchange_portfolio = {
        "cash": 4200.0,
        "equity": 10000.0,
        "positions": {"BTC-USDT-SWAP": {"quantity": -0.1, "unrealized_pnl": 12.5}},
        "position_count": 1,
        "source": "okx_private_account_read_only",
        "data_quality": "good",
    }
    context = worker._portfolio_context({"BTC-USDT": 100.0})
    assert context["position_count"] == 1
    assert context["source"] == "okx_private_account_read_only"
    assert context["cash"] == 4200.0


def test_exchange_sync_skips_without_credentials():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.interval = 30
    worker.exchange_portfolio = None
    worker.exchange_sync_error = ""
    worker.exchange_sync_at = 0.0
    worker.settings = type("Settings", (), {"okx_account_sync": True, "okx_api_key": "", "okx_secret_key": "", "okx_passphrase": ""})()
    assert asyncio.run(worker._sync_exchange_portfolio(force=True)) is None
    assert worker.exchange_sync_error == "okx_account_credentials_missing"

def test_ai_precheck_blocks_unfunded_buy_without_agent_calls():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.settings = type("Settings", (), {"ai_precheck_enabled": True, "max_position_pct": 0.1, "openai_model": "gpt-test"})()
    proposal = {"action": "buy", "data_quality": "good", "notional": 100.0, "position_pct": 0.05, "max_position_pct": 0.1}
    portfolio = {"available_cash": 1.0, "cash": 1.0}
    orderbook = {"data_quality": "good"}
    risk = {"data_quality": "good", "api_healthy": True, "liquidity_ok": True}
    assert worker._ai_precheck_reason(proposal, portfolio, orderbook, risk) == "proposal_notional_exceeds_available_cash"


def test_ai_precheck_allows_funded_buy():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.settings = type("Settings", (), {"ai_precheck_enabled": True, "max_position_pct": 0.1, "openai_model": "gpt-test"})()
    proposal = {"action": "buy", "data_quality": "good", "notional": 1.0, "position_pct": 0.05, "max_position_pct": 0.1}
    portfolio = {"available_cash": 10.0, "cash": 10.0}
    orderbook = {"data_quality": "good"}
    risk = {"data_quality": "good", "api_healthy": True, "liquidity_ok": True}
    assert worker._ai_precheck_reason(proposal, portfolio, orderbook, risk) == ""


def test_strategy_generates_sell_signal():
    from app.strategy import signal
    features = {
        "close": 100.0,
        "ema20": 105.0,
        "ema50": 110.0,
        "rsi": 40.0,
        "macd": -1.5,
        "macd_signal": -0.5,
        "atr": 2.0,
    }
    sig = signal(features, 0.0001, 0.001)
    assert sig["action"] == "sell"
    assert sig["reason"] == "trend_momentum_short"
    assert sig["stop_loss"] == 104.0
    assert sig["take_profit"] == 92.0


def test_proposal_context_sizes_sell_correctly():
    from app.paper_worker import PaperWorker

    worker = object.__new__(PaperWorker)
    worker.broker = PaperBroker()
    worker.settings = type("Settings", (), {
        "max_position_pct": 0.1,
        "position_size_headroom": 0.95,
        "risk_per_trade_pct": 0.005,
        "enable_paper_execution": False,
    })()
    snapshot = type("Snapshot", (), {"last": 100.0})()
    funded = {"equity": 1000.0, "cash": 500.0, "available_cash": 500.0}
    decision = {"action": "sell", "reason": "trend_momentum_short", "stop_loss": 105.0, "take_profit": 90.0}
    proposal = worker._proposal_context(snapshot, decision, funded, 0.0)
    assert proposal["action"] == "sell"
    assert proposal["data_quality"] == "good"
    assert proposal["risk_reward_ratio"] == 2.0
    assert proposal["quantity"] == 0.95
    assert proposal["notional"] == 95.0
    assert round(proposal["position_pct"], 4) == 0.095
