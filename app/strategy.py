"""Deterministic paper-only signal. It is intentionally conservative."""
def signal(latest, spread_pct: float, max_spread_pct: float) -> dict:
    required = ("ema20", "ema50", "rsi", "macd", "macd_signal", "atr", "close")
    if any(key not in latest or latest[key] is None for key in required):
        return {"action":"hold","reason":"missing_features"}
    if spread_pct > max_spread_pct:
        return {"action":"hold","reason":"spread_limit"}
    if latest["close"] > latest["ema20"] > latest["ema50"] and 52 <= latest["rsi"] <= 68 and latest["macd"] > latest["macd_signal"]:
        return {"action":"buy","reason":"trend_momentum","stop_loss":float(latest["close"]-2*latest["atr"]),"take_profit":float(latest["close"]+3*latest["atr"])}
    return {"action":"hold","reason":"no_conservative_setup"}
