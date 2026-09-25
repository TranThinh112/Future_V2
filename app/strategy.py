"""Deterministic paper-only signal. It is intentionally conservative."""


def signal(
    latest,
    spread_pct: float,
    max_spread_pct: float,
    min_stop_pct: float = 0.006,
    risk_reward: float = 2.0,
    tp1_pct: float = 0.004,
    tp1_close_pct: float = 0.30,
    tp2_pct: float = 0.010,
    tp2_close_pct: float = 0.30,
    tp3_pct: float = 0.020,
    tp3_close_pct: float = 0.40,
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
    if close > ema20 > ema50 and 52 <= rsi <= 68 and macd > macd_signal:
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
        }
    if close < ema20 < ema50 and 32 <= rsi <= 48 and macd < macd_signal:
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
        }
    return {"action": "hold", "reason": "no_conservative_setup"}
