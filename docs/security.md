# Security

Secrets come only from environment variables or a secret manager. Do not commit `.env`, API keys, passphrases, account identifiers, or private trading logs. The application must never persist OKX secrets in PostgreSQL, Redis, SQLite, telemetry, or structured logs.

OKX keys must be trade-only. Withdrawal permission is out of scope and no withdrawal API is implemented. Live mode is locked behind `TRADING_MODE=live`, `ENABLE_LIVE_TRADING=true`, credential validation, deterministic risk checks, and an operator gate.

GPT agents receive sanitized market snapshots only. They cannot access API keys, choose arbitrary tools, change risk limits, place orders, cancel orders, disable stops, increase leverage, or increase capital. Missing, stale, malformed, contradictory, or low-quality data must produce `HOLD`.

Before any action that could touch real funds, stop and require explicit operator confirmation.
