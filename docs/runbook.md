# Safety runbook

1. Confirm `/health` reports `paper_worker=true` and `/api/config/safety` reports `live_enabled=false`.
2. Review `/api/events` for stale-data, API errors, and consensus vetoes.
3. Inspect `/api/portfolio` before and after restart; checkpoint files are local paper state only.
4. Use `POST /api/kill-switch` for an immediate paper-worker stop.
5. Never set live mode from GPT output. Live requires a separate operator process and trade-only OKX permission.
