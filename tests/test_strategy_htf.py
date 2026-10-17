import pytest
from app.strategy import signal
from app.paper_worker import PaperWorker


def test_strategy_widen_sl_tp():
    features = {
        "close": 2500.0,
        "ema20": 2480.0,
        "ema50": 2450.0,
        "rsi": 60.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "atr": 10.0,  # 2 * atr = 20.0 < 2500 * 0.012 = 30.0
    }
    decision = signal(
        features,
        spread_pct=0.0001,
        max_spread_pct=0.001,
        min_stop_pct=0.012,
        risk_reward=2.0,
        tp1_pct=0.008,
        tp2_pct=0.016,
        tp3_pct=0.024,
    )
    assert decision["action"] == "buy"
    assert decision["stop_loss"] == 2500.0 - 30.0  # 2470.0 (1.2% SL)
    assert decision["take_profit"] == 2500.0 + 60.0  # 2560.0 (2.4% TP, RR 1:2)
    assert decision["take_profit_ladder"]["tp1"] == 2500.0 * 1.008
    assert decision["take_profit_ladder"]["tp2"] == 2500.0 * 1.016
    assert decision["take_profit_ladder"]["tp3"] == 2500.0 * 1.024


def test_strategy_htf_trend_filter_blocks_counter_trend():
    features_buy = {
        "close": 2500.0,
        "ema20": 2480.0,
        "ema50": 2450.0,
        "rsi": 60.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "atr": 10.0,
    }
    # BUY setup blocked when HTF is bearish
    blocked_buy = signal(
        features_buy,
        spread_pct=0.0001,
        max_spread_pct=0.001,
        htf_trend="bearish",
    )
    assert blocked_buy["action"] == "hold"
    assert blocked_buy["reason"] == "htf_trend_conflict_bearish"

    # BUY setup allowed when HTF is bullish
    allowed_buy = signal(
        features_buy,
        spread_pct=0.0001,
        max_spread_pct=0.001,
        htf_trend="bullish",
    )
    assert allowed_buy["action"] == "buy"

    features_sell = {
        "close": 2400.0,
        "ema20": 2420.0,
        "ema50": 2450.0,
        "rsi": 40.0,
        "macd": -2.0,
        "macd_signal": -1.0,
        "atr": 10.0,
    }
    # SELL setup blocked when HTF is bullish
    blocked_sell = signal(
        features_sell,
        spread_pct=0.0001,
        max_spread_pct=0.001,
        htf_trend="bullish",
    )
    assert blocked_sell["action"] == "hold"
    assert blocked_sell["reason"] == "htf_trend_conflict_bullish"

    # SELL setup allowed when HTF is bearish
    allowed_sell = signal(
        features_sell,
        spread_pct=0.0001,
        max_spread_pct=0.001,
        htf_trend="bearish",
    )
    assert allowed_sell["action"] == "sell"


def test_htf_trend_calculation():
    worker = object.__new__(PaperWorker)
    # Less than 30 candles -> neutral
    assert worker._htf_trend({"data": []}) == "neutral"
    assert worker._htf_trend(Exception("error")) == "neutral"

    # Generate 50 mock candle rows: [ts, open, high, low, close, vol, volCcy, volQuote, complete]
    candles_bullish = [[str(i), "100", "110", "90", str(100 + i * 2), "10", "1000", "1000", "1"] for i in range(50)]
    assert worker._htf_trend({"data": candles_bullish}) == "bullish"

    candles_bearish = [[str(i), "200", "210", "190", str(200 - i * 2), "10", "1000", "1000", "1"] for i in range(50)]
    assert worker._htf_trend({"data": candles_bearish}) == "bearish"


def test_strategy_guards_rejection_and_bollinger():
    features = {
        "close": 2500.0,
        "ema20": 2480.0,
        "ema50": 2450.0,
        "rsi": 60.0,
        "macd": 2.0,
        "macd_signal": 1.0,
        "atr": 10.0,
        "bb_upper": 2490.0,
        "bb_lower": 2430.0,
    }
    sig_bb = signal(features, 0.0001, 0.001)
    assert sig_bb["action"] == "hold"
    assert sig_bb["reason"] == "bollinger_upper_overbought"

    features_over = dict(features, bb_upper=2800.0, close=2650.0, ema20=2480.0)
    sig_over = signal(features_over, 0.0001, 0.001)
    assert sig_over["action"] == "hold"
    assert sig_over["reason"] == "over_extended_above_ema20"
