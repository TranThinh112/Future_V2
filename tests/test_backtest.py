import pytest

from backtests.engine import metrics_from_equity, out_of_sample_split, simulate_long_strategy


def test_backtest_metrics():
    r=metrics_from_equity([100,110,105],[5]); assert r.total_return==pytest.approx(.05) and r.win_rate==1

def test_out_of_sample_split_preserves_order():
    train, test = out_of_sample_split([1, 2, 3, 4, 5], train_fraction=.6)
    assert train == [1, 2, 3]
    assert test == [4, 5]

def test_simulate_long_strategy_models_costs_and_stops():
    result = simulate_long_strategy([100, 101, 96, 120], stop_loss_pct=.03, take_profit_pct=.50)
    assert result.turnover > 0
    assert result.fee_impact > 0
    assert result.total_return < 0
