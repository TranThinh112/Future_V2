# Crypto Agent Trading Bot - 17 Phase Implementation Plan

Repository: `C:\Users\Admin\Documents\ChatGPT\crypto V2`

This plan follows the original 17-phase request exactly. The project must remain default-safe: no real trading during development, no hard-coded secrets, no withdrawal support, and any uncertain state becomes `HOLD`.

## Current Audit Snapshot

- Project skeleton exists with `app/`, `tests/`, `backtests/`, `docs/`, `migrations/`, `pyproject.toml`, `docker-compose.yml`, `.env.example`, and `README.md`.
- Git working tree currently contains untracked project files; preserve them and do not revert user-local changes.
- Latest verification: `pytest -q` passes with 33 tests.
- Static verification passes: `python -m ruff check .` and `python -m mypy app backtests`.
- Live trading remains locked by configuration and operator-gate policy.

## Phase 1 - Repository Survey

Status: DONE

Requirements:
- Read the repository before editing.
- Identify structure, package manager, tests, and configuration.
- Preserve existing work and never overwrite user changes.
- If empty, create a new Python structure.
- Maintain this implementation plan.

Current implementation:
- Repository has been surveyed.
- Python packaging uses `pyproject.toml`.
- Tests are under `tests/`.
- Runtime app is under `app/`.
- Plan is now aligned to the original 17 phases.

Verification:
- `pytest -q`
- `git status --short`

## Phase 2 - Stack Selection

Status: DONE

Required stack:
- Python 3.12+
- FastAPI
- asyncio
- httpx
- websockets
- Pydantic
- PostgreSQL
- Redis
- Docker Compose
- pytest
- ruff
- mypy
- OpenTelemetry
- Prometheus/Grafana where appropriate

Current implementation:
- Dependencies are declared in `pyproject.toml`.
- Docker Compose provides PostgreSQL and Redis.
- Prometheus metrics and optional OpenTelemetry tracing are configured.
- Dev tools include pytest, ruff, and mypy.

