import math
from dataclasses import dataclass


@dataclass
class BacktestResult:
    total_return:float; max_drawdown:float; sharpe:float; sortino:float; win_rate:float; profit_factor:float; average_trade:float; turnover:float; fee_impact:float
def run(prices, initial_cash=10000, fee=0.001):
    if not prices: return BacktestResult(0,0,0,0,0,0,0,0,0)
    ret=prices[-1]/prices[0]-1-fee*2; return BacktestResult(ret, min(0,ret), 0,0, 1 if ret>0 else 0, max(0, ret), ret, 1, fee*2)

def metrics_from_equity(equity, trades, turnover=0, fee_impact=0):
    if len(equity)<2: return BacktestResult(0,0,0,0,0,0,0,turnover,fee_impact)
    returns=[equity[i]/equity[i-1]-1 for i in range(1,len(equity)) if equity[i-1]]; peak=equity[0]; drawdown=0
    for value in equity: peak=max(peak,value); drawdown=min(drawdown,(value-peak)/peak)
    mean=sum(returns)/len(returns); sd=math.sqrt(sum((r-mean)**2 for r in returns)/len(returns)); downside=math.sqrt(sum(min(0,r)**2 for r in returns)/len(returns))
    wins=[p for p in trades if p>0]; losses=[p for p in trades if p<0]
    return BacktestResult(equity[-1]/equity[0]-1,drawdown,mean/sd*math.sqrt(365) if sd else 0,mean/downside*math.sqrt(365) if downside else 0,len(wins)/len(trades) if trades else 0,sum(wins)/abs(sum(losses)) if losses else 0,sum(trades)/len(trades) if trades else 0,turnover,fee_impact)

def buy_and_hold(prices, initial_cash=10000, fee=.001):
    """No-look-ahead baseline: buy first observed price and sell last observed price."""
    return run(list(prices), initial_cash, fee)

def out_of_sample_split(rows, train_fraction=.7):
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction_must_be_between_0_and_1")
    index = max(1, min(len(rows) - 1, int(len(rows) * train_fraction)))
    return rows[:index], rows[index:]

def simulate_long_strategy(prices, *, initial_cash=10000, fee=.001, spread=.0005, slippage=.0005, partial_fill_pct=1.0, stop_loss_pct=.02, take_profit_pct=.04, latency_bars=0):
    prices = list(prices)
    if not prices:
        return metrics_from_equity([], [])
    entry_index = min(latency_bars, len(prices) - 1)
    entry_price = prices[entry_index] * (1 + spread / 2 + slippage)
    fill_pct = max(0, min(1, partial_fill_pct))
    quantity = (initial_cash * fill_pct * (1 - fee)) / entry_price if entry_price else 0
    cash = initial_cash - quantity * entry_price * (1 + fee)
    equity = []
    exit_price = prices[-1] * (1 - spread / 2 - slippage)
    exit_index = len(prices) - 1
    for index, price in enumerate(prices):
        marked = cash + quantity * price
        equity.append(marked)
        if index <= entry_index:
            continue
        if price <= entry_price * (1 - stop_loss_pct) or price >= entry_price * (1 + take_profit_pct):
            exit_price = price * (1 - spread / 2 - slippage)
            exit_index = index
            equity[-1] = cash + quantity * exit_price * (1 - fee)
            break
    final_equity = cash + quantity * exit_price * (1 - fee)
    if exit_index == len(prices) - 1:
        equity[-1] = final_equity
    pnl = final_equity - initial_cash
    turnover = (quantity * entry_price + quantity * exit_price) / initial_cash if initial_cash else 0
    fee_impact = fee * turnover
    return metrics_from_equity(equity, [pnl], turnover=turnover, fee_impact=fee_impact)
