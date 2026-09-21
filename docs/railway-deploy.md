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
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
AI_INPUT_COST_PER_MILLION=0.75
AI_OUTPUT_COST_PER_MILLION=4.50
```

Do not commit `.env` or put real secret values in `.env.example`.

In Railway, provision PostgreSQL and Redis in the same project, then set these
variables as service references. Do not use `localhost` in Railway: that points
to the application container, not the managed database. The `preDeployCommand`
runs `python -m app.storage.migrate` before each deployment.

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

Audit events are stored in the PostgreSQL database referenced by `DATABASE_URL`, including agent decisions, consensus, paper ticks, token usage, and estimated costs. PostgreSQL must be provisioned in the Railway project and its reference URL assigned to `DATABASE_URL`; audit history then survives redeploys. Paper checkpoints remain in `paper_state.json` unless a persistent volume or database-backed state is added.

## GitHub connection

1. Push this repository to GitHub.
2. In Railway, create a new project from the GitHub repository.
3. Select the repository root as the service root.
4. Railway detects `Dockerfile` and `railway.json`.
5. Add the variables above in the service's Variables tab.
6. Generate a domain and verify `/health`.

Keep `ENABLE_LIVE_TRADING=false` and `ENABLE_PAPER_EXECUTION=false` while validating the deployment.


## Audit retention

`paper_tick` events are sampled by default to one row per symbol every 300 seconds,
while important ticks (`buy`, `sell`, market-data errors, fills, or AI consensus)
are always persisted immediately. PostgreSQL keeps detailed `paper_tick` rows for
`AUDIT_PAPER_TICK_RETENTION_DAYS` days and periodically aggregates older scan
history into `market_scan_hourly`. Agent decisions and consensus events are not
removed by this cleanup policy.