Verification:
- `pip install -e ".[dev]"`
- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy app`

## Phase 3 - Project Structure

Status: DONE

Required structure:
- `app/api`
- `app/agents`
- `app/market_data`
- `app/features`
- `app/consensus`
- `app/risk`
- `app/execution`
- `app/storage`
- `app/alerts`
- `app/config.py`
- `migrations`
- `tests`
- `backtests`
- `docs`
- `docker-compose.yml`
- `pyproject.toml`
- `.env.example`
- `README.md`

Current implementation:
- Required directories and files exist.

Verification:
- `rg --files`

## Phase 4 - Environment Configuration

Status: DONE

Requirements:
- Provide `.env.example`.
- Default `TRADING_MODE=paper`.
- Default `OKX_DEMO_TRADING=true`.
- Default `ENABLE_LIVE_TRADING=false`.
- Validate configuration on startup.
- Never hard-code API keys.

Current implementation:
- `.env.example` includes OKX, OpenAI, database, Redis, risk, live guard, Discord, and OpenTelemetry settings.
- `Settings` validates live mode and allowed symbols.
- Live mode refuses to start without explicit enablement and credentials.

Verification:
- `python -m pytest tests/test_safety.py tests/test_config_symbols.py`

## Phase 5 - OKX Client

Status: DONE

Requirements:
- REST authentication according to OKX signing rules.
- Public WebSocket.
- Private/account WebSocket.
- ticker, candles, order book, balances, open orders, positions.
- create order, cancel order, order status.
- instrument metadata.
- timeout, bounded retry, exponential backoff, rate-limit handling.
- WebSocket reconnect.
- request signing.
- structured logging.
- no withdrawal support.

Current implementation:
- REST client supports signing, retries, timeout, 429 handling, demo header, allowed symbols, ticker, candles, order book, balances, orders, positions, order status, trades, and instruments.
- WebSocket modules exist.
- Private WebSocket login message helper exists.
- Secret redaction helper exists for safe request metadata logging.
- No withdrawal API exists.

Remaining work:
- Run external OKX demo/public integration checks with operator-provided credentials before any live use.

Verification:
- `python -m pytest tests/test_okx_client.py tests/test_orderbook.py`

## Phase 6 - Market Data Service

Status: DONE

Requirements:
- Collect OHLCV, bid/ask, spread, order book, volume, trades, account state.
- Store snapshots in PostgreSQL or Redis.
- Detect stale data, missing candle, bad timestamp, abnormal price, and WebSocket disconnect.
- Invalid data returns `HOLD`.

Current implementation:
- Market data service and order book modules exist.
- Tests cover market data and stale/failure behavior.
- Persistence primitives exist.
- Snapshot quality, HOLD fallback, missing-candle detection, abnormal-price detection, and audit persistence helpers exist.

Remaining work:
- Run production deployment with PostgreSQL/Redis enabled before unattended operation.

Verification:
- `python -m pytest tests/test_market_data.py tests/test_orderbook.py`

## Phase 7 - Feature Engine

Status: DONE

Requirements:
- EMA 20/50/200, RSI, MACD, ATR, Bollinger Bands.
- volatility, volume z-score.
- support/resistance.
- spread percentage.
- estimated slippage.
- trend direction.
- market regime.
- Unit tests for important indicators.

Current implementation:
- Feature and indicator modules exist.
- Tests cover core indicator behavior.

Verification:
- `python -m pytest tests/test_core.py`

## Phase 8 - Eight Groktopus Agents

Status: DONE

Required agents:
- VESKA
- NORO
- LUMEN
- TIDAL
- ZEPHR
- RUNE
- OKAPI
- MARIN

Required behavior:
- Separate system prompt, task, and criteria.
- Strict JSON schema.
- Snapshot-only input.
- No API key access.
- No direct order placement/cancel.
- No risk-limit changes.
- Missing or unreliable data returns `HOLD`.
- Include `confidence`, `reason_codes`, and `invalidators`.

Current implementation:
- Exactly eight agent names are configured.
- Prompts and OpenAI adapter exist.
- Pydantic schema validates output.
- Fallback returns `HOLD`.

Verification:
- `python -m pytest tests/test_agent_fallback.py tests/test_orchestrator.py`

## Phase 9 - GPT Integration

Status: DONE

Requirements:
- OpenAI Responses API.
- Model `gpt-5.4-mini`.
- timeout, retry, token/cost logging.
- JSON validation.
- fallback to `HOLD`.
- no secret or personal data sent.
- no arbitrary tool choice.
- separate system prompt per agent.

Current implementation:
- Responses API adapter exists.
- Default model is `gpt-5.4-mini`.
- Timeout, bounded retry, and JSON validation exist.
- Malformed/timeout failures return `HOLD`.
- Prompts are separated by agent.
- Secret-like keys are stripped from snapshots before sending to the model.
- API usage metadata is logged when returned by the Responses API.

Verification:
- `python -m pytest tests/test_agent_fallback.py`

## Phase 10 - Consensus Engine

Status: DONE

Requirements:
- Weighted aggregation:
  - Trend 20%
  - Momentum 15%
  - Regime 15%
  - Liquidity 10%
  - Sentiment 10%
  - Portfolio 10%
  - Execution 10%
  - Critic 10%
- score >= 0.72 can move to risk check.
- score 0.55-0.71 is `HOLD`.
- score < 0.55 is `HOLD`.
- critic strong objection is `HOLD`.
- degraded/bad data is `HOLD`.
- insufficient valid agents is `HOLD`.
- Persist votes and consensus score.

Current implementation:
- Eight-agent aggregation exists with 0.72 approval threshold.
- Veto, bad data, or missing agents hold.
- Consensus schema includes votes and score.
- Weight domains are explicitly mapped to trend, momentum, regime, liquidity, sentiment, portfolio, execution, and critic.

Verification:
- `python -m pytest tests/test_orchestrator.py`

## Phase 11 - Deterministic Risk Engine

Status: DONE

Requirements:
- No GPT.
- max position, total exposure, risk per trade.
- daily loss and max drawdown.
- spread and slippage.
- minimum liquidity.
- cooldown after stop-loss.
- max order count.
- no averaging down.
- no trading on API/data errors.
- position sizing from equity, risk, and stop distance.
- apply the smallest limit from all constraints and OKX metadata.

Current implementation:
- Deterministic risk checks exist.
- Position sizing exists.
- Core safety tests exist.

- OKX metadata rounding is enforced in order normalization and order submission when instrument metadata is supplied.

Verification:
- `python -m pytest tests/test_risk_extended.py tests/test_safety.py`

## Phase 12 - Order Manager

Status: DONE

Requirements:
- Create order proposals.
- Round by OKX metadata.
- Choose limit/market.
- Unique client order ID.
- Place order.
- Track partial fill.
- Cancel expired order.
- Sync fills.
- Place stop-loss/take-profit.
- Reconcile position.
- Link every order to decision, votes, consensus, risk result, order ID, fills, and timestamps.

Current implementation:
- Order manager exists.
- Duplicate prevention exists.
- Paper execution path exists.
- Protective order helpers exist.
- Reconciliation module exists.
- Order submission applies instrument metadata rounding when metadata is supplied.
- Order result includes decision, votes, consensus, risk result, order ID, client order ID, and timestamps for audit linkage.

Remaining work:
- Run partial-fill and expiry behavior against OKX demo before live use.

Verification:
- `python -m pytest tests/test_order_manager.py tests/test_execution_guards.py tests/test_paper.py`

## Phase 13 - Database

Status: DONE

Requirements:
- Migration/model for:
  - market_candles
  - orderbook_snapshots
  - features
  - agent_decisions
  - consensus_decisions
  - risk_checks
  - orders
  - fills
  - positions
  - equity_snapshots
  - system_events
- Do not store API secrets.

Current implementation:
- `migrations/001_init.sql` includes all required tables.
- Storage modules exist.
- Secret persistence is out of scope and not implemented.

Verification:
- `python -m pytest tests/test_migrations.py tests/test_postgres.py`

## Phase 14 - Backtest

Status: DONE

Requirements:
- Fees, spread, slippage.
- Partial fill.
- Stop-loss and take-profit.
- Latency.
- Initial capital.
- Out-of-sample split.
- total return, max drawdown, Sharpe, Sortino, win rate, profit factor, average trade, turnover, fee impact.
- No look-ahead data.

Current implementation:
- Backtest engine exists.
- Backtest tests exist.
- Event-style long strategy simulation models fees, spread, slippage, partial fill percentage, stop-loss, take-profit, latency, initial capital, out-of-sample split, and the requested core metrics.

Remaining work:
- Add more historical fixtures as strategies mature.

Verification:
- `python -m pytest tests/test_backtest.py`

## Phase 15 - Paper/Demo/Live Modes

Status: DONE

Requirements:
- Modes: `backtest`, `paper`, `okx_demo`, `live`.
- Default `paper`.
- Live locked unless `ENABLE_LIVE_TRADING=true`.
- Live prints clear warning on startup.
- GPT cannot enable live.
- Live API key must be trade-only.

Current implementation:
- Mode enum exists.
- Default is `paper`.
- Live config guard exists.
- Order manager refuses live without explicit operator gate.
- OKX demo header support exists.
- Live startup emits a critical warning.

Remaining work:
- Run end-to-end OKX demo test and manually verify trade-only API permission before any live consideration.

Verification:
- `python -m pytest tests/test_demo.py tests/test_safety.py`

## Phase 16 - Testing And Monitoring

Status: DONE

Requirements:
- Tests for indicators, schema, consensus, position sizing, risk limits, stale data, duplicate order, reconnect, partial fill, timeout, malformed GPT output, restart/reconciliation.
- Health endpoint.
- Metrics.
- Structured logs.
- Telegram/Discord alerts if easy.
- Kill switch.
- Emergency shutdown.

Current implementation:
- 33 tests currently pass.
- Health endpoint exists.
- Prometheus metrics exist.
- Structured logging helper exists.
- Discord/webhook alert module exists.
- Kill switch endpoint exists.
- WebSocket reconnect behavior has test coverage.
- `ruff` and `mypy` pass.

Remaining work:
- Add Telegram alert adapter if needed by operations.

Verification:
- `python -m pytest`
- `python -m ruff check .`
- `python -m mypy app`

## Phase 17 - Documentation And Handoff

Status: DONE

Requirements:
- `README.md`
- `docs/architecture.md`
- `docs/security.md`
- `docs/operations.md`
- `docs/backtesting.md`
- `docs/okx-setup.md`
- `docs/prompt-design.md`
- README covers dependencies, `.env`, database/Redis, tests, backtest, paper, OKX demo, and controlled live enablement.

Current implementation:
- Required docs exist.
- README includes setup, test, backtest, paper, OKX demo, live guard, endpoints, and safety notes.

Verification:
- Manual doc review.

## Absolute Safety Rules

1. Do not place real orders during development.
2. Do not implement or call withdrawal APIs.
3. Do not commit `.env`.
4. Do not log secrets.
5. GPT cannot bypass deterministic risk.
6. Do not increase leverage automatically.
7. Do not increase capital automatically.
8. Do not disable stop-loss automatically.
9. If uncertain, return `HOLD`.
10. Before any action that could trade live funds, stop and ask the operator for explicit confirmation.
