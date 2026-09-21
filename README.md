# Crypto Agent Bot

Safety-first OKX spot bot for BTC-USDT and ETH-USDT. Default mode is `paper`; GPT proposes analysis only and deterministic risk remains authoritative.

## Quickstart

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
pytest
uvicorn app.api.main:app --reload
```

Never place secrets in source control. Live mode requires `ENABLE_LIVE_TRADING=true`, credentials with trade-only permission, and a separate operator confirmation gate; development does not enable it.

The included `.env` contains empty placeholders only. Add your own credentials locally; it is ignored by git.

## Configuration

Copy `.env.example` to `.env` and keep `TRADING_MODE=paper` while developing. The only supported spot instruments in this phase are `BTC-USDT` and `ETH-USDT`. The app validates live mode at startup and refuses to start in `live` unless `ENABLE_LIVE_TRADING=true` and OKX credentials are present.

Required local services for the production-like path:

```powershell
docker compose up -d postgres redis
python -m app.storage.migrate
```

## Backtest

```powershell
python -m pytest tests/test_backtest.py
```

The backtest engine models fees, spread, slippage, partial fills, stops, targets, latency, initial capital, and out-of-sample metrics. It must not use look-ahead data.

## Local paper worker

Starting the API in `paper` mode also starts the public-data worker. It polls OKX ticker/candles for the two allowed spot pairs, calculates features, applies conservative deterministic paper signals, persists audit events in `crypto.db`, and exposes `/api/events`, `/api/portfolio`, `/health`, and `/metrics`. It never sends exchange orders.

```powershell
docker compose up -d postgres redis
python -m app.storage.migrate
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

## OKX demo and live

For OKX demo, set `TRADING_MODE=okx_demo` and `OKX_DEMO_TRADING=true` with demo credentials. For live, use trade-only API keys with no withdrawal permission, set `TRADING_MODE=live`, and set `ENABLE_LIVE_TRADING=true`. Live execution still goes through deterministic risk checks and the operator gate; GPT output alone cannot enable or place real orders.

Useful endpoints:

- `/health` for process health.
- `/metrics` for Prometheus metrics.
- `/api/status` for worker status.
- `/api/kill-switch` to stop the paper worker.
"# Future_V2" 


## Durable audit storage

When `DATABASE_URL` starts with `postgresql`, audit events are stored in
PostgreSQL instead of local `crypto.db`. This preserves paper ticks, agent
decisions, consensus, token usage, costs, and setup history across Railway
redeploys. For Railway, use service references such as
`${{Postgres.DATABASE_URL}}`; do not use `localhost`.


By default, routine `paper_tick` audit rows are sampled every 300 seconds per
symbol to control database growth. Buy/sell signals, errors, fills, AI decisions,
and consensus are still recorded immediately. Detailed `paper_tick` rows are
retained for 30 days and aggregated into `market_scan_hourly` for longer-term
reporting.

## Agent context and news

Every AI call sends each of the eight agents the snapshot it needs: market
(last/bid/ask/mid/spread/24h volume), technical features (EMA20/50/200, RSI,
MACD, ATR, Bollinger, volatility, volume z-score), a derived `regime`
(trend/momentum/volatility/atr_pct/rsi_zone), `structure` (VWAP deviation,
Bollinger position, recent support/resistance and distance to each), order book
depth/imbalance/estimated slippage, `portfolio` (cash, equity, positions with
entry/mark/uPnL/stop-target distance/age, exposure, concentration, BTC-ETH
return correlation, execution fills and realized PnL), `risk` budgets, and the
deterministic `proposal` under review (action, entry, stop, target, risk/reward,
size, slippage). The snapshot is stored with each `agent_decision` audit row as
`input_context`.

`correlation` needs at least 30 aligned closes for two symbols, so it reports
`data_quality: unavailable` until both symbols have been scanned; `regime` and
`structure` report `missing` if there are not enough candles.

LUMEN additionally needs news sentiment. Set `NEWS_PROVIDER_URL` to a JSON
endpoint that accepts `q`/`symbol`/`limit`/`lookback_minutes` and returns either
a list or `{"articles"|"news"|"data": [...]}` items with `title`, `summary`,
`source`, `published_at`, `url`, and an optional `sentiment`. Set
`NEWS_API_KEY` if the provider needs a bearer token. `NEWS_LOOKBACK_MINUTES` and
`NEWS_MAX_ITEMS` bound the window and item count.

When no provider is configured or the provider fails, the snapshot marks news
as `data_quality: unavailable` and LUMEN must respond `HOLD` instead of
inventing headlines. All other agents keep working; the other domains are never
silently faked.
