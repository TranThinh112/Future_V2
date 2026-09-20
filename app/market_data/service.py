from dataclasses import dataclass

import pandas as pd


@dataclass
class Snapshot: symbol:str; timestamp_ms:int; bid:float; ask:float; last:float; stale:bool=False
def validate_snapshot(s: Snapshot, now_ms: int, max_age_ms=60000):
    return (not s.stale and s.timestamp_ms>0 and now_ms-s.timestamp_ms<=max_age_ms and 0<s.bid<=s.ask and s.last>0)

def snapshot_quality(s: Snapshot, now_ms: int, max_age_ms=60000, max_spread_pct=.001):
    if s.stale or s.timestamp_ms <= 0 or now_ms - s.timestamp_ms > max_age_ms:
        return "bad", ["stale_data"]
    if not (0 < s.bid <= s.ask and s.last > 0):
        return "bad", ["invalid_price"]
    mid = (s.bid + s.ask) / 2
    spread_pct = (s.ask - s.bid) / mid if mid else 1
    if spread_pct > max_spread_pct:
        return "degraded", ["wide_spread"]
    if not (s.bid * .95 <= s.last <= s.ask * 1.05):
        return "degraded", ["abnormal_last_price"]
    return "good", []

def hold_on_bad_snapshot(symbol: str, quality: str, reasons: list[str]):
    return {
        "symbol": symbol,
        "action": "hold",
        "data_quality": quality,
        "reason_codes": reasons or ["invalid_market_data"],
    }

def candles_frame(rows: list[list[str]]) -> pd.DataFrame:
    """Normalize OKX reverse-chronological candle rows without retaining incomplete candles."""
    columns = ["timestamp", "open", "high", "low", "close", "volume", "volume_ccy", "volume_quote", "complete"]
    frame = pd.DataFrame(rows, columns=columns[:len(rows[0])] if rows else columns)
    if frame.empty:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
    frame = frame[frame["complete"].astype(str) == "1"].copy()
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["timestamp"] = pd.to_datetime(pd.to_numeric(frame["timestamp"]), unit="ms", utc=True)
    return frame.dropna().sort_values("timestamp").drop_duplicates("timestamp")

def missing_candles(frame: pd.DataFrame, expected_interval_ms: int) -> list[str]:
    if frame.empty or len(frame) < 2:
        return []
    timestamps = pd.to_datetime(frame["timestamp"], utc=True).sort_values()
    gaps = timestamps.diff().dropna()
    return [str(ts) for ts, gap in zip(timestamps.iloc[1:], gaps) if gap.total_seconds() * 1000 > expected_interval_ms * 1.5]

def abnormal_close_prices(frame: pd.DataFrame, max_jump_pct=.20) -> list[str]:
    if frame.empty or "close" not in frame:
        return []
    closes = pd.to_numeric(frame["close"], errors="coerce").dropna()
    jumps = closes.pct_change().abs()
    return [str(frame.iloc[i]["timestamp"]) for i, jump in enumerate(jumps) if pd.notna(jump) and jump > max_jump_pct]

def persist_snapshot(repository, snapshot: Snapshot):
    repository.append("market_snapshot", {
        "symbol": snapshot.symbol,
        "timestamp_ms": snapshot.timestamp_ms,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "last": snapshot.last,
        "stale": snapshot.stale,
    })
