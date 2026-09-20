# Railway Deploy

## Safety defaults

Set these Railway variables before running the service:

```env
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
ENABLE_PAPER_EXECUTION=false
ENABLE_AI_ADVISORY=true
AI_ADVISORY_ON_HOLD=false
AI_ADVISORY_COOLDOWN_SECONDS=900
OKX_DEMO_TRADING=false
```

`OPENAI_API_KEY`, `OKX_API_KEY`, `OKX_SECRET_KEY`, and `OKX_PASSPHRASE` must be configured as Railway service variables. Do not commit `.env`.

## Runtime

Railway runs:

```bash
python -m uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Healthcheck:

```text
/health
```

The current runtime stores audit data in local SQLite (`crypto.db`) and paper checkpoints in `paper_state.json`. Railway ephemeral storage can be reset on redeploy; use PostgreSQL wiring before relying on historical audit retention.
