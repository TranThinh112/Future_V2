# Architecture
Async services ingest validated OKX snapshots, compute deterministic features, run eight bounded analysis agents, aggregate consensus, and pass proposals through deterministic risk before paper/demo execution. PostgreSQL stores audit records; Redis stores ephemeral snapshots and locks.
