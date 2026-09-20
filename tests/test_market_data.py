from app.market_data.service import (
    Snapshot,
    abnormal_close_prices,
    candles_frame,
    hold_on_bad_snapshot,
    missing_candles,
    persist_snapshot,
    snapshot_quality,
)
from app.storage.repository import AuditRepository


def test_candles_frame_discards_incomplete_and_sorts():
    rows=[["2","2","3","1","2","5","0","0","1"],["1","1","2","0","1","4","0","0","1"],["3","1","2","0","1","4","0","0","0"]]
    data=candles_frame(rows)
    assert len(data)==2 and data.iloc[0].close==1

def test_snapshot_quality_fails_closed():
    quality, reasons = snapshot_quality(Snapshot("BTC-USDT", 1, 100, 105, 130), now_ms=2, max_spread_pct=.001)
    assert quality == "degraded"
    assert "wide_spread" in reasons
    hold = hold_on_bad_snapshot("BTC-USDT", quality, reasons)
    assert hold["action"] == "hold"

def test_missing_candle_and_abnormal_price_detection():
    rows=[
        ["60000","1","1","1","1","5","0","0","1"],
        ["180000","1","2","1","2","5","0","0","1"],
        ["240000","2","5","2","5","5","0","0","1"],
    ]
    frame = candles_frame(rows)
    assert missing_candles(frame, expected_interval_ms=60000)
    assert abnormal_close_prices(frame, max_jump_pct=.5)

def test_persist_snapshot(tmp_path):
    repo = AuditRepository(str(tmp_path / "audit.db"))
    persist_snapshot(repo, Snapshot("ETH-USDT", 10, 1, 2, 1.5))
    latest = repo.latest_by_symbol("market_snapshot")
    assert latest["ETH-USDT"]["payload"]["last"] == 1.5
    repo.close()
