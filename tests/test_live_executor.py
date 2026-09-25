from types import SimpleNamespace

import pytest

from app.config import TradingMode
from app.execution.live import CONFIRMATION, LiveFuturesExecutor


def settings(**overrides):
    values = {
        "trading_mode": TradingMode.live,
        "enable_live_trading": True,
        "live_execution_enabled": True,
        "live_execution_confirmation": CONFIRMATION,
        "live_dry_run": True,
        "live_margin_mode": "isolated",
        "live_max_leverage": 20,
        "target_margin_usdt": 5.0,
        "target_leverage": 20,
        "okx_read_only": False,
        "okx_demo_trading": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def proposal(action="buy"):
    return {
        "symbol": "BTC-USDT",
        "entry_price": 84000.0,
        "stop_loss": 83496.0 if action == "buy" else 84504.0,
        "take_profit_ladder": {"tp1": 84336.0},
    }


def test_live_executor_returns_dry_run_plan_without_order_submission():
    executor = LiveFuturesExecutor(object(), settings())
    result = __import__("asyncio").run(executor.submit(proposal(), {"approved": True, "action": "buy"}))
    assert result["status"] == "dry_run"
    assert result["plan"]["instId"] == "BTC-USDT-SWAP"
    assert result["plan"]["target_notional_usdt"] == 100.0
    assert result["plan"]["posSide"] == "long"


def test_live_executor_fails_closed_without_confirmation():
    executor = LiveFuturesExecutor(object(), settings(live_execution_confirmation=""))
    with pytest.raises(PermissionError, match="live_confirmation_missing"):
        executor.plan(proposal(), {"approved": True, "action": "buy"})


def test_live_executor_rejects_unapproved_or_unsafe_orders():
    executor = LiveFuturesExecutor(object(), settings())
    with pytest.raises(ValueError, match="consensus_not_approved"):
        executor.plan(proposal(), {"approved": False, "action": "buy"})
    with pytest.raises(ValueError, match="invalid_protective_stop"):
        executor.plan({**proposal(), "stop_loss": 85000.0}, {"approved": True, "action": "buy"})
