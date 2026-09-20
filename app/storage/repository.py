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


class PostgresAuditRepository:
    """Durable audit repository backed by Railway PostgreSQL."""

    def __init__(self, database_url: str):
        self.database_url = _postgres_url(database_url)
        self.connection = None

    async def connect(self):
        if self.connection is None:
            try:
                import asyncpg
            except ImportError as error:
                raise RuntimeError("asyncpg is required for PostgreSQL audit storage") from error
            self.connection = await asyncpg.connect(self.database_url)
            await self.connection.execute(
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
            await self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_ts ON audit_events(ts DESC)"
            )
            await self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_events_kind_ts ON audit_events(kind, ts DESC)"
            )
        return self

    async def append(self, kind: str, payload: dict[str, Any]):
        await self.connect()
        await self.connection.execute(
            "INSERT INTO audit_events(kind, payload, ts) VALUES($1, $2::jsonb, $3)",
            kind,
            json.dumps(payload),
            time.time(),
        )

    async def recent(self, limit: int = 20):
        await self.connect()
        rows = await self.connection.fetch(
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

    async def close(self):
        if self.connection is not None:
            await self.connection.close()
            self.connection = None


def repository_from_url(database_url: str | None = None):
    url = database_url or os.getenv("DATABASE_URL", "")
    if url.startswith("postgresql"):
        return PostgresAuditRepository(url)
    return AsyncSQLiteAuditRepository()
