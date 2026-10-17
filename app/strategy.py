"""Deterministic paper-only signal. It is intentionally conservative."""


def signal(
    latest,
    spread_pct: float,
    max_spread_pct: float,
    min_stop_pct: float = 0.012,
    risk_reward: float = 2.0,
    tp1_pct: float = 0.008,
    tp1_close_pct: float = 0.30,
    tp2_pct: float = 0.016,
    tp2_close_pct: float = 0.30,
    tp3_pct: float = 0.024,
    tp3_close_pct: float = 0.40,
    htf_trend: str | None = None,
    candles=None,
) -> dict:
    required = ("ema20", "ema50", "rsi", "macd", "macd_signal", "atr", "close")
    if any(key not in latest or latest[key] is None for key in required):
        return {"action": "hold", "reason": "missing_features"}
    if spread_pct > max_spread_pct:
        return {"action": "hold", "reason": "spread_limit"}
    close = float(latest["close"])
    ema20 = float(latest["ema20"])
    ema50 = float(latest["ema50"])
    rsi = float(latest["rsi"])
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])
    atr = float(latest["atr"])
    stop_distance = max(2 * atr, close * min_stop_pct)
    target_distance = stop_distance * risk_reward
    ladder = {
        "tp1_pct": tp1_pct,
        "tp1_close_pct": tp1_close_pct,
        "tp2_pct": tp2_pct,
        "tp2_close_pct": tp2_close_pct,
        "tp3_pct": tp3_pct,
        "tp3_close_pct": tp3_close_pct,
    }

    # Guard: Detect recent strong bottom bounce to avoid shorting into V-shaped recovery
    if candles is not None and len(candles) >= 5:
        tail8 = candles.tail(8)
        lowest_tail = float(tail8["low"].astype(float).min())
        bounce_pct = (close - lowest_tail) / lowest_tail if lowest_tail > 0 else 0.0
        # If price has bounced > 0.8% off the 5-candle low or current candle has a long lower shadow (> 40% of range)
        last_c = candles.iloc[-1]
        c_open, c_high, c_low, c_close = float(last_c["open"]), float(last_c["high"]), float(last_c["low"]), float(last_c["close"])
        c_range = max(c_high - c_low, 1e-6)
        lower_shadow = min(c_open, c_close) - c_low
        has_strong_hammer = (lower_shadow / c_range) >= 0.40 and c_close > c_open
        if bounce_pct >= 0.006 or has_strong_hammer:
            recent_bounce_risk = True
        else:
            recent_bounce_risk = False
    else:
        recent_bounce_risk = False

    # Guard: Detect recent top rejection to avoid buying into top-drop
    if candles is not None and len(candles) >= 5:
        tail8 = candles.tail(8)
        highest_tail = float(tail8["high"].astype(float).max())
        drop_pct = (highest_tail - close) / highest_tail if highest_tail > 0 else 0.0
        last_c = candles.iloc[-1]
        c_open, c_high, c_low, c_close = float(last_c["open"]), float(last_c["high"]), float(last_c["low"]), float(last_c["close"])
        c_range = max(c_high - c_low, 1e-6)
        upper_shadow = c_high - max(c_open, c_close)
        has_shooting_star = (upper_shadow / c_range) >= 0.40 and c_close < c_open
        if drop_pct >= 0.006 or has_shooting_star:
            recent_drop_risk = True
        else:
            recent_drop_risk = False
    else:
        recent_drop_risk = False

    # Guard: Over-extension filter (prevent chasing when price is too far from EMA20)
    ema20_dist_pct = abs(close - ema20) / ema20 if ema20 > 0 else 0.0
    over_extended = ema20_dist_pct > 0.050

    # Guard: Bollinger Bands extreme filter
    bb_upper = float(latest.get("bb_upper", 0.0) or 0.0)
    bb_lower = float(latest.get("bb_lower", 0.0) or 0.0)
    bb_overbought = bb_upper > bb_lower and close >= bb_upper
    bb_oversold = bb_upper > bb_lower and close <= bb_lower

    if close > ema20 > ema50 and 52 <= rsi <= 68 and macd > macd_signal:
        if htf_trend == "bearish":
            return {"action": "hold", "reason": "htf_trend_conflict_bearish", "htf_trend": "bearish"}
        if over_extended:
            return {"action": "hold", "reason": "over_extended_above_ema20", "htf_trend": htf_trend or "aligned"}
        if bb_overbought:
            return {"action": "hold", "reason": "bollinger_upper_overbought", "htf_trend": htf_trend or "aligned"}
        if recent_drop_risk:
            return {"action": "hold", "reason": "recent_top_rejection_pullback", "htf_trend": htf_trend or "aligned"}
        return {
            "action": "buy",
            "reason": "trend_momentum",
            "stop_loss": float(close - stop_distance),
            "take_profit": float(close + target_distance),
            "take_profit_ladder": {
                "tp1": float(close * (1 + tp1_pct)),
                "tp2": float(close * (1 + tp2_pct)),
                "tp3": float(close * (1 + tp3_pct)),
                **ladder,
            },
            "htf_trend": htf_trend or "aligned",
        }
    if close < ema20 < ema50 and 32 <= rsi <= 48 and macd < macd_signal:
        if htf_trend == "bullish":
            return {"action": "hold", "reason": "htf_trend_conflict_bullish", "htf_trend": "bullish"}
        if over_extended:
            return {"action": "hold", "reason": "over_extended_below_ema20", "htf_trend": htf_trend or "aligned"}
        if bb_oversold:
            return {"action": "hold", "reason": "bollinger_lower_oversold", "htf_trend": htf_trend or "aligned"}
        if recent_bounce_risk:
            return {"action": "hold", "reason": "recent_bottom_bounce_rebound", "htf_trend": htf_trend or "aligned"}
        return {
            "action": "sell",
            "reason": "trend_momentum_short",
            "stop_loss": float(close + stop_distance),
            "take_profit": float(close - target_distance),
            "take_profit_ladder": {
                "tp1": float(close * (1 - tp1_pct)),
                "tp2": float(close * (1 - tp2_pct)),
                "tp3": float(close * (1 - tp3_pct)),
                **ladder,
            },
            "htf_trend": htf_trend or "aligned",
        }
    return {"action": "hold", "reason": "no_conservative_setup"}
