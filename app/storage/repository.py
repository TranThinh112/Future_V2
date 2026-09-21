import asyncio
import json
import os
import sqlite3
import time
from typing import Any


def _postgres_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def summarize(rows: list[dict]) -> dict:
    """Aggregate AI token/cost totals and per-agent usage from audit rows."""
    totals = {"rounds": 0, "agent_calls": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
    recent_window = {"rounds": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0}
    window_start = time.time() - 86400
    agents: dict[str, dict] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if row.get("kind") == "consensus":
            usage = payload.get("ai_usage") or {}
            totals["rounds"] += 1
            totals["agent_calls"] += int(usage.get("agent_count") or 0)
            totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            totals["total_tokens"] += int(usage.get("total_tokens") or 0)
            totals["estimated_cost_usd"] += float(usage.get("estimated_cost_usd") or 0)
            if (row.get("timestamp") or 0) >= window_start:
                recent_window["rounds"] += 1
                recent_window["input_tokens"] += int(usage.get("input_tokens") or 0)
                recent_window["output_tokens"] += int(usage.get("output_tokens") or 0)
                recent_window["total_tokens"] += int(usage.get("total_tokens") or 0)
                recent_window["estimated_cost_usd"] += float(usage.get("estimated_cost_usd") or 0)
        elif row.get("kind") == "agent_decision":
            name = str(payload.get("agent_name") or "unknown")
            entry = agents.setdefault(name, {
                "agent": name, "calls": 0, "input_tokens": 0, "output_tokens": 0,
                "total_tokens": 0, "estimated_cost_usd": 0.0, "fallback_calls": 0, "veto_calls": 0,
            })
            entry["calls"] += 1
            entry["input_tokens"] += int(payload.get("input_tokens") or 0)
            entry["output_tokens"] += int(payload.get("output_tokens") or 0)
            entry["total_tokens"] += int(payload.get("total_tokens") or 0)
            entry["estimated_cost_usd"] += float(payload.get("estimated_cost_usd") or 0)
            if payload.get("status") and payload["status"] != "ok":
                entry["fallback_calls"] += 1
            if payload.get("veto"):
                entry["veto_calls"] += 1
    totals["estimated_cost_usd"] = round(totals["estimated_cost_usd"], 10)
    recent_window["estimated_cost_usd"] = round(recent_window["estimated_cost_usd"], 10)
    for entry in agents.values():
        entry["estimated_cost_usd"] = round(entry["estimated_cost_usd"], 10)
    return {"totals": totals, "last_24h": recent_window, "agents": [agents[name] for name in sorted(agents)]}

class AuditRepository:
    """SQLite audit repository retained for local tests and explicit file paths."""

    def __init__(self, path="crypto.db"):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS audit(kind TEXT,payload TEXT,ts REAL)")
        self.db.commit()

    def append(self, kind, payload):
        self.db.execute(
            "INSERT INTO audit VALUES(?,?,?)",
            (kind, json.dumps(payload), time.time()),
        )
        self.db.commit()

    def recent(self, limit=20):
        return [
            {"kind": kind, "payload": json.loads(payload), "timestamp": ts}
            for kind, payload, ts in self.db.execute(
                "SELECT kind,payload,ts FROM audit ORDER BY ts DESC LIMIT ?", (limit,)
            )
        ]

    def close(self):
        self.db.close()

    def latest_by_symbol(self, kind):
        result = {}
        for row in self.recent(1000):
            symbol = row["payload"].get("symbol")
            if row["kind"] == kind and symbol and symbol not in result:
                result[symbol] = row
        return result


class AsyncSQLiteAuditRepository:
    """Async-compatible wrapper for local SQLite development."""

    def __init__(self, path="crypto.db"):
        self.repository = AuditRepository(path)

    async def append(self, kind, payload):
        self.repository.append(kind, payload)

    async def recent(self, limit=20):
        return self.repository.recent(limit)

    async def close(self):
        self.repository.close()

    async def aggregate_hourly(self, retention_days=30):
        return None

    async def cleanup(self, retention_days=30):
        return None


    async def summary(self, limit=2000):
        return summarize(self.repository.recent(limit))

    async def market_scan_hourly(self, limit=48):
        return []

class PostgresAuditRepository:
    """Durable audit repository backed by Railway PostgreSQL."""

    def __init__(self, database_url: str):
        self.database_url = _postgres_url(database_url)
        self.pool = None
        self._connect_lock = asyncio.Lock()

    async def connect(self):
        if self.pool is not None:
            return self
        async with self._connect_lock:
            if self.pool is not None:
                return self
            try:
                import asyncpg
            except ImportError as error:
                raise RuntimeError("asyncpg is required for PostgreSQL audit storage") from error
            last_error = None
            for attempt in range(1, 4):
                try:
                    pool = await asyncpg.create_pool(self.database_url, min_size=1, max_size=5, timeout=10)
                    async with pool.acquire() as connection:
                        await self._ensure_schema(connection)
                    self.pool = pool
                    return self
                except Exception as error:
                    last_error = error
                    if attempt < 3:
                        await asyncio.sleep(attempt * 2)
            raise last_error

    async def _ensure_schema(self, connection):
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events(
                id BIGSERIAL PRIMARY KEY,
                kind TEXT NOT NULL,
                payload JSONB NOT NULL,
                ts DOUBLE PRECISION NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts DESC)"
        )
        await connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_events_kind_ts ON audit_events(kind, ts DESC)"
        )
        await connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_scan_hourly(
                bucket_start TIMESTAMPTZ NOT NULL,
                symbol TEXT NOT NULL,
                scans INTEGER NOT NULL,
                buy_count INTEGER NOT NULL,
                sell_count INTEGER NOT NULL,
                hold_count INTEGER NOT NULL,
                min_price DOUBLE PRECISION,
                max_price DOUBLE PRECISION,
                last_price DOUBLE PRECISION,
                avg_rsi DOUBLE PRECISION,
                ai_calls INTEGER NOT NULL DEFAULT 0,
                ai_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY(bucket_start, symbol)
            )
            """
        )

    async def append(self, kind: str, payload: dict[str, Any]):
        for attempt in range(1, 4):
            try:
                await self.connect()
                async with self.pool.acquire() as connection:
                    await connection.execute(
                        "INSERT INTO audit_events(kind, payload, ts) VALUES($1, $2::jsonb, $3)",
                        kind,
                        json.dumps(payload, default=str),
                        time.time(),
                    )
                return
            except Exception:
                if attempt == 3:
                    raise
                await self.close()
                await asyncio.sleep(attempt * 2)

    async def recent(self, limit: int = 20):
        await self.connect()
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT kind, payload, ts FROM audit_events ORDER BY ts DESC LIMIT $1", limit
            )
        return [
            {
                "kind": row["kind"],
                "payload": json.loads(row["payload"])
                if isinstance(row["payload"], str)
                else row["payload"],
                "timestamp": row["ts"],
            }
            for row in rows
        ]

    async def aggregate_hourly(self, retention_days: int = 30):
        await self.connect()
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO market_scan_hourly(
                    bucket_start, symbol, scans, buy_count, sell_count, hold_count,
                    min_price, max_price, last_price, avg_rsi, ai_calls, ai_cost_usd, updated_at
                )
                WITH ticks AS (
                    SELECT
                        date_trunc('hour', to_timestamp(ts)) AS bucket_start,
                        payload->>'symbol' AS symbol,
                        payload->>'action' AS action,
                        NULLIF(payload->>'price', '')::double precision AS price,
                        NULLIF(payload->>'rsi', '')::double precision AS rsi,
                        ts
                    FROM audit_events
                    WHERE kind = 'paper_tick'
                      AND ts < extract(epoch FROM date_trunc('hour', now()))
                      AND ts >= extract(epoch FROM now() - ($1::int * interval '1 day'))
                      AND payload ? 'symbol'
                ), last_prices AS (
                    SELECT DISTINCT ON (bucket_start, symbol)
                        bucket_start, symbol, price AS last_price
                    FROM ticks
                    ORDER BY bucket_start, symbol, ts DESC
                ), grouped AS (
                    SELECT
                        bucket_start,
                        symbol,
                        count(*)::int AS scans,
                        count(*) FILTER (WHERE action = 'buy')::int AS buy_count,
                        count(*) FILTER (WHERE action = 'sell')::int AS sell_count,
                        count(*) FILTER (WHERE action = 'hold')::int AS hold_count,
                        min(price) AS min_price,
                        max(price) AS max_price,
                        avg(rsi) AS avg_rsi
                    FROM ticks
                    GROUP BY bucket_start, symbol
                )
                SELECT
                    grouped.bucket_start, grouped.symbol, scans, buy_count, sell_count, hold_count,
                    min_price, max_price, last_price, avg_rsi, 0, 0, now()
                FROM grouped
                JOIN last_prices USING(bucket_start, symbol)
                ON CONFLICT(bucket_start, symbol) DO UPDATE SET
                    scans = EXCLUDED.scans,
                    buy_count = EXCLUDED.buy_count,
                    sell_count = EXCLUDED.sell_count,
                    hold_count = EXCLUDED.hold_count,
                    min_price = EXCLUDED.min_price,
                    max_price = EXCLUDED.max_price,
                    last_price = EXCLUDED.last_price,
                    avg_rsi = EXCLUDED.avg_rsi,
                    updated_at = now()
                """,
                retention_days,
            )

    async def cleanup(self, retention_days: int = 30):
        await self.connect()
        async with self.pool.acquire() as connection:
            await connection.execute(
                """
                DELETE FROM audit_events
                WHERE kind = 'paper_tick'
                  AND ts < extract(epoch FROM now() - ($1::int * interval '1 day'))
                """,
                retention_days,
            )

    async def close(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def summary(self):
        await self.connect()
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                """
                WITH windowed AS (
                    SELECT payload, ts, ts >= extract(epoch FROM now() - interval '24 hours') AS in_window
                    FROM audit_events WHERE kind = 'consensus'
                ), totals AS (
                    SELECT
                        count(*)::int AS rounds,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'agent_count','')::int), 0)::int AS agent_calls,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'input_tokens','')::bigint), 0)::bigint AS input_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'output_tokens','')::bigint), 0)::bigint AS output_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'total_tokens','')::bigint), 0)::bigint AS total_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'estimated_cost_usd','')::double precision), 0)::double precision AS estimated_cost_usd
                    FROM windowed
                ), recent AS (
                    SELECT
                        count(*)::int AS rounds,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'input_tokens','')::bigint), 0)::bigint AS input_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'output_tokens','')::bigint), 0)::bigint AS output_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'total_tokens','')::bigint), 0)::bigint AS total_tokens,
                        COALESCE(sum(NULLIF(payload->'ai_usage'->>'estimated_cost_usd','')::double precision), 0)::double precision AS estimated_cost_usd
                    FROM windowed WHERE in_window
                ), per_agent AS (
                    SELECT COALESCE(jsonb_agg(entry ORDER BY entry->>'agent'), '[]'::jsonb) AS rows FROM (
                        SELECT jsonb_build_object(
                            'agent', COALESCE(payload->>'agent_name', 'unknown'),
                            'calls', count(*)::int,
                            'input_tokens', COALESCE(sum(NULLIF(payload->>'input_tokens','')::bigint), 0),
                            'output_tokens', COALESCE(sum(NULLIF(payload->>'output_tokens','')::bigint), 0),
                            'total_tokens', COALESCE(sum(NULLIF(payload->>'total_tokens','')::bigint), 0),
                            'estimated_cost_usd', COALESCE(sum(NULLIF(payload->>'estimated_cost_usd','')::double precision), 0),
                            'fallback_calls', count(*) FILTER (WHERE COALESCE(payload->>'status', 'ok') <> 'ok')::int,
                            'veto_calls', count(*) FILTER (WHERE COALESCE((payload->>'veto')::boolean, false))::int
                        ) AS entry
                        FROM audit_events
                        WHERE kind = 'agent_decision'
                        GROUP BY COALESCE(payload->>'agent_name', 'unknown')
                    ) grouped
                )
                SELECT
                    (SELECT row_to_json(totals) FROM totals) AS totals,
                    (SELECT row_to_json(recent) FROM recent) AS last_24h,
                    (SELECT rows FROM per_agent) AS agents
                """
            )
        decode = lambda value: json.loads(value) if isinstance(value, str) else value
        totals = decode(row["totals"])
        agents = decode(row["agents"])
        recent = decode(row["last_24h"])
        return {
            "totals": {
                "rounds": totals["rounds"],
                "agent_calls": totals["agent_calls"],
                "input_tokens": totals["input_tokens"],
                "output_tokens": totals["output_tokens"],
                "total_tokens": totals["total_tokens"],
                "estimated_cost_usd": round(float(totals["estimated_cost_usd"] or 0), 10),
            },
            "last_24h": {
                "rounds": recent["rounds"],
                "input_tokens": recent["input_tokens"],
                "output_tokens": recent["output_tokens"],
                "total_tokens": recent["total_tokens"],
                "estimated_cost_usd": round(float(recent["estimated_cost_usd"] or 0), 10),
            },
            "agents": [
                {
                    "agent": row["agent"],
                    "calls": row["calls"],
                    "input_tokens": row["input_tokens"],
                    "output_tokens": row["output_tokens"],
                    "total_tokens": row["total_tokens"],
                    "estimated_cost_usd": round(float(row["estimated_cost_usd"] or 0), 10),
                    "fallback_calls": row["fallback_calls"],
                    "veto_calls": row["veto_calls"],
                }
                for row in agents
            ],
        }

    async def market_scan_hourly(self, limit: int = 48):
        await self.connect()
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT bucket_start, symbol, scans, buy_count, sell_count, hold_count,
                       min_price, max_price, last_price, avg_rsi, ai_calls, ai_cost_usd
                FROM market_scan_hourly
                ORDER BY bucket_start DESC, symbol
                LIMIT $1
                """,
                limit,
            )
        return [dict(row) for row in rows]

def repository_from_url(database_url: str | None = None):
    url = database_url or os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql"):
        return PostgresAuditRepository(url)
    return AsyncSQLiteAuditRepository()
