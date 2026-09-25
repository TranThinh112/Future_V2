"""Deterministic paper-only signal. It is intentionally conservative."""


def signal(latest, spread_pct: float, max_spread_pct: float) -> dict:
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
    if close > ema20 > ema50 and 52 <= rsi <= 68 and macd > macd_signal:
        return {
            "action": "buy",
            "reason": "trend_momentum",
            "stop_loss": float(close - 2 * atr),
            "take_profit": float(close + 3 * atr),
        }
    if close < ema20 < ema50 and 32 <= rsi <= 48 and macd < macd_signal:
        return {
            "action": "sell",
            "reason": "trend_momentum_short",
            "stop_loss": float(close + 2 * atr),
            "take_profit": float(close - 3 * atr),
        }
    return {"action": "hold", "reason": "no_conservative_setup"}
