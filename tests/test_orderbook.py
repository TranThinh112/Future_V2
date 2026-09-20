from app.market_data.orderbook import estimated_slippage, spread_pct


def test_orderbook_metrics():
    assert spread_pct(99,100)==.01
    assert round(estimated_slippage([[100,1],[101,1]],2),4)==.005
