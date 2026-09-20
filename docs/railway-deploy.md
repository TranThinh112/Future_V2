# Railway Deploy

## Safety defaults

Set these Railway variables before running the service. Enter them in Railway after connecting the GitHub repository.

```env
TRADING_MODE=paper
ENABLE_LIVE_TRADING=false
ENABLE_PAPER_EXECUTION=false
ENABLE_AI_ADVISORY=true
AI_ADVISORY_ON_HOLD=false
AI_ADVISORY_COOLDOWN_SECONDS=900
OKX_DEMO_TRADING=false
```

Required secret variables:

```env
OKX_API_KEY=
OKX_SECRET_KEY=
OKX_PASSPHRASE=
OPENAI_API_KEY=
```

Required runtime variables:

```env
OPENAI_MODEL=gpt-5.4-mini
DATABASE_URL=<Railway PostgreSQL connection string>
REDIS_URL=<Railway Redis connection string>
AI_INPUT_COST_PER_MILLION=<model input price in USD per 1M tokens>
AI_OUTPUT_COST_PER_MILLION=<model output price in USD per 1M tokens>
```

Do not commit `.env` or put real secret values in `.env.example`.

AI usage is recorded in each `agent_decision` event with input/output/total
tokens, attempts, latency, and estimated cost. Each `consensus` event includes
the totals for all agents in that call. Set the two AI cost variables using the
current official pricing for the selected model; leaving them at `0.0` records
tokens but reports zero estimated cost.

## Runtime

Railway runs:

```bash
python -m uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Healthcheck:

```text
/health
```

Deployment verification:

```text
/api/runtime
```

This read-only endpoint reports the running app version, Railway commit/deployment
identifiers, safe runtime mode, and whether token/cost audit logging is present.
It never returns API keys or other secrets.

The current runtime stores audit data in local SQLite (`crypto.db`) and paper checkpoints in `paper_state.json`. Railway ephemeral storage can be reset on redeploy; use PostgreSQL wiring before relying on historical audit retention.

## GitHub connection

1. Push this repository to GitHub.
2. In Railway, create a new project from the GitHub repository.
3. Select the repository root as the service root.
4. Railway detects `Dockerfile` and `railway.json`.
5. Add the variables above in the service's Variables tab.
6. Generate a domain and verify `/health`.

Keep `ENABLE_LIVE_TRADING=false` and `ENABLE_PAPER_EXECUTION=false` while validating the deployment.
