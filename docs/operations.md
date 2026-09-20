# Operations

## Local startup

1. Create a Python 3.12 virtual environment.
2. Install dependencies with `pip install -e ".[dev]"`.
3. Copy `.env.example` to `.env`.
4. Keep `TRADING_MODE=paper` unless you are deliberately testing `backtest` or `okx_demo`.
5. Start infrastructure with `docker compose up -d postgres redis`.
6. Run migrations with `python -m app.storage.migrate`.
7. Start the API with `python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000`.

## Monitoring

Use `/health` for liveness, `/metrics` for Prometheus scraping, `/api/status` for the latest worker state, and `/api/events` for recent audit events. OpenTelemetry is optional and activates when `OTEL_EXPORTER_OTLP_ENDPOINT` is configured.

## Emergency controls

Use `/api/kill-switch` to stop the paper worker. For demo/live-capable deployments, disable the process, revoke OKX keys if needed, and leave `ENABLE_LIVE_TRADING=false` until the incident is reviewed.

## Mode policy

Default mode is `paper`. `live` requires `ENABLE_LIVE_TRADING=true`, OKX credentials, trade-only key permissions, deterministic risk approval, and explicit operator confirmation. GPT agent output is never sufficient to place or modify a live order.
