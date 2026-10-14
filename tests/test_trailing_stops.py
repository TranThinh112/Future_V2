import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.config import Settings, TradingMode
from app.paper_worker import PaperWorker


@pytest.mark.asyncio
async def test_manage_live_trailing_stops_long_tp1_and_tp2():
    settings = Settings(
        trading_mode=TradingMode.live,
        enable_live_trading=True,
        live_execution_enabled=True,
        live_dry_run=False,
        okx_read_only=False,
        live_execution_confirmation="I_UNDERSTAND_LIVE_TRADING_RISK",
        live_trailing_stop_enabled=True,
        breakeven_offset_pct=0.0015,
        tp1_pct=0.004,
        tp2_pct=0.010,
    )
    worker = PaperWorker(settings)
    worker.client = MagicMock()
    worker.audit = MagicMock()
    worker.audit.append = AsyncMock()

    # Mock pending algo orders on OKX
    worker.client.pending_algo_orders = AsyncMock(return_value={
        "code": "0",
        "data": [{
            "algoId": "algo_eth_123",
            "ordId": "ord_1",
            "instId": "ETH-USDT-SWAP",
            "posSide": "long",
            "slTriggerPx": "2550.05",
            "tpTriggerPx": "2596.23",
            "state": "live",
        }]
    })
    worker.client.amend_algo_order = AsyncMock(return_value={
        "code": "0",
        "data": [{"sCode": "0", "algoId": "algo_eth_123"}]
    })

    # Test 1: Price below TP1 -> No amend
    positions = {
        "ETH-USDT-SWAP": {
            "symbol": "ETH-USDT-SWAP",
            "side": "long",
            "entry_price": 2565.41,
            "mark_price": 2570.00,  # +0.18% < 0.4%
            "quantity": 0.39,
        }
    }
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 0
    plan = worker.live_trade_plans["ETH-USDT-SWAP"]
    assert plan["trailing_stage"] == 0
    assert plan["tp1"] == 2575.67
    assert plan["tp2"] == 2591.06

    # Test 2: Price hits TP1 (2576.00 >= 2575.67) -> Amend SL to Breakeven + fee offset (2565.41 * 1.0015 = 2569.26)
    expected_be_sl = round(2565.41 * (1 + 0.0015), 2)
    positions["ETH-USDT-SWAP"]["mark_price"] = 2576.00
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 1
    call_args = worker.client.amend_algo_order.call_args[0][0]
    assert call_args["algoId"] == "algo_eth_123"
    assert call_args["newSlTriggerPx"] == str(expected_be_sl)
    assert call_args["newTpTriggerPx"] == "2596.23"
    assert plan["trailing_stage"] == 1
    assert plan["current_sl"] == expected_be_sl

    # Test 3: Price hits TP2 (2592.00 >= 2591.06) -> Amend SL to TP1 (2575.67)
    positions["ETH-USDT-SWAP"]["mark_price"] = 2592.00
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 2
    call_args2 = worker.client.amend_algo_order.call_args[0][0]
    assert call_args2["newSlTriggerPx"] == "2575.67"
    assert plan["trailing_stage"] == 2
    assert plan["current_sl"] == 2575.67


@pytest.mark.asyncio
async def test_manage_live_trailing_stops_short_tp1_and_tp2():
    settings = Settings(
        trading_mode=TradingMode.live,
        enable_live_trading=True,
        live_execution_enabled=True,
        live_dry_run=False,
        okx_read_only=False,
        live_execution_confirmation="I_UNDERSTAND_LIVE_TRADING_RISK",
        live_trailing_stop_enabled=True,
        breakeven_offset_pct=0.0015,
        tp1_pct=0.004,
        tp2_pct=0.010,
    )
    worker = PaperWorker(settings)
    worker.client = MagicMock()
    worker.audit = MagicMock()
    worker.audit.append = AsyncMock()

    worker.client.pending_algo_orders = AsyncMock(return_value={
        "code": "0",
        "data": [{
            "algoId": "algo_btc_short",
            "ordId": "ord_2",
            "instId": "BTC-USDT-SWAP",
            "posSide": "short",
            "slTriggerPx": "85000.0",
            "tpTriggerPx": "82000.0",
            "state": "live",
        }]
    })
    worker.client.amend_algo_order = AsyncMock(return_value={
        "code": "0",
        "data": [{"sCode": "0", "algoId": "algo_btc_short"}]
    })

    # Short entry at 84000.0. TP1 = 84000 * 0.996 = 83664.0. TP2 = 84000 * 0.990 = 83160.0.
    positions = {
        "BTC-USDT-SWAP": {
            "symbol": "BTC-USDT-SWAP",
            "side": "short",
            "entry_price": 84000.0,
            "mark_price": 83800.0,
            "quantity": 0.12,
        }
    }
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 0

    # Price drops to 83600 <= 83664 (TP1) -> SL to Breakeven minus fee offset (84000 * (1 - 0.0015) = 83874.0)
    expected_be_sl = round(84000.0 * (1 - 0.0015), 1)
    positions["BTC-USDT-SWAP"]["mark_price"] = 83600.0
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 1
    call_args = worker.client.amend_algo_order.call_args[0][0]
    assert call_args["newSlTriggerPx"] == str(expected_be_sl)
    plan = worker.live_trade_plans["BTC-USDT-SWAP"]
    assert plan["trailing_stage"] == 1

    # Price drops to 83100 <= 83160 (TP2) -> SL to TP1 (83664.0)
    positions["BTC-USDT-SWAP"]["mark_price"] = 83100.0
    await worker._manage_live_trailing_stops(positions)
    assert worker.client.amend_algo_order.call_count == 2
    call_args2 = worker.client.amend_algo_order.call_args[0][0]
    assert call_args2["newSlTriggerPx"] == "83664.0"
    assert plan["trailing_stage"] == 2
