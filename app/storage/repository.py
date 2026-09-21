import asyncio
import json
import os
import sqlite3
import time
from typing import Any


def _postgres_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


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

def repository_from_url(database_url: str | None = None):
    url = database_url or os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql"):
        return PostgresAuditRepository(url)
    return AsyncSQLiteAuditRepository()
