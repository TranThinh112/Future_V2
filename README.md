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
